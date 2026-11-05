from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from datetime import timedelta

from openpyxl import Workbook

from generate_market_dashboard import SHEETS, load_dashboard_data, render_dashboard


class MarketDashboardTests(unittest.TestCase):
    def setUp(self) -> None:
        def rates(currency, start, end):
            values=[]
            day=start
            while day<=end:
                if day.weekday()<5:
                    values.append({"effectiveDate":day.isoformat(),"mid":4 if currency=="EUR" else 3.5,"no":"test/A/NBP"})
                day+=timedelta(days=1)
            return values
        patcher=patch("exchange_rates.fetch_rates",side_effect=rates)
        patcher.start()
        self.addCleanup(patcher.stop)

    def create_workbook(self, path: Path) -> None:
        workbook = Workbook()
        workbook.remove(workbook.active)
        for key, (sheet_name, fields) in SHEETS.items():
            worksheet = workbook.create_sheet(sheet_name)
            worksheet.append(
                [
                    "trading_date",
                    "data_id",
                    "source_url",
                    "instrument",
                    *fields[3:],
                    "retrieved_at",
                ]
            )
            value_fields = fields[3:-1] if fields[-1] == "retrieved_at" else fields[3:]
            values = {
                "price_pln_mwh": 100.5,
                "volume_mwh": 250,
                "change_pct": 1.2,
                "dkr_pln_mwh": 101.0,
                "max_pln_mwh": 103.0,
                "price": "95.25",
                "open": "94.00",
                "high": "96.00",
                "low": "93.50",
                "volume": "10.0K",
            }
            row = [
                date(2026, 11, 2),
                f"{key}_id",
                "https://example.test/data",
                "Test instrument",
                *(values[field] for field in value_fields),
                "2026-11-03T10:00:00+01:00",
            ]
            worksheet.append(row)
        workbook.save(path)
        workbook.close()

    def test_load_dashboard_data_reads_latest_workbook_rows(self) -> None:
        with TemporaryDirectory() as directory:
            workbook_path = Path(directory) / "sample.xlsx"
            self.create_workbook(workbook_path)

            data = load_dashboard_data(workbook_path)

        self.assertEqual(data["min_date"], "2026-11-02")
        self.assertEqual(data["max_date"], "2026-11-02")
        self.assertEqual(data["gas_rdn"][0]["price_pln_mwh"], 100.5)
        self.assertEqual(data["coal"][0]["volume"], "10.0K")
        self.assertEqual(data["coal"][0]["price"], 95.25 * 3.5)
        self.assertEqual(data["eua"][0]["price"], 95.25 * 4)
        self.assertEqual(data["coal"][0]["source_values"]["price"], "95.25")
        self.assertEqual(data["biomass_transactions"], [])

    def test_real_biomass_replaces_demonstration_data(self) -> None:
        from biomass_data import save_transactions, validate_response
        from test_biomass import valid_response
        with TemporaryDirectory() as directory:
            workbook_path=Path(directory)/"sample.xlsx"
            self.create_workbook(workbook_path)
            response=validate_response(json.dumps(valid_response()),date(2026,10,7),date(2026,11,5))
            save_transactions(workbook_path,response.records)
            data=load_dashboard_data(workbook_path)
            self.assertEqual(len(data["biomass_transactions"]),1)
            self.assertEqual(data["biomass_transactions"][0]["price_pln_t"],150)
            self.assertEqual(data["biomass_transactions"][0]["record_type"],"tender_award")
            self.assertNotIn("sample_biomass",data)

    def test_rendered_html_is_self_contained_and_embeds_excel_data(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            workbook_path = root / "sample.xlsx"
            template_path = Path("market_dashboard_template.html")
            output_path = root / "dashboard.html"
            self.create_workbook(workbook_path)

            render_dashboard(workbook_path, template_path, output_path)

            html = output_path.read_text(encoding="utf-8")

        self.assertIn("@page { size: A4 landscape;", html)
        self.assertIn("grid-template-columns: repeat(12, minmax(0, 1fr));", html)
        self.assertIn("Chart.js v4.5.1", html)
        self.assertIn(".history-table tbody tr:nth-child(n+6) { display: table-row; }", html)
        self.assertIn('classList.add("history-table")', html)
        self.assertIn('id="report-date"', html)
        self.assertIn("Notowania i trendy", html)
        self.assertIn("--navy: #102338", html)
        self.assertIn("grid-column: span 2;", html)
        self.assertIn("table { font-size: 5.3pt; }", html)
        self.assertIn('content: counter(market, decimal-leading-zero)', html)
        self.assertIn('otfKey:"power_otf",otfPrefix:"power_base",contractPrefix:"BASE_"', html)
        self.assertIn('contractPrefix:"GAS_BASE_"', html)
        self.assertIn('label:"Wolumen",unit:"(MWh)"', html)
        self.assertIn("const split=Math.ceil(rows.length/2);", html)
        self.assertNotIn("__DASHBOARD_DATA__", html)
        self.assertNotIn("__CHARTJS_SCRIPT__", html)
        data_text = html.split('<script id="dashboard-data" type="application/json">', 1)[1]
        data_text = data_text.split("</script>", 1)[0]
        data = json.loads(data_text)
        self.assertEqual(data["power_otf"][0]["trading_date"], "2026-11-02")
        self.assertNotIn("Przykładowy odbiorca", html)


if __name__ == "__main__":
    unittest.main()
