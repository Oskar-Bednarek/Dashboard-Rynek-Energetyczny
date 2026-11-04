from copy import deepcopy
from datetime import date
import json
import unittest

from contract_selection import build_contract_set
from json_validator import parse_json_response, validate_payload, validate_response
from manual_completion import find_missing_tge_records


SESSION_DATE = date(2026, 10, 21)
EARLIER_SESSION_DATE = date(2026, 10, 20)
OTF_CANDIDATES = [SESSION_DATE, EARLIER_SESSION_DATE]
SOURCE_DATES = {
    "gas_rdn": [date(2026, 10, 20)],
    "electricity_rdn": [date(2026, 10, 20)],
    "gas_otf": [SESSION_DATE],
    "electricity_otf": [SESSION_DATE],
}
WINDOW = (date(2026, 9, 23), date(2026, 10, 22))


def _otf_records(market: str, session_date: date = SESSION_DATE) -> list[dict]:
    gas = market == "gas"
    contracts = build_contract_set(session_date, gas=gas)
    prefix = "gas_base" if gas else "power_base"
    url = (
        "https://tge.pl/gaz-otf?dateShow="
        if gas
        else "https://tge.pl/energia-elektryczna-otf?dateShow="
    )
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
                    "source_url": f"{url}{session_date.strftime('%d-%m-%Y')}",
                    "trading_date": session_date.isoformat(),
                    "instrument": instrument,
                    "values": {"dkr_pln_mwh": 1.0, "max_pln_mwh": 2.0, "volume_mwh": None},
                }
            )
    return records


