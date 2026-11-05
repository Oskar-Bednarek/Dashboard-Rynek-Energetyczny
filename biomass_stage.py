from datetime import date
import json
from pathlib import Path

from biomass_data import read_transactions, search_context, validate_response, save_biomass_data, read_tenders
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
        "{{open_tenders}}": json.dumps(read_tenders(path, report_date, open_only=True), ensure_ascii=False, indent=2, default=str),
        "{{existing_records}}": json.dumps(existing, ensure_ascii=False, indent=2, default=str),
    }
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt, start


def show_biomass_page(path: Path) -> None:
    import streamlit as st

    st.title("Dane o zrębkach")
    st.write("Skopiuj osobny prompt do nowej rozmowy AI. Po zakończeniu wyszukiwania wklej pełną odpowiedź poniżej.")
    try:
        prompt, start = build_biomass_prompt(path, st.session_state["report_date"])
    except PermissionError:
        show_workbook_access_error()
        st.button("Spróbuj ponownie", key="biomass_retry_read")
        return
    except (OSError, ValueError) as error:
        st.error(f"Nie udało się przygotować danych o zrębkach: {error}")
        return
    st.subheader("Prompt do skopiowania")
    st.code(prompt, language=None, height=350)
    st.subheader("Odpowiedź")
    with st.form("biomass_response_form"):
        text = st.text_area("Pełna odpowiedź dotycząca zrębków", height=250, key="biomass_response")
        submitted = st.form_submit_button("Sprawdź odpowiedź i kontynuuj", type="primary")
    if submitted:
        report = validate_response(text, start, st.session_state["report_date"], read_tenders(path, st.session_state["report_date"], open_only=True))
        if not report.is_valid:
            st.error("Odpowiedź wymaga poprawy. Dane nie zostały zapisane.")
            for error in report.errors:
                st.write(error)
        else:
            try:
                added, updated = save_biomass_data(path, report.records, report.tenders) if report.records or report.tenders else (0, 0)
            except PermissionError:
                show_workbook_access_error()
            except (OSError, ValueError) as error:
                st.error(f"Nie udało się zapisać transakcji zrębków: {error}")
            else:
                st.session_state["biomass_warnings"] = report.warnings
                st.session_state["biomass_added"] = added
                st.session_state["biomass_tenders_updated"] = updated
                st.session_state["biomass_checked"] = True
                st.session_state["page"] = "ready"
                st.rerun()
    st.caption("Jeśli model nie znalazł nowych transakcji, przetargów ani zmian statusu, nie musisz wklejać pustej odpowiedzi. Jeśli zwrócił aktualizacje przetargów, wklej odpowiedź.")
    if st.button("Model nie znalazł nowych danych ani zmian"):
        st.session_state["biomass_warnings"] = []
        st.session_state["biomass_added"] = 0
        st.session_state["biomass_tenders_updated"] = 0
        st.session_state["biomass_checked"] = True
        st.session_state["page"] = "ready"
        st.rerun()
    if st.button("Wróć do wyboru dat", key="biomass_back_dates"):
        st.session_state["page"] = "dates"
        st.rerun()
