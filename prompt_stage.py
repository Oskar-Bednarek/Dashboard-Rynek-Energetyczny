from datetime import date, timedelta
from pathlib import Path

import streamlit as st


LINK_LIST_PLACEHOLDERS = {
    "{{linki RDN GAZ}}": "gas_rdn_all",
    "{{linki OTF GAZ}}": "gas_otf_selected",
    "{{linki RDN ENERGIA}}": "electricity_rdn_all",
    "{{linki OTF ENERGIA}}": "electricity_otf_selected",
}


def load_prompt_template(template_path: Path) -> str:
    return template_path.read_text(encoding="utf-8")


def build_prompt_replacements(
    full_dates: list[date],
    selected_dates: list[date],
    today: date,
) -> dict[str, str]:
    link_lists = build_link_lists(full_dates, selected_dates)
    replacements = {
        placeholder: link_lists[list_name]
        for placeholder, list_name in LINK_LIST_PLACEHOLDERS.items()
    }
    replacements["{{data dzisiejsza}}"] = today.strftime("%d-%m-%Y")
    replacements["{{ostatnia data}}"] = (today - timedelta(days=1)).strftime(
        "%d-%m-%Y"
    )
    return replacements


def build_prompt(
    template: str,
    full_dates: list[date],
    selected_dates: list[date],
    today: date | None = None,
) -> str:
    current_date = today or date.today()
    latest_trading_date = current_date - timedelta(days=1)
    prompt = template.replace(
        "14-10-2026",
        latest_trading_date.strftime("%d-%m-%Y"),
    )
    replacements = build_prompt_replacements(
        full_dates=full_dates,
        selected_dates=selected_dates,
        today=current_date,
    )
    for placeholder, replacement in replacements.items():
        prompt = prompt.replace(placeholder, replacement)
    return prompt


def build_link_list(base_url: str, dates: list[date]) -> str:
    return "\n\n".join(
        f"dane na {trading_date.strftime('%d-%m-%Y')}:\n"
        f"{base_url}{trading_date.strftime('%d-%m-%Y')}"
        for trading_date in dates
    )


def build_link_lists(
    full_dates: list[date],
    selected_dates: list[date],
) -> dict[str, str]:
    return {
        "gas_rdn_all": build_link_list(
            "https://tge.pl/gaz-rdn?dateShow=",
            full_dates,
        ),
        "gas_otf_selected": build_link_list(
            "https://tge.pl/gaz-otf?dateShow=",
            selected_dates,
        ),
        "electricity_rdn_all": build_link_list(
            "https://tge.pl/energia-elektryczna-rdn?dateShow=",
            full_dates,
        ),
        "electricity_otf_selected": build_link_list(
            "https://tge.pl/energia-elektryczna-otf?dateShow=",
            selected_dates,
        ),
    }


def show_prompt_page() -> None:
    st.title("Prompt i odpowiedź")
    confirmed_dates = st.session_state["confirmed_dates"]
    full_dates = st.session_state["candidate_dates"]

    st.success(
        f"Potwierdzono {len(confirmed_dates)} dat niebędących świętami."
    )
    with st.expander("Daty przekazane do promptu"):
        st.write(
            [value.strftime("%Y-%m-%d") for value in confirmed_dates]
        )
    with st.expander("Wszystkie dni robocze w zakresie"):
        st.write([value.strftime("%Y-%m-%d") for value in full_dates])

    prompt = build_prompt(
        st.session_state["prompt_template"],
        full_dates,
        confirmed_dates,
    )
    with st.expander("Dostępne znaczniki w szablonie promptu"):
        st.code(
            "\n".join(
                (
                    *LINK_LIST_PLACEHOLDERS,
                    "{{data dzisiejsza}}",
                    "{{ostatnia data}}",
                )
            ),
            language=None,
        )
        st.caption(
            "Wstaw wybrane znaczniki do pliku prompt_template.txt. "
            "Zostaną zastąpione przy generowaniu promptu."
        )

    st.subheader("Prompt do skopiowania")
    st.caption("Użyj ikony kopiowania widocznej przy bloku promptu.")
    st.code(prompt, language=None)

    st.subheader("Odpowiedź")
    with st.form("response_form"):
        response = st.text_area(
            "Wklej tutaj odpowiedź otrzymaną na powyższy prompt",
            value=st.session_state.get("response", ""),
            height=300,
        )
        save_response = st.form_submit_button("Zapisz odpowiedź")

    if save_response:
        if not response.strip():
            st.warning("Wklej odpowiedź przed jej zapisaniem.")
        else:
            st.session_state["response"] = response
            st.success("Odpowiedź została zapisana w bieżącej sesji.")

    if st.button("Wróć do weryfikacji dat"):
        st.session_state.pop("holiday_date_table", None)
        st.session_state["page"] = "dates"
        st.rerun()
