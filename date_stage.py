from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook


RDN_SOURCES = {
    "gas_rdn": ("Gaz RDN", "GAZ_RDN"),
    "electricity_rdn": ("Energia RDN", "EE_RDN"),
}
OTF_SOURCES = ("gas_otf", "electricity_otf")
OTF_LOOKBACK_DAYS = 14
INITIAL_RDN_HISTORY_DAYS = 7

WEEKDAY_NAMES = (
    "poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"
)


@dataclass(frozen=True)
class DatePlan:
    latest_rdn_dates: dict[str, date | None]
    effective_latest_rdn_dates: dict[str, date]
    used_fallback: dict[str, bool]
    rdn_dates: dict[str, list[date]]
    otf_session_candidates: list[date]
    coal_window: tuple[date, date]
    eua_window: tuple[date, date]


def _parse_date(value: object, sheet_name: str) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip()[:10])
        except ValueError as error:
            raise ValueError(
                f"Nieprawidłowa data w arkuszu {sheet_name}: {value!r}."
            ) from error
    if value is None:
        return None
    raise ValueError(f"Nieprawidłowa data w arkuszu {sheet_name}: {value!r}.")


def get_latest_rdn_dates(workbook_path: Path) -> dict[str, date | None]:
    """Read the latest stored date independently for gas and electricity RDN."""
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        latest_dates: dict[str, date | None] = {}
        for source, (_, sheet_name) in RDN_SOURCES.items():
            if sheet_name not in workbook.sheetnames:
                raise ValueError(
                    f"W pliku DataMaster.xlsx nie znaleziono arkusza {sheet_name}."
                )
            worksheet = workbook[sheet_name]
            headers = next(
                worksheet.iter_rows(min_row=1, max_row=1, values_only=True), None
            )
            if not headers or not any(value is not None for value in headers):
                latest_dates[source] = None
                continue
            if "trading_date" not in headers:
                raise ValueError(
                    f"W arkuszu {sheet_name} nie znaleziono kolumny trading_date."
                )
            date_column = headers.index("trading_date") + 1
            dates = []
            for (value,) in worksheet.iter_rows(
                min_row=2,
                min_col=date_column,
                max_col=date_column,
                values_only=True,
            ):
                parsed = _parse_date(value, sheet_name)
                if parsed is not None:
                    dates.append(parsed)
            latest_dates[source] = max(dates) if dates else None
        return latest_dates
    finally:
        workbook.close()


def get_dates_between(
    latest_date: date, end_date: date, *, weekdays_only: bool = False
) -> list[date]:
    current = latest_date + timedelta(days=1)
    dates: list[date] = []
    while current <= end_date:
        if not weekdays_only or current.weekday() < 5:
            dates.append(current)
        current += timedelta(days=1)
    return dates


def get_otf_session_candidates(today: date) -> list[date]:
    """Return recent weekdays that may be the latest closed OTF session."""
    first_date = today - timedelta(days=OTF_LOOKBACK_DAYS)
    last_date = today - timedelta(days=1)
    return [
        first_date + timedelta(days=offset)
        for offset in range((last_date - first_date).days + 1)
        if (first_date + timedelta(days=offset)).weekday() < 5
    ]


def build_date_plan(
    latest_rdn_dates: dict[str, date | None], today: date
) -> DatePlan:
    # An empty sheet starts with a small bootstrap window. Once data exists,
    # request every missing calendar day after the latest stored observation.
    empty_sheet_baseline = today - timedelta(days=INITIAL_RDN_HISTORY_DAYS + 1)
    effective_dates = {
        source: stored_date or empty_sheet_baseline
        for source, stored_date in latest_rdn_dates.items()
    }
    used_fallback = {
        source: stored_date is None
        for source, stored_date in latest_rdn_dates.items()
    }
    end_date = today - timedelta(days=1)
    rdn_dates = {
        source: get_dates_between(effective_dates[source], end_date)
        for source in RDN_SOURCES
    }
    rolling_window = (today - timedelta(days=29), today)
    return DatePlan(
        latest_rdn_dates=latest_rdn_dates,
        effective_latest_rdn_dates=effective_dates,
        used_fallback=used_fallback,
        rdn_dates=rdn_dates,
        otf_session_candidates=get_otf_session_candidates(today),
        coal_window=rolling_window,
        eua_window=rolling_window,
    )


def load_date_plan(workbook_path: Path, today: date) -> DatePlan:
    plan = build_date_plan(get_latest_rdn_dates(workbook_path), today)
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        end_date = today - timedelta(days=1)
        start_date = end_date - timedelta(days=INITIAL_RDN_HISTORY_DAYS - 1)
        missing: dict[str, list[date]] = {}
        for source, (_, sheet_name) in RDN_SOURCES.items():
            worksheet = workbook[sheet_name]
            headers = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
            date_column = headers.index("trading_date")
            stored = {
                parsed
                for row in worksheet.iter_rows(min_row=2, values_only=True)
                if (parsed := _parse_date(row[date_column], sheet_name)) is not None
            }
            required = [
                start_date + timedelta(days=offset)
                for offset in range(INITIAL_RDN_HISTORY_DAYS)
            ]
            missing[source] = [value for value in required if value not in stored]
        return replace(plan, rdn_dates=missing)
    finally:
        workbook.close()


