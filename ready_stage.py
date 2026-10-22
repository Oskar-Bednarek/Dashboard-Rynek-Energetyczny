from pathlib import Path
from review_stage import build_dashboard_preview

def show_ready_page(workbook_path: Path) -> None:
    import streamlit as st
    st.title("Dane gotowe do przygotowania dashboardu")
    st.success("Data Master zawiera wszystkie dane wymagane dla wybranej daty raportu.")
    rows = build_dashboard_preview(workbook_path, {"data": {}}, st.session_state["coal_window"], st.session_state["otf_session_date"])
    display = [{k: (str(v) if k == "change_pct" and v is not None else v) for k, v in row.items()} for row in rows]
    st.dataframe(display, hide_index=True, width="stretch")
    st.button("Generuj dashboard", disabled=True, help="Generator dashboardu będzie następnym etapem.")
    if st.button("Wróć do wyboru dat"):
        st.session_state["page"] = "dates"
        st.rerun()