def valid_payload(session_date: date = SESSION_DATE) -> dict:
    power = {
        "tge_power_da_base": "TGeBase",
        "tge_power_da_peak": "TGePeak",
        "tge_power_da_offpeak": "TGeOffpeak",
        "tge_power_da_24": "TGe24",
    }
    return {
        "schema_version": "market-data-1.0",
        "retrieved_at": "2026-10-22T12:00:00+02:00",
        "otf_session_date": session_date.isoformat(),
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
                "futures": _otf_records("gas", session_date),
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
                "futures": _otf_records("electricity", session_date),
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
        return validate_payload(
            payload,
            SOURCE_DATES,
            SESSION_DATE,
            WINDOW,
            WINDOW,
            OTF_CANDIDATES,
        )

    def test_valid_payload_passes(self) -> None:
        report = self.validate(valid_payload())
        self.assertTrue(report.is_valid, report.issues)
        self.assertTrue(all(report.section_validity.values()))

    def test_earlier_candidate_is_validated_using_its_contracts(self) -> None:
        payload = valid_payload(EARLIER_SESSION_DATE)

        report = self.validate(payload)

        self.assertTrue(report.is_valid, report.issues)
        self.assertEqual(
            payload["data"]["gas"]["futures"][0]["trading_date"],
            EARLIER_SESSION_DATE.isoformat(),
        )

    def test_otf_date_outside_candidate_list_is_rejected(self) -> None:
        payload = deepcopy(valid_payload())
        payload["otf_session_date"] = "2026-10-19"

        report = self.validate(payload)

        self.assertFalse(report.is_structurally_valid)
        self.assertTrue(
            any(
                issue.path == "otf_session_date"
                and "kandydatów" in issue.message
                for issue in report.issues
            )
        )

    def test_null_otf_date_blocks_both_otf_sections(self) -> None:
        payload = deepcopy(valid_payload())
        payload["otf_session_date"] = None
        payload["data"]["gas"]["futures"] = []
        payload["data"]["electricity"]["futures"] = []
        payload["status"] = "partial"
        payload["errors"] = [{
            "section": "OTF",
            "source_url": "https://tge.pl/gaz-otf?dateShow=21-10-2026",
            "message": "Nie udało się potwierdzić wspólnej daty.",
        }]

        report = self.validate(payload)

        self.assertTrue(report.is_structurally_valid, report.issues)
        self.assertFalse(report.section_validity["gas.futures"])
        self.assertFalse(report.section_validity["electricity.futures"])
        self.assertEqual(
            find_missing_tge_records(payload, SOURCE_DATES, None),
            [],
        )

    def test_otf_trading_date_must_not_be_inferred_from_url(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["futures"][0]["trading_date"] = (
            EARLIER_SESSION_DATE.isoformat()
        )
        report = self.validate(payload)
        self.assertFalse(report.section_validity["gas.futures"])

    def test_otf_source_url_must_be_one_of_the_candidate_links(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["futures"][0]["source_url"] += "&unexpected=1"

        report = self.validate(payload)

        self.assertFalse(report.section_validity["gas.futures"])

        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["futures"][0]["source_url"] = (
            "https://tge.pl/gaz-otf?dateShow=20-10-2026"
        )
        report = self.validate(payload)
        self.assertFalse(report.section_validity["gas.futures"])

    def test_manual_otf_completion_uses_payload_session_date(self) -> None:
        payload = valid_payload(EARLIER_SESSION_DATE)
        payload["data"]["gas"]["futures"] = [
            record
            for record in payload["data"]["gas"]["futures"]
            if record["data_id"] not in {"gas_base_week_1", "gas_base_week_2"}
        ]

        missing = find_missing_tge_records(
            payload, SOURCE_DATES, date.fromisoformat(payload["otf_session_date"])
        )
        gas_missing = [record for record in missing if record.section == "gas.futures"]

        self.assertEqual(len(gas_missing), 1)
        self.assertEqual(gas_missing[0].trading_date, EARLIER_SESSION_DATE.isoformat())
        self.assertEqual(
            gas_missing[0].source_url,
            "https://tge.pl/gaz-otf?dateShow=20-10-2026",
        )
        self.assertEqual(
            gas_missing[0].instrument,
            build_contract_set(EARLIER_SESSION_DATE, gas=True).weeks[0],
        )

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
            OTF_CANDIDATES,
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

    def test_electricity_non_base_indices_are_required_only_for_latest_date(self) -> None:
        payload = deepcopy(valid_payload())
        dates = [date(2026, 10, 20), date(2026, 10, 21), date(2026, 10, 22)]
        base_record = next(
            record
            for record in payload["data"]["electricity"]["day_ahead"]
            if record["data_id"] == "tge_power_da_base"
        )
        for trading_date in dates[1:]:
            record = deepcopy(base_record)
            record["trading_date"] = trading_date.isoformat()
            record["source_url"] = (
                f"https://tge.pl/energia-elektryczna-rdn"
                f"?dateShow={trading_date.strftime('%d-%m-%Y')}"
            )
            payload["data"]["electricity"]["day_ahead"].append(record)
        payload["data"]["electricity"]["day_ahead"] = [
            record
            for record in payload["data"]["electricity"]["day_ahead"]
            if record["data_id"] == "tge_power_da_base"
        ]
        for data_id, instrument in (
            ("tge_power_da_peak", "TGePeak"),
            ("tge_power_da_offpeak", "TGeOffpeak"),
            ("tge_power_da_24", "TGe24"),
        ):
            payload["data"]["electricity"]["day_ahead"].append({
                "data_id": data_id,
                "source_url": "https://tge.pl/energia-elektryczna-rdn?dateShow=22-10-2026",
                "trading_date": dates[-1].isoformat(),
                "instrument": instrument,
                "values": {"price_pln_mwh": 200.0},
            })

        report = validate_payload(
            payload,
            {**SOURCE_DATES, "electricity_rdn": dates},
            SESSION_DATE,
            WINDOW,
            WINDOW,
        )

        self.assertTrue(report.is_valid, report.issues)

    def test_latest_non_base_electricity_index_is_still_required(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["electricity"]["day_ahead"] = [
            record
            for record in payload["data"]["electricity"]["day_ahead"]
            if record["data_id"] != "tge_power_da_peak"
        ]

        report = self.validate(payload)

        self.assertFalse(report.section_validity["electricity.day_ahead"])
        self.assertTrue(any("tge_power_da_peak" in issue.message for issue in report.issues))

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

    def test_reported_source_error_is_informational(self) -> None:
        payload = deepcopy(valid_payload())
        payload["status"] = "partial"
        payload["errors"] = [{
            "section": "coal.futures",
            "source_url": "https://www.investing.com/commodities/rotterdam-coal-futures-historical-data",
            "message": "Nie odczytano całej tabeli.",
        }]
        report = self.validate(payload)
        self.assertTrue(report.section_validity["coal.futures"])
        self.assertTrue(report.section_validity["emissions.futures"])
        self.assertTrue(report.is_valid, report.issues)

    def test_known_error_sections_are_informational(self) -> None:
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
        self.assertTrue(report.section_validity["coal.futures"])
        self.assertTrue(report.section_validity["emissions.futures"])
        self.assertTrue(report.is_valid, report.issues)
        self.assertFalse(any(
            issue.section == "global" and "Nieznana sekcja" in issue.message
            for issue in report.issues
        ))

    def test_free_form_error_section_does_not_invalidate_payload(self) -> None:
        payload = deepcopy(valid_payload())
        payload["status"] = "partial"
        payload["errors"] = [{
            "section": "ENERGIA ELEKTRYCZNA OTF — BASE_M-11-26",
            "source_url": "https://tge.pl/energia-elektryczna-otf?dateShow=21-10-2026",
            "message": "Nie znaleziono kontraktu w tabeli.",
        }]

        report = self.validate(payload)

        self.assertTrue(report.is_valid, report.issues)
        self.assertTrue(report.section_validity["electricity.futures"])

    def test_missing_month_contract_is_tolerated_when_buffer_is_available(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["futures"] = [
            record
            for record in payload["data"]["gas"]["futures"]
            if record["data_id"] != "gas_base_month_1"
        ]

        report = self.validate(payload)

        self.assertTrue(report.is_valid, report.issues)
        self.assertTrue(report.section_validity["gas.futures"])

    def test_missing_week_contract_is_tolerated(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["futures"] = [
            record
            for record in payload["data"]["gas"]["futures"]
            if record["data_id"] != "gas_base_week_1"
        ]

        report = self.validate(payload)

        self.assertTrue(report.is_valid, report.issues)
        self.assertTrue(report.section_validity["gas.futures"])

    def test_two_missing_month_contracts_fail_validation(self) -> None:
        payload = deepcopy(valid_payload())
        payload["data"]["gas"]["futures"] = [
            record
            for record in payload["data"]["gas"]["futures"]
            if record["data_id"] not in {"gas_base_month_1", "gas_base_month_5"}
        ]

        report = self.validate(payload)

        self.assertFalse(report.section_validity["gas.futures"])
        self.assertTrue(
            any("Brak wymaganego kontraktu" in issue.message for issue in report.issues)
        )

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
