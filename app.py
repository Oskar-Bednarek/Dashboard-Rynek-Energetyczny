from datetime import date, timedelta
from pathlib import Path
from zipfile import BadZipFile

from openpyxl.utils.exceptions import InvalidFileException
import streamlit as st

from date_stage import load_date_plan, show_date_selection
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
    if "date_plan" in st.session_state:
        return

    try:
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


def main() -> None:
    initialize_session()

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
