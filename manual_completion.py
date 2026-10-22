from copy import deepcopy
from dataclasses import dataclass
from datetime import date
from typing import Any

from contract_selection import build_contract_set


@dataclass(frozen=True)
class MissingRecord:
    section: str
    trading_date: str
    data_id: str
    instrument: str
    source_url: str
    value_fields: tuple[str, ...]


def _existing_keys(payload: dict[str, Any], market: str, collection: str) -> set[tuple[str, str]]:
    data = payload.get("data")
    if not isinstance(data, dict):
        return set()
    market_data = data.get(market)
    if not isinstance(market_data, dict):
        return set()
    records = market_data.get(collection, [])
    if not isinstance(records, list):
        return set()
    return {
        (record.get("trading_date"), record.get("data_id"))
        for record in records
        if isinstance(record, dict)
    }


def find_missing_tge_records(
    payload: dict[str, Any],
    source_dates: dict[str, list[date]],
    otf_session_date: date,
) -> list[MissingRecord]:
    missing: list[MissingRecord] = []
    rdn_specs = (
        ("gas", "gas_rdn", "/gaz-rdn", {"tge_gas_da": "TGEgasDA"}),
        (
            "electricity",
            "electricity_rdn",
            "/energia-elektryczna-rdn",
            {
                "tge_power_da_base": "TGeBase",
                "tge_power_da_peak": "TGePeak",
                "tge_power_da_offpeak": "TGeOffpeak",
                "tge_power_da_24": "TGe24",
            },
        ),
    )
    for market, source_key, url_path, instruments in rdn_specs:
        existing = _existing_keys(payload, market, "day_ahead")
        for trading_date in source_dates[source_key]:
            text_date = trading_date.isoformat()
            url = f"https://tge.pl{url_path}?dateShow={trading_date.strftime('%d-%m-%Y')}"
            for data_id, instrument in instruments.items():
                if (text_date, data_id) not in existing:
                    missing.append(MissingRecord(
                        f"{market}.day_ahead", text_date, data_id, instrument, url,
                        ("price_pln_mwh", "volume_mwh", "change_pct"),
                    ))

    for market, gas, path, prefix in (
        ("gas", True, "/gaz-otf", "gas_base"),
        ("electricity", False, "/energia-elektryczna-otf", "power_base"),
    ):
        existing = _existing_keys(payload, market, "futures")
        contracts = build_contract_set(otf_session_date, gas=gas)
        url = f"https://tge.pl{path}?dateShow={otf_session_date.strftime('%d-%m-%Y')}"
        for group, values in (
            ("week", contracts.weeks), ("month", contracts.months),
            ("quarter", contracts.quarters), ("year", contracts.years),
        ):
            for index, instrument in enumerate(values, 1):
                data_id = f"{prefix}_{group}_{index}"
                key = (otf_session_date.isoformat(), data_id)
                if key not in existing:
                    missing.append(MissingRecord(
                        f"{market}.futures", key[0], data_id, instrument, url,
                        ("dkr_pln_mwh", "max_pln_mwh", "volume_mwh"),
                    ))
    return missing


def apply_manual_records(
    payload: dict[str, Any],
    records: list[tuple[MissingRecord, dict[str, float | None]]],
) -> dict[str, Any]:
    result = deepcopy(payload)
    data = result.setdefault("data", {})
    for missing, values in records:
        market, collection = missing.section.split(".")
        target = data.setdefault(market, {}).setdefault(collection, [])
        target.append({
            "data_id": missing.data_id,
            "source_url": missing.source_url,
            "trading_date": missing.trading_date,
            "instrument": missing.instrument,
            "values": {field: values.get(field) for field in missing.value_fields},
        })
    result["errors"] = [
        error for error in result.get("errors", [])
        if isinstance(error, dict)
        and error.get("section") not in {record.section for record, _ in records}
    ]
    result["status"] = "success" if not result["errors"] else "partial"
    return result
