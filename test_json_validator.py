from copy import deepcopy
from datetime import date
import json
import unittest

from contract_selection import build_contract_set
from json_validator import parse_json_response, validate_payload, validate_response


SESSION_DATE = date(2026, 10, 21)
SOURCE_DATES = {
    "gas_rdn": [date(2026, 10, 20)],
    "electricity_rdn": [date(2026, 10, 20)],
    "gas_otf": [SESSION_DATE],
    "electricity_otf": [SESSION_DATE],
}
WINDOW = (date(2026, 9, 23), date(2026, 10, 22))


def _otf_records(market: str) -> list[dict]:
    gas = market == "gas"
    contracts = build_contract_set(SESSION_DATE, gas=gas)
    prefix = "gas_base" if gas else "power_base"
    records = []
    for group, values in (
        ("week", contracts.weeks),
        ("month", contracts.months),
        ("quarter", contracts.quarters),
        ("year", contracts.years),
    ):
        for index, instrument in enumerate(values, 1):
            records.append(
                {
                    "data_id": f"{prefix}_{group}_{index}",
                    "source_url": (
                        "https://tge.pl/gaz-otf?dateShow=21-10-2026"
                        if gas
                        else "https://tge.pl/energia-elektryczna-otf?dateShow=21-10-2026"
                    ),
                    "trading_date": SESSION_DATE.isoformat(),
                    "instrument": instrument,
                    "values": {"dkr_pln_mwh": 1.0, "max_pln_mwh": 2.0, "volume_mwh": None},
                }
            )
    return records


def valid_payload() -> dict:
    power = {
        "tge_power_da_base": "TGeBase",
        "tge_power_da_peak": "TGePeak",
        "tge_power_da_offpeak": "TGeOffpeak",
        "tge_power_da_24": "TGe24",
    }
    return {
        "schema_version": "market-data-1.0",
        "retrieved_at": "2026-10-22T12:00:00+02:00",
        "status": "success",
        "data": {
            "gas": {
                "day_ahead": [{
                    "data_id": "tge_gas_da",
                    "source_url": "https://tge.pl/gaz-rdn?dateShow=20-10-2026",
                    "trading_date": "2026-10-20",
                    "instrument": "TGEgasDA",
                    "values": {"price_pln_mwh": 100.0, "volume_mwh": 20.0, "change_pct": -1.2},
                }],
                "futures": _otf_records("gas"),
            },
            "electricity": {
                "day_ahead": [
                    {
                        "data_id": data_id,
                        "source_url": "https://tge.pl/energia-elektryczna-rdn?dateShow=20-10-2026",
                        "trading_date": "2026-10-20",
                        "instrument": instrument,
                        "values": {"price_pln_mwh": 200.0, "volume_mwh": None, "change_pct": 0.5},
                    }
                    for data_id, instrument in power.items()
                ],
                "futures": _otf_records("electricity"),
            },
            "coal": {"futures": [{
                "data_id": "coal_rotterdam_futures",
                "source_url": "https://www.investing.com/commodities/rotterdam-coal-futures-historical-data",
                "trading_date": "2026-10-20",
                "instrument": "Rotterdam Coal Futures",
                "values": {"price": "101.20", "open": "100.00", "high": "102.00", "low": "99.00", "volume": "1.2K", "change_pct": "+1.20%"},
            }]},
            "emissions": {"futures": [{
                "data_id": "eua_year_futures",
                "source_url": "https://www.investing.com/commodities/european-union-allowance-eua-year-futures-historical-data",
                "trading_date": "2026-10-20",
                "instrument": "European Union Allowance (EUA) Year Futures",
                "values": {"price": "80.20", "open": "80.00", "high": "81.00", "low": "79.00", "volume": "10.2K", "change_pct": "+0.25%"},
            }]},
        },
        "errors": [],
    }


