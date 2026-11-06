from datetime import date
import json
from pathlib import Path

from biomass_data import read_transactions, search_context, save_biomass_data, read_tenders
from workbook_access import show_workbook_access_error
from biomass_import import merge_responses

ROOT = Path(__file__).resolve().parent


def build_biomass_prompt(path: Path, report_date: date) -> tuple[str, date]:
    start, _ = search_context(read_transactions(path), report_date)
    sources = (ROOT / "prompt_biomass_sources.txt").read_text(encoding="utf-8")
    sources = "\n".join(line for line in sources.splitlines() if line.strip() and not line.lstrip().startswith('#'))
    prompt = (ROOT / "prompt_biomass.txt").read_text(encoding="utf-8")
    replacements = {
        "{{start_date}}": start.isoformat(), "{{end_date}}": report_date.isoformat(),
        "{{example_sources}}": sources or "Nie wskazano — samodzielnie wyszukaj wiarygodne źródła.",
        "{{open_tenders}}": json.dumps(read_tenders(path, report_date, open_only=True), ensure_ascii=False, indent=2, default=str),
        "{{existing_records}}": json.dumps([r for r in read_transactions(path) if date.fromisoformat(r["date"]) <= report_date], ensure_ascii=False, indent=2, default=str),
    }
    for placeholder, value in replacements.items():
        prompt = prompt.replace(placeholder, value)
    return prompt, start


def show_biomass_page(path: Path) -> None:
    import streamlit as st

    st.title("Dane o zrębkach")
    st.write("1. Otwórz ChatGPT i rozpocznij nową rozmowę z dostępem do wyszukiwania w internecie.")
    st.markdown("[Otwórz ChatGPT — https://chatgpt.com/](https://chatgpt.com/)")
    st.write("2. Skopiuj poniższy prompt. Możesz uruchomić go w kilku osobnych czatach — niezależne wyszukiwania mogą dać lepszy wynik.")
    st.write("3. Wklej odpowiedzi do osobnych pól. Aplikacja połączy dane, usunie duplikaty i sprawdzi terminy ofert.")
    try:
        prompt, _ = build_biomass_prompt(path, st.session_state["report_date"])
    except PermissionError:
        show_workbook_access_error()
        st.button("Spróbuj ponownie", key="biomass_retry_read")
        return
    except (OSError, ValueError) as error:
        st.error(f"Nie udało się przygotować danych o zrębkach: {error}")
        return
    st.subheader("Prompt do skopiowania")
    st.code(prompt, language=None, height=350)
    st.subheader("Odpowiedzi z ChatGPT")
    count = st.session_state.setdefault("biomass_response_count", 1)
    texts = []
    for index in range(count):
        key = "biomass_response" if index == 0 else f"biomass_response_{index}"
        texts.append(st.text_area(f"Odpowiedź {index+1} — pełny JSON", height=220, key=key))
    if st.button("Dodaj kolejne pole na odpowiedź", key="biomass_add_response"):
        st.session_state["biomass_response_count"] = count + 1
        st.rerun()
    submitted = st.button("Sprawdź odpowiedź i kontynuuj", type="primary")
    if submitted:
        if not any(text.strip() for text in texts):
            st.error("Wklej przynajmniej jedną odpowiedź lub wybierz przycisk braku nowych danych.")
            return
        report = merge_responses(texts, st.session_state["report_date"], read_tenders(path, st.session_state["report_date"]))
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
