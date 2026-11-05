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
from biomass_stage import show_biomass_page
from workbook_access import show_workbook_access_error


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
    except PermissionError:
        show_workbook_access_error()
        if st.button("Spróbuj ponownie", key="retry_workbook"):
            st.rerun()
        st.stop()
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
    steps = ("Wybierz daty", "Pobierz dane", "Sprawdź dane", "Dane o zrębkach", "Gotowe")
    if page == "dates":
        active_step = 0
    elif page == "prompt":
        active_step = 1
    elif page == "review" and not st.session_state.get("data_saved"):
        active_step = 2
    elif page == "biomass":
        active_step = 3
    else:
        active_step = 4

    st.markdown(f"### Krok {active_step + 1} z {len(steps)} — {steps[active_step]}")
    cards = []
    for index, label in enumerate(steps):
        skipped = page in ("biomass", "ready") and not st.session_state.get("data_saved") and index in (1, 2)
        current = index == active_step
        status = "Teraz" if current else "Pominięto" if skipped else "Ukończono" if index < active_step else "Przed Tobą"
        marker = str(index + 1) if index >= active_step or skipped else "✓"
        background = "#1763a6" if current else "var(--secondary-background-color, #f2f4f7)"
        color = "#ffffff" if current else "var(--text-color, #475569)"
        outline = "2px solid #1763a6" if current else "1px solid #8894a344"
        aria = ' aria-current="step"' if current else ""
        cards.append(
            f'<li{aria} style="list-style:none;flex:1;min-width:115px;padding:12px;'
            f'border-radius:10px;border:{outline};background:{background};color:{color}">'
            f'<span style="font-size:12px;opacity:.85">{marker} · {status}</span><br>'
            f'<strong style="font-size:15px">{label}</strong></li>'
        )
    st.markdown(
        '<nav aria-label="Etapy przygotowania raportu"><ol style="display:flex;flex-wrap:wrap;'
        'gap:8px;margin:0 0 16px;padding:0">' + "".join(cards) + '</ol></nav>',
        unsafe_allow_html=True,
    )
    if page == "ready":
        if st.session_state.get("data_saved"):
            st.caption("Dane zostały zapisane. Możesz pobrać raport lub wrócić do wyboru dat.")
        else:
            st.caption("Dane energetyczne są już dostępne — ich pobieranie i kontrolę pominięto. Możesz pobrać raport lub wrócić do wyboru dat.")

    report_day = st.session_state["report_date"]
    plan = st.session_state["date_plan"]
    if page == "dates":
        otf_day = st.session_state.get("selected_otf_session_date", next(iter(plan.otf_session_candidates), None))
    else:
        otf_day = st.session_state.get("otf_session_date")
    with st.container(border=True):
        left, right = st.columns(2)
        left.markdown(f"**Dane na dzień:** {report_day.strftime('%d.%m.%Y')}")
        right.markdown(f"**Sesja OTF:** {otf_day.strftime('%d.%m.%Y') if otf_day else 'Nie wybrano'}")


def scroll_to_top_on_stage_change() -> None:
    page = st.session_state["page"]
    if st.session_state.get("last_scroll_page") == page:
        return
    st.session_state["last_scroll_page"] = page
    render_iframe = getattr(st, "iframe", None)
    if render_iframe is None:
        from streamlit.components.v1 import html
        render_iframe = html
    render_iframe(f"<!-- stage: {page} -->" + """<script>
      const resetScroll = () => {
        try {
          const doc = window.parent.document;
          const main = doc.querySelector('[data-testid="stMain"]') || doc.querySelector('section.main');
          if (main) main.scrollTo({top:0,behavior:'instant'});
          window.parent.scrollTo({top:0,behavior:'instant'});
        } catch (_) { window.scrollTo(0,0); }
      };
      resetScroll(); setTimeout(resetScroll,150); setTimeout(resetScroll,400);
    </script>""", height=1)


def main() -> None:
    initialize_session()
    show_workflow_progress()

    scroll_to_top_on_stage_change()
    try:
        if st.session_state["page"] == "ready":
            show_ready_page(WORKBOOK_PATH)
        elif st.session_state["page"] == "biomass":
            show_biomass_page(WORKBOOK_PATH)
        elif st.session_state["page"] == "review":
            show_review_page(WORKBOOK_PATH)
        elif st.session_state["page"] == "prompt":
            show_prompt_page(WORKBOOK_PATH)
        else:
            show_date_selection(WORKBOOK_PATH)
    except PermissionError:
        show_workbook_access_error()
        st.button("Spróbuj ponownie", key="retry_workbook_page")


if __name__ == "__main__":
    main()
