from datetime import date, datetime, timedelta
from pathlib import Path

from openpyxl import load_workbook
import streamlit as st


WEEKDAY_NAMES = (
    "poniedziałek",
    "wtorek",
    "środa",
    "czwartek",
    "piątek",
    "sobota",
    "niedziela",
)


def get_first_trading_date(workbook_path: Path) -> date:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        if "GAZ_RDN" not in workbook.sheetnames:
            raise ValueError("W pliku DataMaster.xlsx nie znaleziono arkusza GAZ_RDN.")

        worksheet = workbook["GAZ_RDN"]
        headers = next(
            worksheet.iter_rows(min_row=1, max_row=1, values_only=True),
            None,
        )
        if headers is None or "trading_date" not in headers:
            raise ValueError(
                "W arkuszu GAZ_RDN nie znaleziono kolumny trading_date."
            )

        date_column = headers.index("trading_date") + 1
        trading_dates: list[date] = []
        for (value,) in worksheet.iter_rows(
            min_row=2,
            min_col=date_column,
            max_col=date_column,
            values_only=True,
        ):
            if isinstance(value, datetime):
                trading_dates.append(value.date())
            elif isinstance(value, date):
                trading_dates.append(value)
            elif isinstance(value, str) and value.strip():
                trading_dates.append(date.fromisoformat(value[:10]))
            elif value is not None:
                raise ValueError(
                    f"Nieprawidłowa data w kolumnie trading_date: {value!r}."
                )

        if not trading_dates:
            raise ValueError("Kolumna trading_date w arkuszu GAZ_OTF jest pusta.")
        return min(trading_dates)
    finally:
        workbook.close()


def get_candidate_dates(first_trading_date: date, today: date) -> list[date]:
    next_date = first_trading_date + timedelta(days=1)
    last_date = today - timedelta(days=1)
    dates: list[date] = []
    while next_date <= last_date:
        if next_date.weekday() < 5:
            dates.append(next_date)
        next_date += timedelta(days=1)
    return dates


def load_candidate_dates(workbook_path: Path, today: date) -> list[date]:
    first_trading_date = get_first_trading_date(workbook_path)
    return get_candidate_dates(first_trading_date, today)


def show_date_selection() -> None:
    st.title("Weryfikacja dat sesji giełdowych")
    st.write(
        "Sprawdź daty i dni tygodnia odczytane z arkusza `GAZ_RDN`. "
        "Zaznacz pole „Święto” przy datach, w które giełda była zamknięta."
    )

    candidate_dates = st.session_state["candidate_dates"]
    selected_holidays = set(st.session_state.get("selected_holidays", []))
    edited_dates = st.data_editor(
        [
            {
                "Date": (
                    f"{trading_date.isoformat()} "
                    f"{WEEKDAY_NAMES[trading_date.weekday()].capitalize()}"
                ),
                "Holiday": trading_date in selected_holidays,
            }
            for trading_date in candidate_dates
        ],
        hide_index=True,
        disabled=["Date"],
        column_config={
            "Date": st.column_config.TextColumn(
                "Data", width="medium", help="Data wraz z dniem tygodnia."
            ),
            "Holiday": st.column_config.CheckboxColumn(
                "Święto", help="Zaznacz, jeśli giełda była zamknięta."
            ),
        },
        key="holiday_date_table",
    )
    if st.button("Potwierdź daty", type="primary", key="confirm_table_dates"):
        holidays = [
            date.fromisoformat(row["Date"].split()[0])
            for row in edited_dates
            if row["Holiday"]
        ]
        confirm_dates(holidays)


def confirm_dates(holidays: list[date]) -> None:
    holiday_set = set(holidays)
    st.session_state["selected_holidays"] = holidays
    st.session_state["confirmed_dates"] = [
        value
        for value in st.session_state["candidate_dates"]
        if value not in holiday_set
    ]
    st.session_state["page"] = "prompt"
    st.rerun()
