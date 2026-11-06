from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from openpyxl import Workbook, load_workbook

from exchange_rates import (
    FX_SHEET, ExchangeRateError, convert_record_to_pln,
    ensure_exchange_rates, read_exchange_rates,
)


class ExchangeRateTests(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "DataMaster.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "WEGIEL"
        sheet.append(["trading_date", "price"])
        sheet.append(["2026-10-30", "100"])
        workbook.save(self.path)
        workbook.close()

    @staticmethod
    def rates(currency, start, end):
        records = []
        day = start
        while day <= end:
            if day.weekday() < 5:
                records.append({"effectiveDate": day.isoformat(), "mid": 4.2 if currency == "EUR" else 3.8, "no": "test/A/NBP"})
            day += timedelta(days=1)
        return records

    def test_calendar_gaps_weekend_fallback_and_source_unchanged(self):
        with patch("exchange_rates.fetch_rates", side_effect=self.rates):
            result = ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        self.assertEqual(len(result), 8)
        self.assertEqual(result[(date(2026, 11, 1), "USD")]["effective_date"], date(2026, 10, 30))
        workbook = load_workbook(self.path)
        self.assertEqual(workbook["WEGIEL"]["B2"].value, "100")
        sheet = workbook[FX_SHEET]
        for row in range(sheet.max_row, 1, -1):
            if sheet.cell(row, 1).value == "2026-10-31":
                sheet.delete_rows(row)
        workbook.save(self.path)
        workbook.close()
        with patch("exchange_rates.fetch_rates", side_effect=self.rates):
            repaired = ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        self.assertEqual(len(repaired), 8)
        before = self.path.read_bytes()
        with patch("exchange_rates.fetch_rates", side_effect=AssertionError("Unexpected network")):
            ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        self.assertEqual(before, self.path.read_bytes())

    def test_failure_preserves_workbook_and_never_invents_rates(self):
        before = self.path.read_bytes()
        with patch("exchange_rates.fetch_rates", side_effect=ExchangeRateError("Network")):
            with self.assertRaises(ExchangeRateError):
                ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        self.assertEqual(before, self.path.read_bytes())
        with patch("exchange_rates.fetch_rates", return_value=[]):
            with self.assertRaises(ExchangeRateError):
                ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        self.assertEqual(before, self.path.read_bytes())

    def test_long_history_uses_at_most_93_day_requests(self):
        workbook = load_workbook(self.path)
        workbook["WEGIEL"]["A2"] = "2025-01-01"
        workbook.save(self.path)
        workbook.close()
        with patch("exchange_rates.fetch_rates", side_effect=self.rates) as fetch:
            result = ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        self.assertGreater(len(result), 1000)
        for call in fetch.call_args_list:
            self.assertLessEqual((call.args[2] - call.args[1]).days + 1, 93)
        self.assertEqual(result[(date(2025, 1, 1), "EUR")]["mid_pln"], 4.2)

    def test_current_day_fallback_is_refreshed_when_nbp_publishes(self):
        def before_publication(currency, start, end):
            return [r for r in self.rates(currency, start, end) if r["effectiveDate"] < "2026-11-02"]
        with patch("exchange_rates.fetch_rates", side_effect=before_publication):
            ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        self.assertEqual(read_exchange_rates(self.path)[(date(2026, 11, 2), "EUR")]["effective_date"], date(2026, 10, 30))
        with patch("exchange_rates.fetch_rates", side_effect=self.rates):
            updated = ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        self.assertEqual(updated[(date(2026, 11, 2), "EUR")]["effective_date"], date(2026, 11, 2))

    def test_conversion_prices_only_and_preserves_provenance(self):
        with patch("exchange_rates.fetch_rates", side_effect=self.rates):
            rates = ensure_exchange_rates(self.path, today=date(2026, 11, 2))
        source = dict(trading_date="2026-11-01", price="100,50", open="99", high="102", low=None, volume="1.32K", change_pct="2%")
        result = convert_record_to_pln(source, "USD", rates)
        self.assertAlmostEqual(result["price"], 381.9)
        self.assertEqual(result["open"], 376.2)
        self.assertEqual(result["volume"], "1.32K")
        self.assertIsNone(result["low"])
        self.assertIsNone(result["change_pct"])
        self.assertEqual(result["source_values"]["price"], "100,50")
        self.assertEqual(result["fx_effective_date"], "2026-10-30")
        self.assertEqual(source["price"], "100,50")
        with self.assertRaises(ExchangeRateError):
            convert_record_to_pln(source, "EUR", {})


if __name__ == "__main__":
    unittest.main()
