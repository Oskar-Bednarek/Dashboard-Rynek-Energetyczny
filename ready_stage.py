from pathlib import Path

from review_stage import build_dashboard_preview


_COVERAGE_LABELS = {
    "gas_rdn": "Ceny dzienne gazu",
    "electricity_rdn": "Ceny dzienne energii",
    "gas_otf": "Kontrakty terminowe na gaz",
    "electricity_otf": "Kontrakty terminowe na energię",
    "coal": "Węgiel",
    "emissions": "Uprawnienia do emisji EUA",
}


def show_ready_page(workbook_path: Path) -> None:
    import streamlit as st

    st.title("Dane są już dostępne")
    st.success(
        "Wszystkie wymagane dane dla wybranego raportu znajdują się już "
        "w pliku DataMaster.xlsx."
    )
    coverage = st.session_state.get("coverage_result")
    if coverage is not None:
        st.subheader("Sprawdzenie zawartości")
        st.dataframe(
            [
                {
                    "Dane": _COVERAGE_LABELS[key],
                    "Stan": value,
                }
                for key, value in coverage.details.items()
            ],
            hide_index=True,
            width="stretch",
        )

    rows = build_dashboard_preview(
        workbook_path,
        {"data": {}},
        st.session_state["coal_window"],
        st.session_state["otf_session_date"],
    )
    if rows:
        display = [
            {
                key: (str(value) if key == "change_pct" and value is not None else value)
                for key, value in row.items()
            }
            for row in rows
        ]
        st.subheader("Podgląd zapisanych danych")
        st.dataframe(display, hide_index=True, width="stretch")

    st.info(
        "Tworzenie dashboardu nie jest jeszcze dostępne. Możesz jednak przejść "
        "przez pobieranie i kontrolę, jeśli chcesz odświeżyć lub sprawdzić dane."
    )
    if st.button("Przejdź do pobierania i kontroli", type="primary"):
        st.session_state["page"] = "prompt"
        st.session_state["data_saved"] = False
        st.rerun()
    if st.button("Wróć do wyboru dat"):
        st.session_state["page"] = "dates"
        st.rerun()
