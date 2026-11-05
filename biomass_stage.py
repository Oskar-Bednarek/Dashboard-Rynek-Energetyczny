from datetime import date
import json
from pathlib import Path

from biomass_data import read_transactions, search_context, validate_response, save_transactions
from workbook_access import show_workbook_access_error

ROOT = Path(__file__).resolve().parent


def build_biomass_prompt(path: Path, report_date: date) -> tuple[str, date]:
    start, existing = search_context(read_transactions(path), report_date)
    sources = (ROOT / "prompt_biomass_sources.txt").read_text(encoding="utf-8")
    sources = "\n".join(line for line in sources.splitlines() if line.strip() and not line.lstrip().startswith('#'))
    prompt = (ROOT / "prompt_biomass.txt").read_text(encoding="utf-8")
    replacements = {
        "{{start_date}}": start.isoformat(), "{{end_date}}": report_date.isoformat(),
        "{{example_sources}}": sources or "Nie wskazano — samodzielnie wyszukaj wiarygodne źródła.",
        "{{existing_records}}": json.dumps(existing, ensure_ascii=False, indent=2, default=str),
    }
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt, start


def show_biomass_page(path: Path) -> None:
    import streamlit as st

    st.title("Dane o zrębkach")
    st.write("Skopiuj osobny prompt do nowej rozmowy AI. Po zakończeniu wyszukiwania wklej pełną odpowiedź poniżej.")
    prompt, start = build_biomass_prompt(path, st.session_state["report_date"])
    st.subheader("Prompt do skopiowania")
    st.code(prompt, language=None, height=350)
    st.subheader("Odpowiedź")
    with st.form("biomass_response_form"):
        text = st.text_area("Pełna odpowiedź dotycząca zrębków", height=250, key="biomass_response")
        submitted = st.form_submit_button("Sprawdź odpowiedź i kontynuuj", type="primary")
    if submitted:
        report = validate_response(text, start, st.session_state["report_date"])
        if not report.is_valid:
            st.error("Odpowiedź wymaga poprawy. Dane nie zostały zapisane.")
            for error in report.errors:
                st.write(error)
        else:
            try:
                added = save_transactions(path, report.records) if report.records else 0
            except PermissionError:
                show_workbook_access_error()
            except (OSError, ValueError) as error:
                st.error(f"Nie udało się zapisać transakcji zrębków: {error}")
            else:
                st.session_state["biomass_warnings"] = report.warnings
                st.session_state["biomass_added"] = added
                st.session_state["biomass_checked"] = True
                st.session_state["page"] = "ready"
                st.rerun()
    st.caption("Jeśli model zakończył wyszukiwanie i nie znalazł nowych transakcji, nie musisz wklejać pustej odpowiedzi.")
    if st.button("Model nie znalazł nowych transakcji"):
        st.session_state["biomass_warnings"] = []
        st.session_state["biomass_added"] = 0
        st.session_state["biomass_checked"] = True
        st.session_state["page"] = "ready"
        st.rerun()
    if st.button("Wróć do wyboru dat", key="biomass_back_dates"):
        st.session_state["page"] = "dates"
        st.rerun()
