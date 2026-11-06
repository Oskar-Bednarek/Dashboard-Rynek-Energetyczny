"""Readable market previews shared by the review and completed-report screens."""
from datetime import date, datetime
from typing import Any

MARKETS = {
    "gas.day_ahead": ("Gaz — rynek dnia następnego", {
        "price_pln_mwh": "Cena (PLN/MWh)", "volume_mwh": "Wolumen (MWh)", "change_pct": "Zmiana (%)",
    }),
    "gas.futures": ("Gaz — kontrakty terminowe", {
        "dkr_pln_mwh": "Kurs rozliczeniowy (PLN/MWh)", "max_pln_mwh": "Kurs maksymalny (PLN/MWh)", "volume_mwh": "Wolumen (MWh)",
    }),
    "electricity.day_ahead": ("Energia elektryczna — rynek dnia następnego", {
        "price_pln_mwh": "Cena (PLN/MWh)", "volume_mwh": "Wolumen (MWh)", "change_pct": "Zmiana (%)",
    }),
    "electricity.futures": ("Energia elektryczna — kontrakty terminowe", {
        "dkr_pln_mwh": "Kurs rozliczeniowy (PLN/MWh)", "max_pln_mwh": "Kurs maksymalny (PLN/MWh)", "volume_mwh": "Wolumen (MWh)",
    }),
    "coal.futures": ("Węgiel — notowania", {
        "price": "Cena (USD/t)", "open": "Otwarcie (USD/t)", "high": "Maksimum (USD/t)", "low": "Minimum (USD/t)", "volume": "Wolumen", "change_pct": "Zmiana (%)",
    }),
    "emissions.futures": ("EUA — notowania", {
        "price": "Cena (EUR/t)", "open": "Otwarcie (EUR/t)", "high": "Maksimum (EUR/t)", "low": "Minimum (EUR/t)", "volume": "Wolumen", "change_pct": "Zmiana (%)",
    }),
}


def _display(value: Any) -> str:
    if value is None or value == "":
        return "—"
    if isinstance(value, (float, int)) and not isinstance(value, bool):
        return f"{value:,.2f}".rstrip("0").rstrip(".").replace(",", " ").replace(".", ",")
    return str(value)


def group_preview_rows(rows: list[dict]) -> dict[str, list[dict]]:
    result = {key: [] for key in MARKETS}
    for row in rows:
        section = row.get("sekcja")
        if section not in MARKETS:
            continue
        raw_date = row.get("data")
        try:
            parsed = raw_date.date() if isinstance(raw_date, datetime) else (
                raw_date if isinstance(raw_date, date) else date.fromisoformat(str(raw_date)[:10])
            )
            display_date = parsed.strftime("%d.%m.%Y")
        except ValueError:
            display_date = _display(raw_date)
        display = {"Data": display_date, "Instrument": _display(row.get("instrument"))}
        display.update({label: _display(row.get(field)) for field, label in MARKETS[section][1].items()})
        display["Źródło"] = row.get("source_url")
        result[section].append(display)
    return result


def show_market_tables(rows: list[dict]) -> None:
    import streamlit as st

    st.caption("Dane podzielono według rynku. Ceny węgla i EUA są tu w walutach źródłowych; dashboard przelicza je na PLN.")
    for section, records in group_preview_rows(rows).items():
        st.subheader(MARKETS[section][0])
        if not records:
            st.caption("Brak danych w wybranym zakresie.")
            continue
        st.dataframe(
            records, hide_index=True, width="stretch",
            column_config={"Źródło": st.column_config.LinkColumn("Źródło")},
        )
