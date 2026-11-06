from workbook_storage import atomic_save, serialized_update
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


SHEET_SPECS = {
    "gas.day_ahead": ("GAZ_RDN", ("price_pln_mwh", "volume_mwh", "change_pct")),
    "gas.futures": ("GAZ_OTF", ("dkr_pln_mwh", "max_pln_mwh", "volume_mwh")),
    "electricity.day_ahead": ("EE_RDN", ("price_pln_mwh", "volume_mwh", "change_pct")),
    "electricity.futures": ("EE_OTF", ("dkr_pln_mwh", "max_pln_mwh", "volume_mwh")),
    "coal.futures": ("WEGIEL", ("price", "open", "high", "low", "volume", "change_pct")),
    "emissions.futures": ("EUA", ("price", "open", "high", "low", "volume", "change_pct")),
}


def _records(payload: dict[str, Any], section: str) -> list[dict[str, Any]]:
    market, collection = section.split(".")
    return payload["data"][market][collection]


def _upsert_sheet(
    worksheet,
    records: list[dict[str, Any]],
    value_fields: tuple[str, ...],
    retrieved_at: str,
    *, preserve_unchanged: bool = False,
) -> bool:
    headers = [cell.value for cell in worksheet[1]]
    expected = ["trading_date", "data_id", "source_url", "instrument", *value_fields, "retrieved_at"]
    if headers != expected:
        raise ValueError(
            f"Arkusz {worksheet.title} ma nieoczekiwane kolumny: {headers!r}."
        )
    existing: dict[tuple[str, str], int] = {}
    last_data_row = 1
    for row in range(2, worksheet.max_row + 1):
        trading_date = worksheet.cell(row, 1).value
        if hasattr(trading_date, "isoformat"):
            trading_date = trading_date.isoformat()[:10]
        data_id = worksheet.cell(row, 2).value
        if trading_date and data_id:
            existing[(str(trading_date)[:10], str(data_id))] = row
            last_data_row = max(last_data_row, row)
    changed = False
    for record in records:
        key = (record["trading_date"], record["data_id"])
        row = existing.get(key, last_data_row + 1)
        values = record["values"]
        output = [
            record["trading_date"], record["data_id"], record["source_url"],
            record["instrument"], *(values.get(field) for field in value_fields), retrieved_at,
        ]
        if preserve_unchanged and key in existing:
            current = [worksheet.cell(row, column).value for column in range(1, len(output))]
            current[0] = current[0].isoformat()[:10] if hasattr(current[0], "isoformat") else str(current[0])[:10]
            if current[:4] == output[:4] and all(
                _same_number(old, new) for old, new in zip(current[4:], output[4:-1])
            ):
                continue
        changed = True
        for column, value in enumerate(output, 1):
            worksheet.cell(row, column).value = value
        existing[key] = row
        last_data_row = max(last_data_row, row)
    return changed


def _same_number(old, new) -> bool:
    if old == new:
        return True
    if old is None or new is None:
        return False
    def number(value):
        text = str(value).strip().replace(" ", "").replace("\xa0", "")
        multiplier = Decimal(1)
        if text.lower().endswith(("k", "m")):
            multiplier = Decimal(1000 if text[-1].lower() == "k" else 1000000)
            text = text[:-1]
        return Decimal(text.rstrip("%").replace(",", ".")) * multiplier
    try:
        return number(old) == number(new)
    except InvalidOperation:
        return False


@serialized_update
def save_market_data(
    workbook_path: Path,
    payload: dict[str, Any],
    coal_window: tuple[date, date],
    eua_window: tuple[date, date],
) -> None:
    workbook = load_workbook(workbook_path)
    try:
        retrieved_at = payload.get("retrieved_at") or datetime.now().astimezone().isoformat()
        changed = False
        for section, (sheet_name, fields) in SHEET_SPECS.items():
            if sheet_name not in workbook.sheetnames:
                raise ValueError(f"Brak arkusza {sheet_name} w DataMaster.xlsx.")
            worksheet = workbook[sheet_name]
            changed |= _upsert_sheet(
                worksheet, _records(payload, section), fields, retrieved_at,
                preserve_unchanged=section in {"coal.futures", "emissions.futures"},
            )
        if changed:
            atomic_save(workbook, workbook_path)
    finally:
        workbook.close()
