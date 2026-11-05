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
LEGACY_FIELDS = ("record_id", "date", "date_basis", "record_type", "buyer", "kind", "price_pln_t", "price_basis", "transport", "volume_t", "source_name", "source_url", "reference", "evidence", "retrieved_at")
FIELDS = LEGACY_FIELDS + ("tender_id",)
TENDER_SHEET = "ZREBKI_PRZETARGI"
TENDER_FIELDS = ("tender_id", "published_date", "buyer", "kind", "reference", "source_name", "source_url", "status", "status_date", "deadline", "volume_t", "evidence", "checked_as_of", "retrieved_at")



@dataclass
class BiomassValidation:
    records: list[dict] = field(default_factory=list)
    tenders: list[dict] = field(default_factory=list)
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
        if headers not in (FIELDS, LEGACY_FIELDS):
            raise ValueError("Arkusz ZREBKI ma nieprawidłowy układ kolumn.")
        records = []
        for values in sheet.iter_rows(min_row=2, values_only=True):
            if not values[0]:
                continue
            row = dict(zip(headers, values))
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


def validate_response(text: str, start: date, end: date, known_tenders: list[dict] | None = None) -> BiomassValidation:
    result = BiomassValidation()
    text = text.strip()
    if text.startswith('```') and text.endswith('```'):
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.I)[:-3].strip()
    try:
        payload = json.loads(text, parse_constant=lambda value: (_ for _ in ()).throw(ValueError("Nieprawidłowa liczba JSON")))
        if not isinstance(payload, dict) or payload.get("schema_version") not in ("biomass-data-1.0", "biomass-data-2.0"):
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
        tenders = payload["data"]["biomass"].get("tenders", [])
        if not isinstance(tenders, list):
            raise ValueError("tenders musi być listą")
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
    if payload["status"] == "partial" and not transactions and not tenders:
        result.errors.append("Wyszukiwanie nie było kompletne i nie zwróciło rekordów. Ponów wyszukiwanie.")
        return result
    known = {r["tender_id"]: r for r in (known_tenders or [])}
    for index, raw in enumerate(tenders, 1):
        try:
            result.tenders.append(validate_tender(raw, end, retrieved, known))
        except (ValueError, TypeError, KeyError) as error:
            result.errors.append(f"Przetarg {index}: {error}.")
    ids = [row["tender_id"] for row in result.tenders]
    if len(ids) != len(set(ids)):
        result.errors.append("Ten sam przetarg występuje więcej niż raz w odpowiedzi.")
    allowed_tenders = {**known, **{r["tender_id"]: r for r in result.tenders}}
    for index, raw in enumerate(transactions, 1):
        try:
            if not isinstance(raw, dict):
                raise ValueError("Rekord musi być obiektem")
            row = {}
            raw_date = raw.get("date")
            if not isinstance(raw_date, str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}', raw_date):
                raise ValueError("Data musi mieć format RRRR-MM-DD")
            day = date.fromisoformat(raw_date)
            linked_id = raw.get("tender_id")
            if linked_id is not None and linked_id not in allowed_tenders:
                raise ValueError("Nieznany tender_id — przekaż przetarg w tenders lub użyj ID z promptu")
            if day > end or (day < start and linked_id not in known):
                raise ValueError(f"Data poza zakresem {start}–{end}")
            row["tender_id"] = linked_id
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
            if not linked_id and row.get("reference"):
                matches = [t for t in allowed_tenders.values() if t.get("reference") == row["reference"] and t.get("buyer") == row.get("buyer")]
                if len(matches) == 1:
                    linked_id = matches[0]["tender_id"]
                    row["tender_id"] = linked_id
            if linked_id:
                tender = allowed_tenders[linked_id]
                if row["record_type"] != "tender_award" or tender["status"] != "awarded":
                    raise ValueError("Cena z przetargu wymaga potwierdzonego statusu awarded")
                if day != as_date(tender["status_date"]):
                    raise ValueError("Data wyniku i status_date przetargu muszą być zgodne")
            row["price_pln_t"] = _number(raw.get("price_pln_t"))
            row["volume_t"] = _number(raw.get("volume_t"), optional=True)
            row["retrieved_at"] = retrieved
            row["record_id"] = record_key(row)
            result.records.append(row)
        except (ValueError, TypeError, KeyError) as error:
            result.errors.append(f"Rekord {index}: {error}.")
    # Reject the whole batch when any record is invalid; no partial, hidden writes.
    return result


def read_tenders(path: Path, as_of: date | None = None, *, open_only: bool = False, history: bool = False) -> list[dict]:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        if TENDER_SHEET not in workbook.sheetnames:
            return []
        sheet = workbook[TENDER_SHEET]
        if tuple(c.value for c in sheet[1]) != TENDER_FIELDS:
            raise ValueError("Arkusz ZREBKI_PRZETARGI ma nieprawidłowy układ kolumn.")
        latest = {}
        snapshots = []
        for values in sheet.iter_rows(min_row=2, values_only=True):
            if not values[0]:
                continue
            row = dict(zip(TENDER_FIELDS, values))
            if as_of and (as_date(row["checked_as_of"]) > as_of or as_date(row["status_date"]) > as_of):
                continue
            snapshots.append(row)
            key = row["tender_id"]
            if key not in latest or (row["checked_as_of"], row["retrieved_at"]) > (latest[key]["checked_as_of"], latest[key]["retrieved_at"]):
                latest[key] = row
        return [r for r in (snapshots if history else latest.values()) if not open_only or r["status"] == "open"]
    finally:
        workbook.close()


