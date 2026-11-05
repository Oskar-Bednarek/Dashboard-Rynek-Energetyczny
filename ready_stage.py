from pathlib import Path
from tempfile import TemporaryDirectory

from generate_market_dashboard import render_dashboard

from review_stage import build_dashboard_preview
from preview_tables import show_market_tables
from workbook_access import show_workbook_access_error
from report_pdf import generate_report_pdf, PdfGenerationError
from biomass_data import read_transactions, as_date, read_tenders


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


    if st.session_state.get("biomass_checked"):
        st.caption(f"Zrębki: nowe transakcje — {st.session_state.get('biomass_added', 0)}, zapisane aktualizacje przetargów — {st.session_state.get('biomass_tenders_updated', 0)}.")
    for message in st.session_state.get("biomass_warnings", []):
        st.warning(f"Wyszukiwanie zrębków — uwaga ze źródła: {message}")
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

    st.subheader("Zrębki drzewne — transakcje i wyniki przetargów")
    transactions = [row for row in read_transactions(workbook_path) if as_date(row["date"]) <= st.session_state["report_date"]]
    if transactions:
        st.dataframe([
            {"Data": as_date(row["date"]).strftime("%d.%m.%Y"), "Nabywca": row["buyer"] or "—",
             "Rodzaj": row["kind"], "Cena (PLN/t)": row["price_pln_t"],
             "VAT": {"net":"Netto","gross":"Brutto","unknown":"Nie podano"}[row["price_basis"]],
             "Wolumen (t)": row["volume_t"], "Źródło": row["source_url"],
             "Typ": "Wynik przetargu" if row["record_type"] == "tender_award" else "Transakcja"}
            for row in sorted(transactions, key=lambda r:r["date"], reverse=True)
        ], hide_index=True, width="stretch", column_config={"Źródło":st.column_config.LinkColumn("Źródło")})
    else:
        st.caption("Brak zapisanych transakcji zrębków do wybranej daty.")

    st.subheader("Zrębki drzewne — monitorowane przetargi")
    tenders = read_tenders(workbook_path, st.session_state["report_date"])
    if tenders:
        labels = {"open":"Otwarty", "awarded":"Rozstrzygnięty", "cancelled":"Unieważniony", "closed_without_result":"Zakończony bez wyniku"}
        st.dataframe([
            {"Zamawiający": r["buyer"] or "—", "Postępowanie": r["reference"] or "—",
             "Rodzaj": r["kind"], "Status": labels[r["status"]],
             "Termin ofert": r["deadline"] or "—", "Data statusu": r["status_date"],
             "Sprawdzono dla dnia": r["checked_as_of"], "Źródło": r["source_url"]}
            for r in tenders
        ], hide_index=True, width="stretch", column_config={"Źródło":st.column_config.LinkColumn("Źródło")})
    else:
        st.caption("Brak zapisanych przetargów do monitorowania.")

    if st.button("Wróć do wyboru dat"):
        st.session_state["page"] = "dates"
        st.rerun()
