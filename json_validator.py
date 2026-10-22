from dataclasses import dataclass, field
from datetime import date, datetime
import json
import re
from typing import Any
from urllib.parse import parse_qs, urlparse

from contract_selection import ContractSet, build_contract_set


SECTION_NAMES = (
    "gas.day_ahead",
    "gas.futures",
    "electricity.day_ahead",
    "electricity.futures",
    "coal.futures",
    "emissions.futures",
)
ALLOWED_STATUS = {"success", "partial", "error"}
SECTION_ALIASES = {
    "gas": "gas.day_ahead",
    "gas.rdn": "gas.day_ahead",
    "gas.otf": "gas.futures",
    "electricity": "electricity.day_ahead",
    "electricity.rdn": "electricity.day_ahead",
    "electricity.otf": "electricity.futures",
    "coal": "coal.futures",
    "eua": "emissions.futures",
    "eua.futures": "emissions.futures",
    "emissions": "emissions.futures",
}
FENCED_JSON = re.compile(r"^\s*```(?:json)?\s*(.*?)\s*```\s*$", re.DOTALL | re.IGNORECASE)


@dataclass(frozen=True)
class ValidationIssue:
    section: str
    path: str
    message: str
    severity: str = "error"


@dataclass
class ValidationReport:
    data: dict[str, Any] | None = None
    issues: list[ValidationIssue] = field(default_factory=list)
    section_validity: dict[str, bool] = field(
        default_factory=lambda: {name: True for name in SECTION_NAMES}
    )

    @property
    def is_valid(self) -> bool:
        return self.data is not None and not any(
            issue.severity == "error" for issue in self.issues
        )

    @property
    def is_usable(self) -> bool:
        """A parsed response with no global errors and at least one valid section."""
        return (
            self.is_structurally_valid
            and any(self.section_validity.values())
        )

    @property
    def is_structurally_valid(self) -> bool:
        """JSON envelope is valid even when every data section is incomplete."""
        return self.data is not None and not any(
            issue.severity == "error" and issue.section == "global"
            for issue in self.issues
        )

    def add(
        self,
        section: str,
        path: str,
        message: str,
        severity: str = "error",
    ) -> None:
        self.issues.append(ValidationIssue(section, path, message, severity))
        if severity == "error" and section in self.section_validity:
            self.section_validity[section] = False


def parse_json_response(response: str) -> dict[str, Any]:
    text = response.strip()
    fenced = FENCED_JSON.fullmatch(text)
    if fenced:
        text = fenced.group(1).strip()
    try:
        value = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Niepoprawny JSON: linia {error.lineno}, kolumna {error.colno}: {error.msg}."
        ) from error
    if not isinstance(value, dict):
        raise ValueError("Odpowiedź JSON musi być jednym obiektem.")
    return value


