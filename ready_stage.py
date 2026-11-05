from pathlib import Path
from tempfile import TemporaryDirectory

from generate_market_dashboard import render_dashboard

from review_stage import build_dashboard_preview
from preview_tables import show_market_tables
from workbook_access import show_workbook_access_error
from report_pdf import generate_report_pdf, PdfGenerationError


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

    st.title("Gotowe")
    if st.session_state.get("data_saved"):
        st.info("Dane zapisano w pliku DataMaster.xlsx.")
    else:
        st.info("Dane dla wybranego raportu znajdują się już w pliku DataMaster.xlsx.")
    try:
        with TemporaryDirectory() as directory:
            output = render_dashboard(
                workbook_path, output_path=Path(directory) / "dashboard.html",
                report_date=st.session_state["report_date"],
            )
            dashboard_html = output.read_bytes()
    except PermissionError:
        show_workbook_access_error()
    except (OSError, ValueError, KeyError) as error:
        st.error(f"Nie udało się przygotować dashboardu: {error}")
    else:
        st.success("Dashboard jest gotowy do pobrania.")
        filename = f"raport energetyczny {st.session_state['report_date'].isoformat()}"
        html_column, pdf_column = st.columns(2)
        html_column.download_button(
            "Pobierz dashboard HTML", data=dashboard_html,
            file_name=f"{filename}.html", mime="text/html", type="primary",
        )
        try:
            with st.spinner("Przygotowywanie PDF…"):
                pdf = generate_report_pdf(dashboard_html.decode("utf-8"))
        except PdfGenerationError as error:
            pdf_column.button("Pobierz PDF", disabled=True)
            st.warning(str(error))
        else:
            pdf_column.download_button(
                "Pobierz PDF", data=pdf, file_name=f"{filename}.pdf",
                mime="application/pdf", type="primary",
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
        st.subheader("Podgląd zapisanych danych")
        show_market_tables(rows)

    if st.button("Wróć do wyboru dat"):
        st.session_state["page"] = "dates"
        st.rerun()