def select_latest_otf_session(
    candidates: list[date], holidays: list[date]
) -> date:
    holiday_set = set(holidays)
    valid_dates = [value for value in candidates if value not in holiday_set]
    if not valid_dates:
        raise ValueError(
            "Nie można ustalić ostatniej sesji OTF. "
            "Wszystkie daty kontrolne oznaczono jako święta."
        )
    return max(valid_dates)


def show_date_selection(workbook_path: Path) -> None:
    import streamlit as st

    st.title("Weryfikacja dat pobierania")
    report_date: date = st.session_state["report_date"]
    allow_change = st.toggle(
        "Zmień datę raportu",
        value=st.session_state.get("allow_report_date_change", False),
    )
    st.session_state["allow_report_date_change"] = allow_change
    selected_report_date = st.date_input(
        "Raport na dzień",
        value=report_date,
        max_value=date.today() - timedelta(days=1),
        disabled=not allow_change,
    )
    if selected_report_date != report_date:
        st.session_state["report_date"] = selected_report_date
        st.session_state["date_plan"] = load_date_plan(
            workbook_path, selected_report_date + timedelta(days=1)
        )
        st.session_state.pop("holiday_date_table", None)
        st.rerun()
    st.caption(
        "Data raportu wyznacza koniec zakresu danych. Domyślnie jest to wczoraj."
    )
    plan: DatePlan = st.session_state["date_plan"]
    st.subheader("Historia RDN")
    summary_rows = []
    for source, (label, sheet_name) in RDN_SOURCES.items():
        stored = plan.latest_rdn_dates[source]
        effective = plan.effective_latest_rdn_dates[source]
        summary_rows.append(
            {
                "Rynek": label,
                "Arkusz": sheet_name,
                "Ostatnia zapisana data": stored.isoformat() if stored else "brak danych",
                "Data bazowa": effective.isoformat(),
                "Dat do uzupełnienia": len(plan.rdn_dates[source]),
                "Fallback": "tak" if plan.used_fallback[source] else "nie",
            }
        )
    st.dataframe(summary_rows, hide_index=True, width="stretch")
    if any(plan.used_fallback.values()):
        st.info(
            "Dla pustego arkusza RDN aplikacja pobierze ostatnie 7 "
            "zakończonych dni kalendarzowych, osobno dla gazu i energii."
        )

    st.subheader("Ostatnia zamknięta sesja OTF")
    st.write(
        "Weekend jest odfiltrowany automatycznie. Zaznacz święta giełdowe; "
        "aplikacja wybierze najnowszy pozostały dzień dla gazu i energii."
    )
    selected_holidays = set(st.session_state.get("selected_holidays", []))
    edited_dates = st.data_editor(
        [
            {
                "Date": (
                    f"{session_date.isoformat()} "
                    f"{WEEKDAY_NAMES[session_date.weekday()].capitalize()}"
                ),
                "Holiday": session_date in selected_holidays,
            }
            for session_date in reversed(plan.otf_session_candidates)
        ],
        hide_index=True,
        disabled=["Date"],
        column_config={
            "Date": st.column_config.TextColumn("Data", width="medium"),
            "Holiday": st.column_config.CheckboxColumn("Święto"),
        },
        key="holiday_date_table",
    )

    start, end = plan.coal_window
    st.subheader("Pozostałe zakresy")
    st.write(
        f"Węgiel i EUA: pełne ruchome okno 30 dni od "
        f"{start.isoformat()} do {end.isoformat()} włącznie."
    )
    if st.button("Potwierdź daty", type="primary", key="confirm_table_dates"):
        holidays = [
            date.fromisoformat(row["Date"].split()[0])
            for row in edited_dates
            if row["Holiday"]
        ]
        try:
            confirm_dates(holidays, workbook_path)
        except ValueError as error:
            st.error(str(error))


def confirm_dates(holidays: list[date], workbook_path: Path | None = None) -> None:
    import streamlit as st

    plan: DatePlan = st.session_state["date_plan"]
    otf_session_date = select_latest_otf_session(
        plan.otf_session_candidates, holidays
    )
    st.session_state["selected_holidays"] = holidays
    st.session_state["confirmed_source_dates"] = {
        **plan.rdn_dates,
        "gas_otf": [otf_session_date],
        "electricity_otf": [otf_session_date],
    }
    st.session_state["otf_session_date"] = otf_session_date
    st.session_state["coal_window"] = plan.coal_window
    st.session_state["eua_window"] = plan.eua_window
    if workbook_path is None:
        st.session_state["page"] = "prompt"
    else:
        from data_coverage import assess_coverage
        coverage = assess_coverage(workbook_path, plan.rdn_dates, otf_session_date, plan.coal_window, plan.eua_window)
        st.session_state["coverage_result"] = coverage
        st.session_state["page"] = "ready" if coverage.complete else "prompt"
    st.rerun()
