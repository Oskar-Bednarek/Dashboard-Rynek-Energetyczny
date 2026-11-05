"""Real wood-chip transactions, kept separate from demo and energy data."""
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit

from openpyxl import load_workbook
from exchange_rates import _atomic_save, as_date

SHEET = "ZREBKI"
FIELDS = ("record_id", "date", "date_basis", "record_type", "buyer", "kind", "price_pln_t", "price_basis", "transport", "volume_t", "source_name", "source_url", "reference", "evidence", "retrieved_at")


@dataclass
class BiomassValidation:
    records: list[dict] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def is_valid(self):
        return not self.errors


def read_transactions(path: Path) -> list[dict]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if SHEET not in workbook.sheetnames:
            return []
        sheet = workbook[SHEET]
        headers = tuple(cell.value for cell in sheet[1])
        if headers != FIELDS:
            raise ValueError("Arkusz ZREBKI ma nieprawidłowy układ kolumn.")
        records = []
        for values in sheet.iter_rows(min_row=2, values_only=True):
            if not values[0]:
                continue
            row = dict(zip(FIELDS, values))
            row["date"] = as_date(row["date"]).isoformat()
            records.append(row)
        return records
    finally:
        workbook.close()


def search_context(records: list[dict], end: date) -> tuple[date, list[dict]]:
    eligible = [r for r in records if as_date(r["date"]) <= end]
    start = max((as_date(r["date"]) for r in eligible), default=end-timedelta(days=29))
    return start, [r for r in eligible if as_date(r["date"]) == start]


def _url(value):
    if not isinstance(value, str):
        raise ValueError("Brak linku źródłowego")
    parts = urlsplit(value)
    if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
        raise ValueError("Nieprawidłowy link źródłowy")
    return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), parts.path.rstrip('/'), parts.query, ''))


def _text(value, required=False):
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Brak wymaganego tekstu")
    text = value.strip()
    if text.startswith(('=', '+', '-', '@')):
        raise ValueError("Tekst nie może zaczynać się od znaku formuły Excela")
    return text


def _number(value, optional=False):
    if value is None and optional:
        return None
    if isinstance(value, bool) or not isinstance(value, (float, int)):
        raise ValueError("Cena i wolumen muszą być liczbami JSON, bez jednostek")
    number = Decimal(str(value))
    if not number.is_finite() or number <= 0:
        raise ValueError("Cena i wolumen muszą być dodatnie i skończone")
    return float(number)


def record_key(row):
    normalized = lambda value: re.sub(r'\s+', ' ', str(value or '').strip().casefold())
    # Do not count the same named transaction again just because another site cites it.
    identity = [row["date"], normalized(row.get("buyer")), normalized(row["kind"]),
                str(Decimal(str(row["price_pln_t"])).normalize()),
                str(Decimal(str(row["volume_t"])).normalize()) if row.get("volume_t") is not None else None,
                row["price_basis"], row["record_type"], normalized(row.get("reference"))]
    if not row.get("buyer"):
        identity.append(_url(row["source_url"]))
    return sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def validate_response(text: str, start: date, end: date) -> BiomassValidation:
    result = BiomassValidation()
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.I)[:-3].strip()
    try:
        payload = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nieprawidłowa liczba JSON")))
        if not isinstance(payload, dict) or payload.get("schema_version") != "biomass-data-1.0":
            raise ValueError("Oczekiwano schematu biomass-data-1.0")
        if payload.get("status") not in ("success", "partial", "error"):
            raise ValueError("Nieprawidłowy status odpowiedzi")
        retrieved = payload.get("retrieved_at")
        if not isinstance(retrieved, str) or datetime.fromisoformat(retrieved.replace('Z','+00:00')).tzinfo is None:
            raise ValueError("retrieved_at musi zawierać datę, godzinę i strefę czasową")
        errors = payload.get("errors")
        if not isinstance(errors, list):
            raise ValueError("Brak listy errors")
        if any(not isinstance(e, dict) or not isinstance(e.get("message"), str) for e in errors):
            raise ValueError("Wpisy errors muszą zawierać message")
        transactions = payload["data"]["biomass"]["transactions"]
        if not isinstance(transactions, list):
            raise ValueError("transactions musi być listą")
        if payload["status"] == "error" or (payload["status"] == "success" and errors):
            raise ValueError("Model zgłosił błąd wyszukiwania — popraw odpowiedź lub ponów wyszukiwanie")
        if payload["status"] == "partial" and not errors:
            raise ValueError("Status partial wymaga opisania braków w errors")
    except (ValueError, TypeError, KeyError) as error:
        result.errors.append(f"Nie udało się odczytać odpowiedzi: {error}")
        return result
    result.warnings = [entry["message"] for entry in errors]
    if payload["status"] == "partial" and not transactions:
        result.errors.append("Wyszukiwanie nie było kompletne i nie zwróciło rekordów. Ponów wyszukiwanie.")
        return result
    for index, raw in enumerate(transactions, 1):
        try:
            if not isinstance(raw, dict):
                raise ValueError("Rekord musi być obiektem")
            row = {}
            raw_date = raw.get("date")
            if not isinstance(raw_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_date):
                raise ValueError("Data musi mieć format RRRR-MM-DD")
            day = date.fromisoformat(raw_date)
            if not start <= day <= end:
                raise ValueError(f"Data poza zakresem {start}–{end}")
            row["date"] = day.isoformat()
            for key, allowed in {
                "date_basis": ("transaction", "award_publication"),
                "record_type": ("transaction", "tender_award"),
                "price_basis": ("net", "gross", "unknown"),
                "transport": ("included", "excluded", "unknown"),
            }.items():
                if raw.get(key) not in allowed:
                    raise ValueError(f"Nieprawidłowe pole {key}")
                row[key] = raw[key]
            if row['date_basis'] == 'award_publication' and row['record_type'] != 'tender_award':
                raise ValueError("Data publikacji wyniku dotyczy wyłącznie przetargów")
            for key in ("buyer", "reference"):
                row[key] = _text(raw.get(key))
            for key in ("kind", "source_name", "evidence"):
                row[key] = _text(raw.get(key), required=True)
            row["source_url"] = _url(raw.get("source_url"))
            row["price_pln_t"] = _number(raw.get("price_pln_t"))
            row["volume_t"] = _number(raw.get("volume_t"), optional=True)
            row["retrieved_at"] = retrieved
            row["record_id"] = record_key(row)
            result.records.append(row)
        except (ValueError, TypeError, KeyError) as error:
            result.errors.append(f"Rekord {index}: {error}.")
    # Reject the whole batch when any record is invalid; no partial, hidden writes.
    return result


def save_transactions(path: Path, records: list[dict]) -> int:
    workbook = load_workbook(path)
    try:
        if SHEET in workbook.sheetnames:
            sheet = workbook[SHEET]
            if tuple(c.value for c in sheet[1]) != FIELDS:
                raise ValueError("Arkusz ZREBKI ma nieprawidłowy układ kolumn.")
        else:
            sheet = workbook.create_sheet(SHEET)
            sheet.append(FIELDS)
        existing = {r[0] for r in sheet.iter_rows(min_row=2, values_only=True) if r[0]}
        added = 0
        for row in records:
            key = record_key(row)
            if key in existing:
                continue
            row = dict(row, record_id=key)
            sheet.append([row.get(field) for field in FIELDS])
            existing.add(key)
            added += 1
        if added:
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            _atomic_save(workbook, path)
        return added
    finally:
        workbook.close()
