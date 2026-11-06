from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from contract_selection import build_contract_set
from data_coverage import assess_coverage
from market_values import contract_map, INVESTING_INSTRUMENTS


class DataCoverageTests(unittest.TestCase):
    session_date = date(2026, 10, 30)
    window = (date(2026, 10, 1), date(2026, 10, 30))

    def _create_workbook(
        self, gas_ids: list[str], power_ids: list[str] | None = None
    ) -> Path:
        temporary_directory = TemporaryDirectory()
        self.addCleanup(temporary_directory.cleanup)
        path = Path(temporary_directory.name) / "coverage.xlsx"
        workbook = Workbook()
        workbook.remove(workbook.active)
        ids_by_sheet = {
            "GAZ_OTF": gas_ids,
            "EE_OTF": power_ids if power_ids is not None else gas_ids,
        }
        for sheet_name, ids in ids_by_sheet.items():
            worksheet = workbook.create_sheet(sheet_name)
            worksheet.append(["trading_date", "data_id", "instrument", "dkr_pln_mwh"])
            worksheet.append([self.session_date, "unrelated_id"])
            for data_id in ids:
                market = "gas" if sheet_name == "GAZ_OTF" else "electricity"
                worksheet.append([self.session_date, data_id, contract_map(self.session_date,market).get(data_id), 100])
        for sheet_name in ("WEGIEL", "EUA"):
            worksheet = workbook.create_sheet(sheet_name)
            worksheet.append(["trading_date", "data_id", "instrument", "price"])
            identifier, instrument = INVESTING_INSTRUMENTS["coal" if sheet_name == "WEGIEL" else "emissions"]
            worksheet.append([date(2026, 10, 29),identifier,instrument,"100"])
        workbook.save(path)
        workbook.close()
        return path

    def test_otf_coverage_uses_minimums_for_each_contract_group(self) -> None:
        gas = build_contract_set(self.session_date, gas=True)
        power = build_contract_set(self.session_date, gas=False)
        gas_ids = [
            "gas_base_week_1",
            "gas_base_week_3",
            "gas_base_month_1",
            "gas_base_month_3",
            "gas_base_month_4",
            "gas_base_month_5",
            "gas_base_quarter_1",
            "gas_base_quarter_3",
            "gas_base_year_2",
        ]
        power_ids = [
            "power_base_week_1",
            "power_base_week_3",
            "power_base_month_1",
            "power_base_month_3",
            "power_base_month_4",
            "power_base_month_5",
            "power_base_quarter_1",
            "power_base_quarter_3",
            "power_base_year_2",
        ]
        self.assertEqual(len(gas.weeks), 3)
        self.assertEqual(len(power.years), 2)

        result = assess_coverage(
            self._create_workbook(gas_ids, power_ids),
            {"gas_rdn": [], "electricity_rdn": []},
            self.session_date,
            self.window,
            self.window,
        )

        self.assertTrue(result.complete)
        self.assertIn("tygodniowe — dostępne: 2, wymagane minimum: 2", result.details["gas_otf"])
        self.assertIn("miesięczne — dostępne: 4, wymagane minimum: 4", result.details["gas_otf"])
        self.assertIn("roczne — dostępne: 1, wymagane minimum: 1", result.details["gas_otf"])

        result = assess_coverage(
            self._create_workbook(gas_ids, power_ids),
            {"gas_rdn": [], "electricity_rdn": []},
            self.session_date,
            self.window,
            self.window,
        )
        self.assertTrue(result.complete)
        self.assertIn("roczne — dostępne: 1, wymagane minimum: 1", result.details["electricity_otf"])

    def test_ten_otf_records_do_not_hide_a_missing_group_minimum(self) -> None:
        ids = [
            "gas_base_week_1",
            "gas_base_week_2",
            "gas_base_week_3",
            "gas_base_month_1",
            "gas_base_month_2",
            "gas_base_month_3",
            "gas_base_quarter_1",
            "gas_base_quarter_2",
            "gas_base_quarter_3",
            "gas_base_year_1",
        ]
        result = assess_coverage(
            self._create_workbook(ids),
            {"gas_rdn": [], "electricity_rdn": []},
            self.session_date,
            self.window,
            self.window,
        )

        self.assertFalse(result.complete)
        self.assertIn("miesięczne — dostępne: 3, wymagane minimum: 4", result.details["gas_otf"])
        self.assertIn("kwartalne — dostępne: 3, wymagane minimum: 2", result.details["gas_otf"])

    def test_missing_market_history_is_reported_in_selected_window(self) -> None:
        ids = [
            "gas_base_week_1",
            "gas_base_week_2",
            "gas_base_month_1",
            "gas_base_month_2",
            "gas_base_month_3",
            "gas_base_month_4",
            "gas_base_quarter_1",
            "gas_base_quarter_2",
            "gas_base_year_1",
        ]
        result = assess_coverage(
            self._create_workbook(ids),
            {"gas_rdn": [date(2026, 10, 30)], "electricity_rdn": []},
            self.session_date,
            (date(2026, 11, 1), date(2026, 11, 30)),
            self.window,
        )

        self.assertFalse(result.complete)
        self.assertEqual(result.details["gas_rdn"], "brakuje 1 dzień do pobrania")
        self.assertEqual(result.details["coal"], "brak notowań w wybranym zakresie")
        self.assertEqual(result.details["emissions"], "1 notowanie w wybranym zakresie")


if __name__ == "__main__":
    unittest.main()
