from datetime import date, timedelta
from pathlib import Path
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException
import streamlit as st

from date_stage import load_date_plan, show_date_selection
from exchange_rates import ensure_exchange_rates, warsaw_today
from prompt_stage import (
    load_prompt_template,
    show_prompt_page,
)
from review_stage import show_review_page
from ready_stage import show_ready_page


BASE_DIR  = Path(__file__).resolve().parent
WORKBOOK_PATH = BASE_DIR / "DataMaster.xlsx"
PROMPT_TEMPLATE_PATH = BASE_DIR / "prompt_market_data.txt"

st.set_page_config(
    page_title="Generator promptu — Rynek Energetyczny",
    page_icon="📈",
    layout="centered",
)


def initialize_session() -> None:
    try:
        fx_key = (warsaw_today(), WORKBOOK_PATH.stat().st_mtime_ns)
        if st.session_state.get("fx_sync_key") != fx_key:
            ensure_exchange_rates(WORKBOOK_PATH)
            st.session_state["fx_sync_key"] = (warsaw_today(), WORKBOOK_PATH.stat().st_mtime_ns)
        if "date_plan" in st.session_state:
            return
        report_date = st.session_state.setdefault(
            "report_date", date.today() - timedelta(days=1)
        )
        date_plan = load_date_plan(WORKBOOK_PATH, report_date + timedelta(days=1))
        prompt_template = load_prompt_template(PROMPT_TEMPLATE_PATH)
    except (
        BadZipFile,
        InvalidFileException,
        OSError,
        ValueError,
        KeyError,
    ) as error:
        st.error(f"Nie udało się przygotować listy dat lub promptu: {error}")
        st.stop()

    st.session_state["date_plan"] = date_plan
    st.session_state["prompt_template"] = prompt_template
    st.session_state.setdefault("page", "dates")


def show_workflow_progress() -> None:
    page = st.session_state["page"]
    steps = ("Wybierz daty", "Pobierz dane", "Sprawdź dane", "Gotowe")
    if page == "dates":
        active_step = 0
    elif page == "prompt":
        active_step = 1
    elif page == "review" and not st.session_state.get("data_saved"):
        active_step = 2
    else:
        active_step = 3

    if page == "ready":
        st.caption(
            "Dane dla wybranego zakresu są już w pliku, więc pobieranie i "
            "kontrolę pominięto."
        )
    else:
        st.caption(f"Krok {active_step + 1} z 4")

    columns = st.columns(len(steps))
    for index, (column, label) in enumerate(zip(columns, steps)):
        if page == "ready" and index in (1, 2):
            text = f"— {label}"
        elif index < active_step:
            text = f"✓ {label}"
        elif index == active_step:
            text = f"**{label}**"
        else:
            text = label
        column.markdown(text)


def main() -> None:
    initialize_session()
    show_workflow_progress()

    if st.session_state["page"] == "ready":
        show_ready_page(WORKBOOK_PATH)
    elif st.session_state["page"] == "review":
        show_review_page(WORKBOOK_PATH)
    elif st.session_state["page"] == "prompt":
        show_prompt_page(WORKBOOK_PATH)
    else:
        show_date_selection(WORKBOOK_PATH)


if __name__ == "__main__":
    main()