class JsonValidatorTests(unittest.TestCase):
    def validate(self, payload: dict):
        return validate_payload(payload, SOURCE_DATES, SESSION_DATE, WINDOW, WINDOW)

    def test_valid_payload_passes(self) -> None:
        report = self.validate(valid_payload())
        self.assertTrue(report.is_valid, report.issues)
        self.assertTrue(all(report.section_validity.values()))

    def test_fenced_json_is_accepted(self) -> None:
        text = "```json\n" + json.dumps(valid_payload()) + "\n```"
        parsed = parse_json_response(text)
        self.assertEqual(parsed["schema_version"], "market-data-1.0")

    def test_surrounding_text_is_rejected(self) -> None:
        report = validate_response(
            "Oto dane: " + json.dumps(valid_payload()),
            SOURCE_DATES,
            SESSION_DATE,
            WINDOW,
            WINDOW,
        )
        self.assertIsNone(report.data)
        self.assertFalse(report.is_valid)

    def test_tge_text_number_is_rejected_in_its_section(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["day_ahead"][0]["values"]["price_pln_mwh"] = "100.0"
        report = self.validate(payload)
        self.assertFalse(report.section_validity["gas.day_ahead"])
        self.assertTrue(report.section_validity["electricity.day_ahead"])

    def test_investing_date_outside_window_is_rejected(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["coal"]["futures"][0]["trading_date"] = "2026-09-22"
        report = self.validate(payload)
        self.assertFalse(report.section_validity["coal.futures"])

    def test_wrong_rdn_date_in_source_url_is_rejected(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["day_ahead"][0]["source_url"] = (
            "https://tge.pl/gaz-rdn?dateShow=19-10-2026"
        )
        report = self.validate(payload)
        self.assertFalse(report.section_validity["gas.day_ahead"])

    def test_missing_otf_section_keeps_other_sections_usable(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["futures"] = []
        payload["status"] = "partial"
        payload["errors"] = [{
            "section": "gas.futures",
            "source_url": "https://tge.pl/gaz-otf?dateShow=21-10-2026",
            "message": "Nie odczytano tabeli kontraktów.",
        }]
        report = self.validate(payload)
        self.assertFalse(report.is_valid)
        self.assertTrue(report.is_usable)
        self.assertFalse(report.section_validity["gas.futures"])
        self.assertTrue(report.section_validity["electricity.futures"])

    def test_reported_source_error_invalidates_its_section(self) -> None:
        payload = deepcopy(valid_payload())
        payload["status"] = "partial"
        payload["errors"] = [{
            "section": "coal.futures",
            "source_url": "https://www.investing.com/commodities/rotterdam-coal-futures-historical-data",
            "message": "Nie odczytano całej tabeli.",
        }]
        report = self.validate(payload)
        self.assertFalse(report.section_validity["coal.futures"])
        self.assertTrue(report.section_validity["emissions.futures"])
        self.assertTrue(report.is_usable)

    def test_error_section_aliases_are_normalized(self) -> None:
        payload = deepcopy(valid_payload())
        payload["status"] = "partial"
        payload["errors"] = [
            {
                "section": "coal",
                "source_url": "https://www.investing.com/commodities/rotterdam-coal-futures-historical-data",
                "message": "Brak dzisiejszej sesji.",
            },
            {
                "section": "eua",
                "source_url": "https://www.investing.com/commodities/european-union-allowance-eua-year-futures-historical-data",
                "message": "Brak dzisiejszej sesji.",
            },
        ]
        report = self.validate(payload)
        self.assertFalse(report.section_validity["coal.futures"])
        self.assertFalse(report.section_validity["emissions.futures"])
        self.assertFalse(any(
            issue.section == "global" and "Nieznana sekcja" in issue.message
            for issue in report.issues
        ))

    def test_empty_sections_keep_valid_json_structure(self) -> None:
        payload = deepcopy(valid_payload())
        for market in ("gas", "electricity"):
            payload["data"][market]["day_ahead"] = []
            payload["data"][market]["futures"] = []
        payload["status"] = "partial"
        payload["errors"] = [
            {
                "section": "gas.day_ahead",
                "source_url": "https://tge.pl/gaz-rdn?dateShow=20-10-2026",
                "message": "Nie odczytano danych.",
            },
            {
                "section": "gas.futures",
                "source_url": "https://tge.pl/gaz-otf?dateShow=21-10-2026",
                "message": "Nie odczytano danych.",
            },
            {
                "section": "electricity.day_ahead",
                "source_url": "https://tge.pl/energia-elektryczna-rdn?dateShow=20-10-2026",
                "message": "Nie odczytano danych.",
            },
            {
                "section": "electricity.futures",
                "source_url": "https://tge.pl/energia-elektryczna-otf?dateShow=21-10-2026",
                "message": "Nie odczytano danych.",
            },
        ]
        report = self.validate(payload)
        self.assertTrue(report.is_structurally_valid)
        self.assertFalse(report.is_valid)


if __name__ == "__main__":
    unittest.main()
