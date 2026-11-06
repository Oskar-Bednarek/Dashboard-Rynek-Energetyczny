from market_values import valid_tge_record
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook

from contract_selection import build_contract_set


RDN_SOURCES = {
    "gas_rdn": ("Gaz RDN", "GAZ_RDN"),
    "electricity_rdn": ("Energia RDN", "EE_RDN"),
}
OTF_SOURCES = ("gas_otf", "electricity_otf")
OTF_CANDIDATE_COUNT = 5
RDN_LOOKBACK_DAYS = 30
RDN_FETCH_LIMIT = 7
INITIAL_RDN_HISTORY_DAYS = 7

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
    """Return the five most recent weekdays before the report date."""
    candidates = []
    current = today - timedelta(days=1)
    while len(candidates) < OTF_CANDIDATE_COUNT:
        if current.weekday() < 5:
            candidates.append(current)
        current -= timedelta(days=1)
    return candidates


def build_otf_contract_preview(candidates: list[date]) -> list[dict[str, str]]:
    rows = []
    for market_label, gas in (("Gaz", True), ("Energia", False)):
        grouped_contracts: dict[str, list[str]] = {
            "Tygodniowe": [],
            "Miesięczne": [],
            "Kwartalne": [],
            "Roczne": [],
        }
        seen_by_group = {group: set() for group in grouped_contracts}
        for candidate in sorted(candidates, reverse=True):
            contracts = build_contract_set(candidate, gas=gas)
            for group_label, instruments in (
                ("Tygodniowe", contracts.weeks),
                ("Miesięczne", contracts.months),
                ("Kwartalne", contracts.quarters),
                ("Roczne", contracts.years),
            ):
                for instrument in instruments:
                    if instrument not in seen_by_group[group_label]:
                        seen_by_group[group_label].add(instrument)
                        grouped_contracts[group_label].append(instrument)
        for group_label, instruments in grouped_contracts.items():
            rows.append(
                {
                    "Rynek": market_label,
                    "Rodzaj": group_label,
                    "Przykładowe kontrakty": ", ".join(instruments),
                }
            )
    return rows


def build_date_plan(
    latest_rdn_dates: dict[str, date | None], today: date
) -> DatePlan:
    # The workbook-aware planner below finds internal gaps across 30 days.
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
    window_start = end_date - timedelta(days=RDN_LOOKBACK_DAYS - 1)
    request_baseline = window_start - timedelta(days=1)
    rdn_dates = {
        source: get_dates_between(
            max(effective_dates[source], request_baseline), end_date
        )[-RDN_FETCH_LIMIT:]
        for source in RDN_SOURCES
    }
    report_date = today - timedelta(days=1)
    rolling_window = (report_date - timedelta(days=29), report_date)
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
        missing: dict[str, list[date]] = {}
        for source, (_, sheet_name) in RDN_SOURCES.items():
            worksheet = workbook[sheet_name]
            headers = [cell.value for cell in next(worksheet.iter_rows(min_row=1, max_row=1))]
            date_column = headers.index("trading_date")
            id_column = headers.index("data_id") if "data_id" in headers else None
            expected_id = "tge_gas_da" if source == "gas_rdn" else "tge_power_da_base"
            stored = {
                parsed
                for row in worksheet.iter_rows(min_row=2, values_only=True)
                if valid_tge_record(dict(zip(headers, row)), "gas" if source == "gas_rdn" else "electricity", "day_ahead")
                and (id_column is not None and row[id_column] == expected_id)
                and (parsed := _parse_date(row[date_column], sheet_name)) is not None
            }
            if source == "electricity_rdn":
                report_day = today - timedelta(days=1)
                latest_valid_ids = {
                    record.get("data_id")
                    for row in worksheet.iter_rows(min_row=2, values_only=True)
                    if (record := dict(zip(headers, row)))
                    and _parse_date(record.get("trading_date"), sheet_name) == report_day
                    and valid_tge_record(record, "electricity", "day_ahead")
                }
                if not {"tge_power_da_base", "tge_power_da_peak", "tge_power_da_offpeak", "tge_power_da_24"}.issubset(latest_valid_ids):
                    stored.discard(report_day)
            missing[source] = [
                value for value in get_dates_between(
                    today - timedelta(days=RDN_LOOKBACK_DAYS + 1), today - timedelta(days=1)
                ) if value not in stored
            ][-RDN_FETCH_LIMIT:]
        return replace(plan, rdn_dates=missing)
    finally:
        workbook.close()


def validate_otf_session_choice(candidates: list[date], selected_date: date) -> date:
    if selected_date not in candidates:
        raise ValueError("Wybierz datę sesji OTF z listy dostępnych dni.")
    return selected_date


