from datetime import date, datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from contract_selection import build_contract_set
from date_stage import (
    RDN_LOOKBACK_DAYS,
    OTF_CANDIDATE_COUNT,
    build_date_plan,
    build_otf_contract_preview,
    get_dates_between,
    get_otf_session_candidates,
    load_date_plan,
    validate_otf_session_choice,
)
from prompt_stage import build_prompt


class DateStageTests(unittest.TestCase):
    def test_rdn_includes_weekends(self) -> None:
        result = get_dates_between(date(2026, 10, 15), date(2026, 10, 19))
        self.assertEqual(
            result,
            [date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 18), date(2026, 10, 19)],
        )

    def test_otf_shows_five_most_recent_weekdays(self) -> None:
        candidates = get_otf_session_candidates(date(2026, 10, 26))
        self.assertEqual(OTF_CANDIDATE_COUNT, 5)
        self.assertEqual(
            candidates,
            [
                date(2026, 10, 23),
                date(2026, 10, 22),
                date(2026, 10, 21),
                date(2026, 10, 20),
                date(2026, 10, 19),
            ],
        )
        self.assertEqual(
            validate_otf_session_choice(candidates, date(2026, 10, 20)),
            date(2026, 10, 20),
        )
        with self.assertRaises(ValueError):
            validate_otf_session_choice(candidates, date(2026, 10, 18))

    def test_rdn_requests_only_last_seven_calendar_days(self) -> None:
        plan = build_date_plan(
            {
                "gas_rdn": date(2026, 10, 1),
                "electricity_rdn": date(2026, 10, 1),
            },
            date(2026, 10, 22),
        )

        expected = [
            date(2026, 10, day)
            for day in range(15, 22)
        ]
        self.assertEqual(RDN_LOOKBACK_DAYS, 30)
        self.assertEqual(plan.rdn_dates["gas_rdn"], expected)
        self.assertEqual(plan.rdn_dates["electricity_rdn"], expected)

    def test_empty_rdn_source_gets_last_7_days(self) -> None:
        plan = build_date_plan(
            {
                "gas_rdn": date(2026, 10, 15),
                "electricity_rdn": None,
            },
            date(2026, 10, 22),
        )
        self.assertEqual(
            plan.effective_latest_rdn_dates["electricity_rdn"],
            date(2026, 10, 14),
        )
        self.assertTrue(plan.used_fallback["electricity_rdn"])
        self.assertEqual(
            plan.rdn_dates["gas_rdn"],
            [date(2026, 10, day) for day in range(16, 22)],
        )
        self.assertEqual(
            plan.rdn_dates["electricity_rdn"],
            get_dates_between(date(2026, 10, 14), date(2026, 10, 21)),
        )
        self.assertEqual(plan.coal_window, (date(2026, 9, 22), date(2026, 10, 21)))

    def test_both_empty_rdn_sources_get_last_7_days(self) -> None:
        plan = build_date_plan(
            {"gas_rdn": None, "electricity_rdn": None},
            date(2026, 10, 22),
        )
        expected = get_dates_between(date(2026, 10, 14), date(2026, 10, 21))
        self.assertEqual(len(expected), 7)
        self.assertEqual(plan.rdn_dates["gas_rdn"], expected)
        self.assertEqual(plan.rdn_dates["electricity_rdn"], expected)

    def test_existing_rdn_gap_is_capped_to_last_seven_calendar_days(self) -> None:
        plan = build_date_plan(
            {
                "gas_rdn": date(2026, 10, 1),
                "electricity_rdn": date(2026, 10, 1),
            },
            date(2026, 10, 22),
        )
        self.assertEqual(
            plan.rdn_dates["gas_rdn"],
            [date(2026, 10, day) for day in range(15, 22)],
        )

    def test_previous_day_already_present_produces_no_rdn_request(self) -> None:
        plan = build_date_plan(
            {
                "gas_rdn": date(2026, 10, 21),
                "electricity_rdn": date(2026, 10, 21),
            },
            date(2026, 10, 22),
        )
        self.assertEqual(plan.rdn_dates["gas_rdn"], [])
        self.assertEqual(plan.rdn_dates["electricity_rdn"], [])

    def test_load_date_plan_caps_requests_to_last_seven_days(self) -> None:
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "DataMaster.xlsx"
            workbook = Workbook()
            gas = workbook.active
            gas.title = "GAZ_RDN"
            gas.append(["trading_date"])
            gas.append([date(2026, 10, 21)])
            electricity = workbook.create_sheet("EE_RDN")
            electricity.append(["trading_date"])
            electricity.append([date(2026, 10, 21)])
            workbook.save(path)
            workbook.close()

            plan = load_date_plan(path, date(2026, 11, 3))

        expected = [date(2026, 10, day) for day in range(27, 32)] + [
            date(2026, 11, 1),
            date(2026, 11, 2),
        ]
        self.assertEqual(plan.rdn_dates["gas_rdn"], expected)
        self.assertEqual(plan.rdn_dates["electricity_rdn"], expected)
        self.assertEqual(plan.coal_window, (date(2026, 10, 4), date(2026, 11, 2)))

    def test_contracts_follow_configured_offsets(self) -> None:
        gas = build_contract_set(date(2026, 10, 14), gas=True)
        power = build_contract_set(date(2026, 10, 14), gas=False)
        self.assertEqual(
            gas.weeks,
            ("GAS_BASE_W-44-26", "GAS_BASE_W-45-26", "GAS_BASE_W-46-26"),
        )
        self.assertEqual(
            gas.months,
            (
                "GAS_BASE_M-11-26",
                "GAS_BASE_M-12-26",
                "GAS_BASE_M-01-27",
                "GAS_BASE_M-02-27",
                "GAS_BASE_M-03-27",
            ),
        )
        self.assertEqual(
            gas.quarters,
            ("GAS_BASE_Q-1-27", "GAS_BASE_Q-2-27", "GAS_BASE_Q-3-27"),
        )
        self.assertEqual(gas.years, ("GAS_BASE_Y-27", "GAS_BASE_Y-28"))
        self.assertEqual(power.weeks[0], "BASE_W-44-26")

    def test_otf_contract_preview_shows_only_unique_contracts(self) -> None:
        candidates = [date(2026, 10, 21), date(2026, 10, 20)]

        rows = build_otf_contract_preview(candidates)

        self.assertEqual(len(rows), 8)
        self.assertEqual(
            [row["Rodzaj"] for row in rows[:4]],
            ["Tygodniowe", "Miesięczne", "Kwartalne", "Roczne"],
        )
        self.assertTrue(
            all(
                "Data kandydata" not in row and "Identyfikator" not in row
                for row in rows
            )
        )
        for market_rows in (rows[:4], rows[4:]):
            for row in market_rows:
                instruments = row["Przykładowe kontrakty"].split(", ")
                self.assertEqual(len(instruments), len(set(instruments)))

    def test_prompt_receives_dates_links_and_contracts(self) -> None:
        template = Path("prompt_market_data.txt").read_text(encoding="utf-8")
        prompt = build_prompt(
            template,
            source_dates={
                "gas_rdn": [date(2026, 10, 20), date(2026, 10, 21)],
                "electricity_rdn": [date(2026, 10, 21)],
                "gas_otf": [date(2026, 10, 20)],
                "electricity_otf": [date(2026, 10, 20)],
            },
            otf_session_date=date(2026, 10, 20),
            coal_window=(date(2026, 9, 23), date(2026, 10, 22)),
            eua_window=(date(2026, 9, 23), date(2026, 10, 22)),
            retrieved_at=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        )
        self.assertNotIn("{{", prompt)
        self.assertIn("gaz-rdn?dateShow=20-10-2026", prompt)
        self.assertIn("energia-elektryczna-rdn?dateShow=21-10-2026", prompt)
        self.assertIn("gaz-otf?dateShow=20-10-2026", prompt)
        self.assertNotIn("gaz-otf?dateShow=21-10-2026", prompt)
        self.assertIn("GAS_BASE_W-45-26", prompt)
        self.assertIn("BASE_M-11-26", prompt)
        self.assertIn("2026-09-23–2026-10-22", prompt)
        self.assertIn("Użytkownik wybrał datę sesji OTF w aplikacji: 2026-10-20.", prompt)
        self.assertIn("energia-elektryczna-otf?dateShow=20-10-2026", prompt)
        self.assertIn("Nie wybieraj daty samodzielnie ani nie sprawdzaj innych dni.", prompt)
        self.assertIn("Aby potwierdzić datę RDN", prompt)
        self.assertIn("każdy wpis errors dotyczy jednego konkretnego URL-a", prompt)
        self.assertIn("dynamicznie przez JavaScript", prompt)
        self.assertIn("otwórz bezpośrednio dokładny adres", prompt)
        self.assertNotIn("odśwież dokładny URL", prompt)
        self.assertIn("Nie otwieraj ponownie ani nie odświeżaj adresu", prompt)
        self.assertNotIn("właściwości value", prompt)


if __name__ == "__main__":
    unittest.main()
