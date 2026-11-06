"""NBP table A cache. Calendar rows explicitly record their source publication date."""
from __future__ import annotations
from workbook_storage import atomic_save, serialized_update
from market_values import number as market_number

from bisect import bisect_right
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
import json
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from openpyxl import load_workbook

FX_SHEET = "KURSY_NBP"
FX_HEADERS = ("date", "currency", "mid_pln", "effective_date", "table_number", "checked_at")
MARKET_SHEETS = ("GAZ_RDN", "EE_RDN", "GAZ_OTF", "EE_OTF", "WEGIEL", "EUA")
CURRENCIES = ("EUR", "USD")


class ExchangeRateError(ValueError):
    """A report must never silently label unconverted prices as PLN."""


def warsaw_today() -> date:
    return datetime.now(ZoneInfo("Europe/Warsaw")).date()


def as_date(value) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def positive_decimal(value) -> Decimal:
    try:
        result = Decimal(str(value).strip().replace(" ", "").replace("\xa0", "").replace(",", "."))
    except (InvalidOperation, ValueError) as error:
        raise ExchangeRateError(f"Nieprawidłowa wartość kursu NBP: {value!r}") from error
    if not result.is_finite() or result <= 0:
        raise ExchangeRateError("Kurs NBP musi być dodatnią, skończoną liczbą.")
    return result


def fetch_rates(currency: str, start: date, end: date) -> list[dict]:
    url = f"https://api.nbp.pl/api/exchangerates/rates/A/{currency}/{start.isoformat()}/{end.isoformat()}/?format=json"
    request = Request(url, headers={"Accept": "application/json", "User-Agent": "EnergyMarketDashboard/1.0"})
    try:
        with urlopen(request, timeout=20) as response:
            payload = json.load(response)
    except HTTPError as error:
        if error.code == 404:  # No table was published within this interval.
            return []
        raise ExchangeRateError(f"NBP: błąd HTTP {error.code} przy pobieraniu {currency}.") from error
    except (URLError, TimeoutError, OSError, ValueError) as error:
        raise ExchangeRateError(f"Nie udało się pobrać kursów {currency} z NBP.") from error
    try:
        if payload["code"] != currency or payload["table"] != "A":
            raise ValueError("Nieoczekiwana waluta lub tabela")
        rates = payload["rates"]
        for row in rates:
            publication = as_date(row["effectiveDate"])
            if not start <= publication <= end:
                raise ValueError("Data kursu poza zakresem")
            positive_decimal(row["mid"])
            if not row["no"]:
                raise ValueError("Brak numeru tabeli")
        return rates
    except (KeyError, TypeError, ValueError) as error:
        raise ExchangeRateError("Nieprawidłowa odpowiedź API NBP.") from error


def _read_cache(workbook) -> dict:
    if FX_SHEET not in workbook.sheetnames:
        return {}
    sheet = workbook[FX_SHEET]
    if tuple(cell.value for cell in sheet[1]) != FX_HEADERS:
        raise ExchangeRateError(f"Nieprawidłowe kolumny arkusza {FX_SHEET}.")
    result = {}
    for values in sheet.iter_rows(min_row=2, values_only=True):
        if not values[0]:
            continue
        record = dict(zip(FX_HEADERS, values))
        try:
            day, effective = as_date(record["date"]), as_date(record["effective_date"])
            positive_decimal(record["mid_pln"])
            if record["currency"] not in CURRENCIES or effective > day or not record["table_number"]:
                continue
        except (ValueError, TypeError):
            continue  # Invalid/missing cache entries are repaired as gaps.
        record.update(date=day, effective_date=effective)
        result[(day, record["currency"])] = record
    return result


def read_exchange_rates(path: Path) -> dict:
    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        return _read_cache(workbook)
    finally:
        workbook.close()


_atomic_save = atomic_save


