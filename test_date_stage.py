from datetime import date, datetime, timezone
from pathlib import Path
import unittest

from contract_selection import build_contract_set
from date_stage import (
    build_date_plan,
    get_dates_between,
    get_otf_session_candidates,
    select_latest_otf_session,
)
from prompt_stage import build_prompt


class DateStageTests(unittest.TestCase):
    def test_rdn_includes_weekends(self) -> None:
        result = get_dates_between(date(2026, 10, 15), date(2026, 10, 19))
        self.assertEqual(
            result,
            [date(2026, 10, 16), date(2026, 10, 17), date(2026, 10, 18), date(2026, 10, 19)],
        )

    def test_otf_uses_only_latest_non_holiday_weekday(self) -> None:
        candidates = get_otf_session_candidates(date(2026, 10, 26))
        result = select_latest_otf_session(
            candidates,
            [date(2026, 10, 23)],
        )
        self.assertEqual(result, date(2026, 10, 22))

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
        self.assertEqual(plan.coal_window, (date(2026, 9, 23), date(2026, 10, 22)))

    def test_both_empty_rdn_sources_get_last_7_days(self) -> None:
        plan = build_date_plan(
            {"gas_rdn": None, "electricity_rdn": None},
            date(2026, 10, 22),
        )
        expected = get_dates_between(date(2026, 10, 14), date(2026, 10, 21))
        self.assertEqual(len(expected), 7)
        self.assertEqual(plan.rdn_dates["gas_rdn"], expected)
        self.assertEqual(plan.rdn_dates["electricity_rdn"], expected)

    def test_existing_rdn_gap_requests_all_missing_dates(self) -> None:
        plan = build_date_plan(
            {
                "gas_rdn": date(2026, 10, 1),
                "electricity_rdn": date(2026, 10, 1),
            },
            date(2026, 10, 22),
        )
        self.assertEqual(
            plan.rdn_dates["gas_rdn"],
            [date(2026, 10, day) for day in range(2, 22)],
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
            ),
        )
        self.assertEqual(gas.quarters, ("GAS_BASE_Q-1-27", "GAS_BASE_Q-2-27"))
        self.assertEqual(gas.years, ("GAS_BASE_Y-27",))
        self.assertEqual(power.weeks[0], "BASE_W-44-26")

    def test_prompt_receives_dates_links_and_contracts(self) -> None:
        template = Path("prompt_template.txt").read_text(encoding="utf-8")
        prompt = build_prompt(
            template,
            source_dates={
                "gas_rdn": [date(2026, 10, 20), date(2026, 10, 21)],
                "electricity_rdn": [date(2026, 10, 21)],
                "gas_otf": [date(2026, 10, 21)],
                "electricity_otf": [date(2026, 10, 21)],
            },
            otf_session_date=date(2026, 10, 21),
            coal_window=(date(2026, 9, 23), date(2026, 10, 22)),
            eua_window=(date(2026, 9, 23), date(2026, 10, 22)),
            retrieved_at=datetime(2026, 10, 22, 12, 0, tzinfo=timezone.utc),
        )
        self.assertNotIn("{{", prompt)
        self.assertIn("gaz-rdn?dateShow=20-10-2026", prompt)
        self.assertIn("energia-elektryczna-rdn?dateShow=21-10-2026", prompt)
        self.assertIn("gaz-otf?dateShow=21-10-2026", prompt)
        self.assertIn("GAS_BASE_W-45-26", prompt)
        self.assertIn("BASE_M-11-26", prompt)
        self.assertIn("2026-09-23–2026-10-22", prompt)


if __name__ == "__main__":
    unittest.main()