def tender_key(row):
    if row.get("reference") and row.get("buyer"):
        identity = [str(row[k]).strip().casefold() for k in ("buyer", "reference")]
    else:
        identity = [_url(row["source_url"])]
    return sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()


def validate_tender(raw, end, retrieved, known):
    if not isinstance(raw, dict):
        raise ValueError("Przetarg musi być obiektem")
    row = {key: _text(raw.get(key), required=key in ("kind", "source_name", "evidence"))
           for key in ("buyer", "kind", "source_name", "reference", "evidence")}
    row["source_url"] = _url(raw.get("source_url"))
    row["volume_t"] = _number(raw.get("volume_t"), optional=True)
    row["status"] = raw.get("status")
    if row["status"] not in ("open", "awarded", "cancelled", "closed_without_result"):
        raise ValueError("Nieprawidłowy status przetargu")
    for key in ("published_date", "status_date", "deadline"):
        value = raw.get(key)
        if key == "deadline" and value is None:
            row[key] = None
            continue
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError(f"Nieprawidłowa data {key}")
        row[key] = date.fromisoformat(value).isoformat()
    if as_date(row["published_date"]) > as_date(row["status_date"]) or as_date(row["status_date"]) > end:
        raise ValueError("Daty przetargu wykraczają poza datę raportu lub są odwrócone")
    if row["deadline"] and as_date(row["deadline"]) < as_date(row["published_date"]):
        raise ValueError("Termin ofert jest wcześniejszy niż publikacja")
    supplied = raw.get("tender_id")
    if supplied:
        if supplied not in known:
            raise ValueError("Nieznany tender_id — dla nowego przetargu podaj null")
        old = known[supplied]
        if old.get("reference") and row.get("reference") != old["reference"]:
            raise ValueError("Zmieniono identyfikator wcześniej zapisanego postępowania")
    row["tender_id"] = supplied or tender_key(row)
    row["checked_as_of"] = end.isoformat()
    row["retrieved_at"] = retrieved
    return row


def save_biomass_data(path: Path, records: list[dict], tenders: list[dict]) -> tuple[int, int]:
    """Save both transaction and tender changes in one atomic workbook update."""
    workbook = load_workbook(path)
    changed = False
    added = updates = 0
    try:
        if records:
            if SHEET in workbook.sheetnames:
                sheet = workbook[SHEET]
                headers = tuple(c.value for c in sheet[1])
                if headers not in (FIELDS, LEGACY_FIELDS):
                    raise ValueError("Arkusz ZREBKI ma nieprawidłowy układ kolumn.")
                if headers == LEGACY_FIELDS:
                    sheet.cell(1, len(FIELDS), "tender_id")
                    changed = True
            else:
                sheet = workbook.create_sheet(SHEET)
                sheet.append(FIELDS)
            existing = {r[0]: index for index, r in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2) if r[0]}
            for row in records:
                key = record_key(row)
                if key in existing:
                    if row.get("tender_id") and not sheet.cell(existing[key], len(FIELDS)).value:
                        sheet.cell(existing[key], len(FIELDS), row["tender_id"])
                        changed = True
                    continue
                row = dict(row, record_id=key)
                sheet.append([row.get(field) for field in FIELDS])
                existing[key] = sheet.max_row
                added += 1
                changed = True
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
        if tenders:
            if TENDER_SHEET in workbook.sheetnames:
                sheet = workbook[TENDER_SHEET]
                if tuple(c.value for c in sheet[1]) != TENDER_FIELDS:
                    raise ValueError("Arkusz ZREBKI_PRZETARGI ma nieprawidłowy układ kolumn.")
            else:
                sheet = workbook.create_sheet(TENDER_SHEET)
                sheet.append(TENDER_FIELDS)
            existing = {(r[0], r[12]): index for index, r in enumerate(sheet.iter_rows(min_row=2, values_only=True), 2) if r[0]}
            snapshots = [dict(zip(TENDER_FIELDS, values)) for values in sheet.iter_rows(min_row=2, values_only=True) if values[0]]
            for row in tenders:
                past = [entry for entry in snapshots if entry["tender_id"] == row["tender_id"] and entry["checked_as_of"] <= row["checked_as_of"]]
                latest = max(past, key=lambda entry:(entry["checked_as_of"],entry["retrieved_at"])) if past else None
                if latest and latest["status"] != "open" and row["status"] == "open":
                    raise ValueError("Nie można ponownie otworzyć już zakończonego postępowania na podstawie starego ogłoszenia.")
                key = (row["tender_id"], row["checked_as_of"])
                values = [row.get(field) for field in TENDER_FIELDS]
                if key in existing:
                    index = existing[key]
                    if [c.value for c in sheet[index]] == values:
                        continue
                    for column, value in enumerate(values, 1):
                        sheet.cell(index, column).value = value
                else:
                    sheet.append(values)
                    existing[key] = sheet.max_row
                updates += 1
                changed = True
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
        if changed:
            _atomic_save(workbook, path)
        return added, updates
    finally:
        workbook.close()


def save_transactions(path: Path, records: list[dict]) -> int:
    return save_biomass_data(path, records, [])[0]
