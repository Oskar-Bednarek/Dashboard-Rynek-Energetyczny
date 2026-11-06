from market_values import valid_tge_record, valid_values, INVESTING_INSTRUMENTS
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from openpyxl import load_workbook

from contract_selection import OTF_MINIMUM_COUNTS, ContractSet, build_contract_set


@dataclass(frozen=True)
class CoverageResult:
    complete: bool
    details: dict[str, str]
    section_complete: dict[str, bool] = field(default_factory=dict)


def _date_text(value: object) -> str | None:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, str) and value:
        return value[:10]
    return None


def _valid_date(text):
    try:
        date.fromisoformat(text)
        return True
    except ValueError:
        return False


def _day_count_text(count: int) -> str:
    if count == 1:
        return "1 dzień"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return f"{count} dni"
    return f"{count} dni"


def _observation_count_text(count: int) -> str:
    if count == 1:
        return "1 notowanie w wybranym zakresie"
    if 2 <= count % 10 <= 4 and not 12 <= count % 100 <= 14:
        return f"{count} notowania w wybranym zakresie"
    return f"{count} notowań w wybranym zakresie"


def _otf_requirements(contracts: ContractSet, market: str) -> dict[str, list[str]]:
    prefix = "gas_base" if market == "gas" else "power_base"
    return {
        group: [
            f"{prefix}_{group}_{index}"
            for index in range(1, len(instruments) + 1)
        ]
        for group, instruments in (
            ("week", contracts.weeks),
            ("month", contracts.months),
            ("quarter", contracts.quarters),
            ("year", contracts.years),
        )
    }


def assess_coverage(
    workbook_path: Path,
    rdn_missing: dict[str, list[date]],
    otf_session_date: date,
    coal_window: tuple[date, date],
    eua_window: tuple[date, date],
) -> CoverageResult:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    details: dict[str, str] = {}
    is_complete = True
    section_complete = {}
    try:
        for key, label in (
            ("gas_rdn", "gaz"),
            ("electricity_rdn", "energia"),
        ):
            count = len(rdn_missing[key])
            details[key] = (
                "kompletne"
                if count == 0
                else f"brakuje {_day_count_text(count)} do pobrania"
            )
            section_complete[key] = count == 0
            is_complete &= count == 0

        contracts = {
            "gas_otf": ("GAZ_OTF", "gas"),
            "electricity_otf": ("EE_OTF", "electricity"),
        }
        group_labels = {
            "week": "tygodniowe",
            "month": "miesięczne",
            "quarter": "kwartalne",
            "year": "roczne",
        }
        for key, (sheet_name, market) in contracts.items():
            worksheet = workbook[sheet_name]
            headers = [
                cell.value
                for cell in next(worksheet.iter_rows(min_row=1, max_row=1))
            ]
            date_column = headers.index("trading_date")
            id_column = headers.index("data_id")
            stored_ids = {
                str(row[id_column])
                for row in worksheet.iter_rows(min_row=2, values_only=True)
                if _date_text(row[date_column]) == otf_session_date.isoformat()
                and row[id_column]
                and valid_tge_record(dict(zip(headers, row)), market, "futures")
            }
            requirements = _otf_requirements(
                build_contract_set(otf_session_date, gas=market == "gas"), market
            )
            all_ids = {row[id_column] for row in worksheet.iter_rows(min_row=2, values_only=True)
                       if _date_text(row[date_column]) == otf_session_date.isoformat()}
            invalid_ids = all_ids.intersection({item for ids in requirements.values() for item in ids}) - stored_ids
            group_status = []
            market_complete = True
            for group, ids in requirements.items():
                available = len(stored_ids.intersection(ids))
                required = OTF_MINIMUM_COUNTS[group]
                group_status.append(
                    f"{group_labels[group]} — dostępne: {available}, "
                    f"wymagane minimum: {required}"
                )
                market_complete &= available >= required
            if invalid_ids:
                market_complete = False
                group_status.append(f"rekordy wymagające poprawy: {len(invalid_ids)}")
            details[key] = ", ".join(group_status)
            section_complete[key] = market_complete
            is_complete &= market_complete

        for key, sheet_name, window in (
            ("coal", "WEGIEL", coal_window),
            ("emissions", "EUA", eua_window),
        ):
            worksheet = workbook[sheet_name]
            headers = [
                cell.value
                for cell in next(worksheet.iter_rows(min_row=1, max_row=1))
            ]
            date_column = headers.index("trading_date")
            expected_id, expected_name = INVESTING_INSTRUMENTS[key]
            candidates = []
            for row in worksheet.iter_rows(min_row=2, values_only=True):
                text = _date_text(row[date_column])
                if text and _valid_date(text) and window[0] <= date.fromisoformat(text) <= window[1]:
                    candidates.append(dict(zip(headers, row)))
            valid_records = [record for record in candidates
                             if record.get("data_id") == expected_id
                             and record.get("instrument") == expected_name
                             and valid_values(record, "price", ("open", "high", "low", "volume", "change_pct"))]
            dates = {_date_text(record["trading_date"]) for record in valid_records}
            invalid_count = len(candidates) - len(valid_records)
            details[key] = (
                _observation_count_text(len(dates))
                if dates
                else "brak notowań w wybranym zakresie"
            )
            if invalid_count:
                details[key] += f"; rekordy wymagające poprawy: {invalid_count}"
            section_complete[key] = bool(dates) and invalid_count == 0
            is_complete &= section_complete[key]
    finally:
        workbook.close()
    return CoverageResult(is_complete, details, section_complete)