def show_date_selection(workbook_path: Path) -> None:
    import streamlit as st

    st.title("Wybór dat i zakresu danych")
    report_date: date = st.session_state["report_date"]
    selected_report_date = st.date_input(
        "Data raportu",
        value=report_date,
        max_value=date.today() - timedelta(days=1),
    )
    if selected_report_date != report_date:
        st.session_state["report_date"] = selected_report_date
        updated_plan = load_date_plan(
            workbook_path, selected_report_date + timedelta(days=1)
        )
        st.session_state["date_plan"] = updated_plan
        st.session_state["selected_otf_session_date"] = (
            updated_plan.otf_session_candidates[0]
        )
        st.rerun()
    st.caption(
        "Data raportu określa, do którego dnia pobierane są dane. "
        "Jej zmiana aktualizuje zakresy."
    )
    plan: DatePlan = st.session_state["date_plan"]
    candidate_dates = sorted(plan.otf_session_candidates, reverse=True)
    selection_key = "selected_otf_session_date"
    if candidate_dates:
        if st.session_state.get(selection_key) not in candidate_dates:
            st.session_state[selection_key] = candidate_dates[0]
        selected_otf_session_date = st.radio(
            "Wybierz datę sesji kontraktów terminowych (OTF)",
            options=candidate_dates,
            format_func=lambda value: value.strftime("%d.%m.%Y"),
            key=selection_key,
        )
        st.caption(
            "Wybierz datę ostatniej sesji (ostatni dzień roboczy)."
        )
    else:
        selected_otf_session_date = None

    def format_date_range(dates: list[date]) -> str:
        if not dates:
            return "Potrzebne dane są już kompletne"
        if dates[0] == dates[-1]:
            return dates[0].strftime("%d.%m.%Y")
        return (
            f"{dates[0].strftime('%d.%m.%Y')}–{dates[-1].strftime('%d.%m.%Y')} "
            f"({len(dates)} dni)"
        )

    from data_coverage import assess_coverage
    coverage = assess_coverage(
        workbook_path, plan.rdn_dates, selected_otf_session_date,
        plan.coal_window, plan.eua_window,
    ) if selected_otf_session_date is not None else None
    complete = coverage.section_complete if coverage else {}
    complete_text = "Potrzebne dane są już kompletne"

    summary_rows = [
        {
            "Grupa danych": "Gaz — cena dzienna (RDN)",
            "Daty / zakres": format_date_range(plan.rdn_dates["gas_rdn"]),
        },
        {
            "Grupa danych": "Energia — TGeBase (historia)",
            "Daty / zakres": format_date_range(
                plan.rdn_dates["electricity_rdn"]
            ),
        },
        {
            "Grupa danych": "Energia — TGePeak, TGeOffpeak, TGe24",
            "Daty / zakres": (
                selected_report_date.strftime("%d.%m.%Y")
                if plan.rdn_dates["electricity_rdn"]
                else "Potrzebne dane są już kompletne"
            ),
        },
        {
            "Grupa danych": "Gaz i energia — kontrakty terminowe (OTF)",
            "Daty / zakres": (
                complete_text if complete.get("gas_otf") and complete.get("electricity_otf") else
                selected_otf_session_date.strftime("%d.%m.%Y")
                if selected_otf_session_date is not None else "Brak dostępnych dat"
            ),
        },
        {
            "Grupa danych": "Węgiel — historia",
            "Daty / zakres": complete_text if complete.get("coal") else format_date_range(
                get_dates_between(plan.coal_window[0] - timedelta(days=1), plan.coal_window[1])
            ),
        },
        {
            "Grupa danych": "EUA — historia uprawnień do emisji",
            "Daty / zakres": complete_text if complete.get("emissions") else format_date_range(
                get_dates_between(plan.eua_window[0] - timedelta(days=1), plan.eua_window[1])
            ),
        },
    ]
    st.subheader("Zakres danych do raportu")
    st.dataframe(summary_rows, hide_index=True, width="stretch")
    st.caption(
        "Dla RDN sprawdzamy ostatnie 30 dni i pobieramy maksymalnie 7 najnowszych brakujących dat. Część indeksów "
        "pobierana jest tylko dla najnowszej daty."
    )

    contract_rows = build_otf_contract_preview(candidate_dates)
    with st.expander("Podgląd kontraktów terminowych"):
        if not candidate_dates:
            st.caption("Brak dostępnych kontraktów do podglądu.")
        else:
            st.caption("Unikalne kontrakty z bieżącego zakresu — podgląd.")
        st.dataframe(contract_rows, hide_index=True, width="stretch")

    if not candidate_dates:
        st.warning("Brak dostępnych dat do sprawdzenia.")
    if st.button(
        "Potwierdź zakres i sprawdź dane",
        type="primary",
        key="confirm_table_dates",
        disabled=not candidate_dates,
    ):
        try:
            if selected_otf_session_date is None:
                raise ValueError("Wybierz datę sesji OTF.")
            confirm_dates(selected_otf_session_date, workbook_path)
        except ValueError as error:
            st.error(str(error))


def confirm_dates(
    selected_otf_date: date, workbook_path: Path | None = None
) -> None:
    import streamlit as st

    plan: DatePlan = st.session_state["date_plan"]
    otf_session_candidates = sorted(plan.otf_session_candidates, reverse=True)
    if not otf_session_candidates:
        raise ValueError("Brak dni roboczych do sprawdzenia dla tej daty raportu.")
    otf_session_date = validate_otf_session_choice(
        otf_session_candidates, selected_otf_date
    )
    for key in ("validation_report", "response", "parsed_response", "validated_payload", "validated_sections", "biomass_response", "biomass_added", "biomass_checked", "biomass_warnings", "biomass_tenders_updated"):
        st.session_state.pop(key, None)
    for key in list(st.session_state):
        if key.startswith("biomass_response_"):
            st.session_state.pop(key, None)
    st.session_state["data_saved"] = False
    st.session_state["otf_session_candidates"] = [otf_session_date]
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
        from exchange_rates import missing_exchange_rates
        st.session_state["review_existing_data"] = coverage.complete
        st.session_state["page"] = ("review" if missing_exchange_rates(workbook_path) else "biomass") if coverage.complete else "prompt"
    st.rerun()