@serialized_update
def ensure_exchange_rates(path: Path, *, today: date | None = None) -> dict:
    """Fill every calendar day from the oldest market record through today.

    Missing days are fetched in <=93-day windows, with a 14-day seed for
    previous-publication fallback. Today's entry is refreshed because table A
    may be published after an earlier invocation. A complete historical cache
    needs no network. No workbook is changed if fetching/validation fails.
    """
    path = Path(path)
    today = today or warsaw_today()
    workbook = load_workbook(path)
    try:
        dates = []
        for name in MARKET_SHEETS:
            if name not in workbook.sheetnames:
                continue
            sheet = workbook[name]
            headers = [cell.value for cell in sheet[1]]
            if "trading_date" not in headers:
                continue
            column = headers.index("trading_date")
            for row in sheet.iter_rows(min_row=2, values_only=True):
                if row[column]:
                    dates.append(as_date(row[column]))
        if not dates:
            return {}
        start = min(dates)
        if start < date(2002, 1, 2):
            raise ExchangeRateError("API NBP udostępnia kursy od 02.01.2002.")
        if start > today:
            raise ExchangeRateError("Daty notowań są późniejsze niż dzisiejsza data.")
        cache = _read_cache(workbook)
        updated = dict(cache)
        checked_at = datetime.combine(today, datetime.now(ZoneInfo("Europe/Warsaw")).timetz()).isoformat()
        for currency in CURRENCIES:
            missing = []
            day = start
            while day <= today:
                record = cache.get((day, currency))
                # Same-day publication can arrive after an earlier fallback.
                if record is None or (record["table_number"] != "MANUAL"
                        and record["effective_date"] < day
                        and (day == today or (day.weekday() < 5 and str(record.get("checked_at", ""))[:10] <= day.isoformat()))):
                    missing.append(day)
                day += timedelta(days=1)
            if not missing:
                continue
            publications = {}
            for (day, code), record in cache.items():
                if code == currency:
                    publications[record["effective_date"]] = record
            # Group nearby gaps, without downloading complete intervening years.
            groups = []
            for day in missing:
                if not groups or (day - groups[-1][-1]).days > 7:
                    groups.append([day])
                else:
                    groups[-1].append(day)
            for group in groups:
                cursor = max(date(2002, 1, 2), group[0] - timedelta(days=14))
                end = group[-1]
                while cursor <= end:
                    chunk_end = min(end, cursor + timedelta(days=92))
                    for row in fetch_rates(currency, cursor, chunk_end):
                        effective = as_date(row["effectiveDate"])
                        publications[effective] = dict(
                            effective_date=effective, mid_pln=float(positive_decimal(row["mid"])),
                            table_number=row["no"],
                        )
                    cursor = chunk_end + timedelta(days=1)
            publication_days = sorted(publications)
            for day in missing:
                index = bisect_right(publication_days, day) - 1
                if index < 0:
                    raise ExchangeRateError(f"Brak wcześniejszego kursu {currency} dla {day}.")
                source = publications[publication_days[index]]
                updated[(day, currency)] = dict(
                    date=day, currency=currency, mid_pln=source["mid_pln"],
                    effective_date=source["effective_date"], table_number=source["table_number"],
                    checked_at=checked_at,
                )
        if updated != cache:
            sheet = workbook[FX_SHEET] if FX_SHEET in workbook.sheetnames else workbook.create_sheet(FX_SHEET)
            sheet.delete_rows(1, sheet.max_row)
            sheet.append(FX_HEADERS)
            for key in sorted(updated):
                row = updated[key]
                sheet.append([row[field].isoformat() if isinstance(row[field], date) else row[field] for field in FX_HEADERS])
            sheet.freeze_panes = "A2"
            sheet.auto_filter.ref = sheet.dimensions
            _atomic_save(workbook, path)
        return updated
    finally:
        workbook.close()


def convert_record_to_pln(record: dict, currency: str, rates: dict) -> dict:
    """Convert prices only. Preserve original values and FX provenance in JSON."""
    day = as_date(record["trading_date"])
    fx = rates.get((day, currency))
    if fx is None:
        raise ExchangeRateError(f"Brak kursu {currency} dla notowania {day}.")
    rate = positive_decimal(fx["mid_pln"])
    converted = dict(record)
    converted["source_currency"] = currency
    converted["currency"] = "PLN"
    converted["fx_mid_pln"] = float(rate)
    converted["fx_effective_date"] = as_date(fx["effective_date"]).isoformat()
    converted["fx_table_number"] = fx["table_number"]
    converted["source_values"] = {key: record.get(key) for key in ("price", "open", "high", "low", "change_pct")}
    for field in ("price", "open", "high", "low"):
        value = record.get(field)
        if value is None or value in ("", "—", "-"):
            converted[field] = None
            continue
        try:
            number = market_number(value)
        except ValueError as error:
            raise ExchangeRateError(f"Nieprawidłowa cena {field} dla {day}.") from error
        converted[field] = float(number * rate)
    # Source percentage changes are foreign-currency changes, not PLN changes.
    converted["change_pct"] = None
    return converted


def missing_exchange_rates(path: Path, *, today: date | None = None) -> list[tuple[date, str]]:
    """Calendar gaps, including all historical market dates, through today."""
    cache = read_exchange_rates(path)
    workbook = load_workbook(path, read_only=True, data_only=True)
    dates = []
    try:
        for name in MARKET_SHEETS:
            if name not in workbook.sheetnames:
                continue
            rows = workbook[name].iter_rows(values_only=True)
            headers = next(rows)
            if 'trading_date' in headers:
                index = headers.index('trading_date')
                dates.extend(as_date(row[index]) for row in rows if row[index])
    finally:
        workbook.close()
    if not dates:
        return []
    first, last = min(dates), today or warsaw_today()
    return [(first + timedelta(days=i), currency)
            for i in range(max(0, (last-first).days+1)) for currency in CURRENCIES
            if (first + timedelta(days=i), currency) not in cache]


@serialized_update
def save_manual_exchange_rates(path: Path, entries: list[tuple[date, str, object]]) -> None:
    validated = [(day, code, float(positive_decimal(value))) for day, code, value in entries]
    if any(code not in CURRENCIES or day > warsaw_today() for day, code, _ in validated):
        raise ExchangeRateError('Nieprawidłowa waluta lub data kursu.')
    workbook = load_workbook(path)
    try:
        cache = _read_cache(workbook)
        for day, code, value in validated:
            cache[(day, code)] = dict(date=day, currency=code, mid_pln=value,
                effective_date=day, table_number='MANUAL',
                checked_at=datetime.now(ZoneInfo('Europe/Warsaw')).isoformat())
        sheet = workbook[FX_SHEET] if FX_SHEET in workbook.sheetnames else workbook.create_sheet(FX_SHEET)
        sheet.delete_rows(1, sheet.max_row)
        sheet.append(FX_HEADERS)
        for key in sorted(cache):
            sheet.append([value.isoformat() if isinstance(value, date) else value
                          for value in (cache[key][field] for field in FX_HEADERS)])
        _atomic_save(workbook, Path(path))
    finally:
        workbook.close()