def _type_name(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    return type(value).__name__


def _is_number_or_none(value: Any) -> bool:
    return value is None or (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    )


def _valid_iso_date(value: Any) -> bool:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return False
    try:
        date.fromisoformat(value)
        return True
    except ValueError:
        return False


def _valid_url(value: Any, expected_host: str | None = None) -> bool:
    if not isinstance(value, str):
        return False
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return False
    return expected_host is None or parsed.netloc.lower().endswith(expected_host)


def _normalize_error_section(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip().lower()
    if normalized in SECTION_NAMES:
        return normalized
    if normalized in SECTION_ALIASES:
        return SECTION_ALIASES[normalized]
    for section in SECTION_NAMES:
        if normalized.startswith(section + ".") or normalized.startswith(section + "["):
            return section
    return None


def _validate_tge_source_url(
    value: Any,
    expected_path: str,
    expected_date: str,
    section: str,
    path: str,
    report: ValidationReport,
) -> None:
    if not _valid_url(value, "tge.pl"):
        return
    parsed = urlparse(value)
    if parsed.path.rstrip("/") != expected_path:
        report.add(
            section,
            path,
            f"Oczekiwano ścieżki {expected_path}.",
        )
    expected_query_date = date.fromisoformat(expected_date).strftime("%d-%m-%Y")
    actual_dates = parse_qs(parsed.query).get("dateShow", [])
    if actual_dates != [expected_query_date]:
        report.add(
            section,
            path,
            f"Oczekiwano parametru dateShow={expected_query_date}.",
        )


def _get_section(
    payload: dict[str, Any], market: str, collection: str, report: ValidationReport
) -> list[Any]:
    section = f"{market}.{collection}"
    data = payload.get("data")
    if not isinstance(data, dict):
        report.add(section, "data", "Oczekiwano obiektu.")
        return []
    market_value = data.get(market)
    if not isinstance(market_value, dict):
        report.add(section, f"data.{market}", "Oczekiwano obiektu.")
        return []
    records = market_value.get(collection)
    if not isinstance(records, list):
        report.add(section, f"data.{market}.{collection}", "Oczekiwano tablicy.")
        return []
    return records


def _validate_record_shell(
    record: Any,
    section: str,
    path: str,
    report: ValidationReport,
    expected_host: str,
) -> dict[str, Any] | None:
    if not isinstance(record, dict):
        report.add(section, path, "Rekord musi być obiektem.")
        return None
    for key in ("data_id", "source_url", "trading_date", "instrument", "values"):
        if key not in record:
            report.add(section, f"{path}.{key}", "Brak wymaganego pola.")
    if not isinstance(record.get("data_id"), str) or not record.get("data_id"):
        report.add(section, f"{path}.data_id", "Oczekiwano niepustego tekstu.")
    if not _valid_url(record.get("source_url"), expected_host):
        report.add(section, f"{path}.source_url", f"Oczekiwano URL domeny {expected_host}.")
    if not _valid_iso_date(record.get("trading_date")):
        report.add(section, f"{path}.trading_date", "Oczekiwano daty YYYY-MM-DD.")
    if not isinstance(record.get("instrument"), str) or not record.get("instrument"):
        report.add(section, f"{path}.instrument", "Oczekiwano niepustego tekstu.")
    if not isinstance(record.get("values"), dict):
        report.add(section, f"{path}.values", "Oczekiwano obiektu.")
    return record


def _validate_tge_values(
    values: Any, keys: tuple[str, ...], section: str, path: str, report: ValidationReport
) -> None:
    if not isinstance(values, dict):
        return
    for key in keys:
        if key not in values:
            report.add(section, f"{path}.{key}", "Brak wymaganego pola.")
        elif not _is_number_or_none(values[key]):
            report.add(
                section,
                f"{path}.{key}",
                f"Oczekiwano liczby lub null, otrzymano {_type_name(values[key])}.",
            )


def _validate_rdn(
    payload: dict[str, Any],
    market: str,
    expected_dates: list[date],
    report: ValidationReport,
) -> None:
    section = f"{market}.day_ahead"
    records = _get_section(payload, market, "day_ahead", report)
    instruments = (
        {"tge_gas_da": "TGEgasDA"}
        if market == "gas"
        else {
            "tge_power_da_base": "TGeBase",
            "tge_power_da_peak": "TGePeak",
            "tge_power_da_offpeak": "TGeOffpeak",
            "tge_power_da_24": "TGe24",
        }
    )
    expected = {(value.isoformat(), data_id) for value in expected_dates for data_id in instruments}
    actual: set[tuple[str, str]] = set()
    for index, raw in enumerate(records):
        path = f"data.{market}.day_ahead[{index}]"
        record = _validate_record_shell(raw, section, path, report, "tge.pl")
        if record is None:
            continue
        data_id = record.get("data_id")
        trading_date = record.get("trading_date")
        pair = (trading_date, data_id)
        if pair in actual:
            report.add(section, path, f"Duplikat rekordu {data_id} dla {trading_date}.")
        actual.add(pair)
        if data_id not in instruments:
            report.add(section, f"{path}.data_id", "Nieoczekiwany identyfikator RDN.")
        elif record.get("instrument") != instruments[data_id]:
            report.add(section, f"{path}.instrument", f"Oczekiwano {instruments[data_id]}.")
        if _valid_iso_date(trading_date):
            expected_path = "/gaz-rdn" if market == "gas" else "/energia-elektryczna-rdn"
            _validate_tge_source_url(
                record.get("source_url"),
                expected_path,
                trading_date,
                section,
                f"{path}.source_url",
                report,
            )
        _validate_tge_values(
            record.get("values"),
            ("price_pln_mwh", "volume_mwh", "change_pct"),
            section,
            f"{path}.values",
            report,
        )
    for missing in sorted(expected - actual):
        report.add(section, f"data.{market}.day_ahead", f"Brak rekordu {missing[1]} dla {missing[0]}.")
    for extra in sorted(actual - expected):
        report.add(section, f"data.{market}.day_ahead", f"Nieoczekiwany rekord {extra[1]} dla {extra[0]}.")


def _contract_map(contracts: ContractSet, market: str) -> dict[str, str]:
    prefix = "gas_base" if market == "gas" else "power_base"
    result: dict[str, str] = {}
    for group, values in (
        ("week", contracts.weeks),
        ("month", contracts.months),
        ("quarter", contracts.quarters),
        ("year", contracts.years),
    ):
        for index, instrument in enumerate(values, 1):
            result[f"{prefix}_{group}_{index}"] = instrument
    return result


def _validate_otf(
    payload: dict[str, Any], market: str, session_date: date, report: ValidationReport
) -> None:
    section = f"{market}.futures"
    records = _get_section(payload, market, "futures", report)
    expected = _contract_map(
        build_contract_set(session_date, gas=market == "gas"), market
    )
    actual_ids: set[str] = set()
    for index, raw in enumerate(records):
        path = f"data.{market}.futures[{index}]"
        record = _validate_record_shell(raw, section, path, report, "tge.pl")
        if record is None:
            continue
        data_id = record.get("data_id")
        if data_id in actual_ids:
            report.add(section, f"{path}.data_id", f"Duplikat {data_id}.")
        actual_ids.add(data_id)
        if data_id not in expected:
            report.add(section, f"{path}.data_id", "Nieoczekiwany identyfikator OTF.")
        elif record.get("instrument") != expected[data_id]:
            report.add(section, f"{path}.instrument", f"Oczekiwano {expected[data_id]}.")
        if record.get("trading_date") != session_date.isoformat():
            report.add(section, f"{path}.trading_date", f"Oczekiwano {session_date.isoformat()}.")
        expected_path = "/gaz-otf" if market == "gas" else "/energia-elektryczna-otf"
        _validate_tge_source_url(
            record.get("source_url"),
            expected_path,
            session_date.isoformat(),
            section,
            f"{path}.source_url",
            report,
        )
        _validate_tge_values(
            record.get("values"),
            ("dkr_pln_mwh", "max_pln_mwh", "volume_mwh"),
            section,
            f"{path}.values",
            report,
        )
    for missing in sorted(set(expected) - actual_ids):
        report.add(section, f"data.{market}.futures", f"Brak kontraktu {missing} ({expected[missing]}).")


def _validate_investing(
    payload: dict[str, Any],
    market: str,
    expected_id: str,
    expected_instrument: str,
    date_window: tuple[date, date],
    report: ValidationReport,
) -> None:
    section = f"{market}.futures"
    records = _get_section(payload, market, "futures", report)
    seen_dates: set[str] = set()
    start, end = date_window
    for index, raw in enumerate(records):
        path = f"data.{market}.futures[{index}]"
        record = _validate_record_shell(raw, section, path, report, "investing.com")
        if record is None:
            continue
        if record.get("data_id") != expected_id:
            report.add(section, f"{path}.data_id", f"Oczekiwano {expected_id}.")
        if record.get("instrument") != expected_instrument:
            report.add(section, f"{path}.instrument", f"Oczekiwano {expected_instrument}.")
        text_date = record.get("trading_date")
        if _valid_iso_date(text_date):
            parsed = date.fromisoformat(text_date)
            if not start <= parsed <= end:
                report.add(section, f"{path}.trading_date", f"Data poza zakresem {start}–{end}.")
            if text_date in seen_dates:
                report.add(section, f"{path}.trading_date", f"Duplikat daty {text_date}.")
            seen_dates.add(text_date)
        values = record.get("values")
        if isinstance(values, dict):
            for key in ("price", "open", "high", "low", "volume", "change_pct"):
                if key not in values:
                    report.add(section, f"{path}.values.{key}", "Brak wymaganego pola.")
                elif values[key] is not None and not isinstance(values[key], str):
                    report.add(section, f"{path}.values.{key}", "Oczekiwano tekstu lub null.")
    if not records:
        report.add(section, f"data.{market}.futures", "Brak rekordów z 30-dniowego zakresu.")


def validate_payload(
    payload: dict[str, Any],
    source_dates: dict[str, list[date]],
    otf_session_date: date,
    coal_window: tuple[date, date],
    eua_window: tuple[date, date],
) -> ValidationReport:
    report = ValidationReport(data=payload)
    if payload.get("schema_version") != "market-data-1.0":
        report.add("global", "schema_version", 'Oczekiwano wartości "market-data-1.0".')
    retrieved_at = payload.get("retrieved_at")
    try:
        parsed_at = datetime.fromisoformat(retrieved_at) if isinstance(retrieved_at, str) else None
        if parsed_at is None or parsed_at.tzinfo is None:
            raise ValueError
    except ValueError:
        report.add("global", "retrieved_at", "Oczekiwano daty ISO 8601 ze strefą czasową.")
    status = payload.get("status")
    if status not in ALLOWED_STATUS:
        report.add("global", "status", "Dozwolone wartości: success, partial, error.")
    errors = payload.get("errors")
    if not isinstance(errors, list):
        report.add("global", "errors", "Oczekiwano tablicy.")
        errors = []
    else:
        for index, error in enumerate(errors):
            if not isinstance(error, dict):
                report.add("global", f"errors[{index}]", "Wpis błędu musi być obiektem.")
                continue
            for key in ("section", "source_url", "message"):
                if not isinstance(error.get(key), str) or not error.get(key):
                    report.add("global", f"errors[{index}].{key}", "Oczekiwano niepustego tekstu.")
            error_section = error.get("section")
            normalized_section = _normalize_error_section(error_section)
            if isinstance(error_section, str) and normalized_section is None:
                report.add(
                    "global",
                    f"errors[{index}].section",
                    f"Nieznana sekcja danych rynkowych: {error_section!r}.",
                )
            elif (
                normalized_section is not None
                and isinstance(error.get("message"), str)
                and error.get("message")
            ):
                report.add(
                    normalized_section,
                    f"errors[{index}]",
                    f"Źródło zgłosiło problem: {error['message']}",
                )
            if isinstance(error.get("source_url"), str) and not _valid_url(error["source_url"]):
                report.add("global", f"errors[{index}].source_url", "Oczekiwano poprawnego URL.")

    _validate_rdn(payload, "gas", source_dates["gas_rdn"], report)
    _validate_rdn(payload, "electricity", source_dates["electricity_rdn"], report)
    _validate_otf(payload, "gas", otf_session_date, report)
    _validate_otf(payload, "electricity", otf_session_date, report)
    _validate_investing(
        payload, "coal", "coal_rotterdam_futures", "Rotterdam Coal Futures",
        coal_window, report,
    )
    _validate_investing(
        payload, "emissions", "eua_year_futures",
        "European Union Allowance (EUA) Year Futures", eua_window, report,
    )
    record_count = 0
    data = payload.get("data")
    if isinstance(data, dict):
        for market in data.values():
            if isinstance(market, dict):
                record_count += sum(len(value) for value in market.values() if isinstance(value, list))
    has_validation_errors = any(issue.severity == "error" for issue in report.issues)
    if status == "success" and (errors or has_validation_errors):
        report.add("metadata", "status", "Status success jest niespójny z błędami odpowiedzi.")
    if status == "partial" and (not errors or record_count == 0):
        report.add("metadata", "status", "Status partial wymaga rekordów oraz wpisu w errors.")
    if status == "error" and record_count > 0:
        report.add("metadata", "status", "Status error jest niespójny z obecnością rekordów.")
    return report


def validate_response(
    response: str,
    source_dates: dict[str, list[date]],
    otf_session_date: date,
    coal_window: tuple[date, date],
    eua_window: tuple[date, date],
) -> ValidationReport:
    try:
        payload = parse_json_response(response)
    except ValueError as error:
        report = ValidationReport()
        report.add("global", "$", str(error))
        return report
    return validate_payload(
        payload, source_dates, otf_session_date, coal_window, eua_window
    )
