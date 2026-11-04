from datetime import date
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook

from generate_market_dashboard import SHEETS, load_dashboard_data, render_dashboard


class MarketDashboardTests(unittest.TestCase):
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
        self.assertEqual(data["sample_biomass"][0]["source"], "Dane demonstracyjne")

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
        self.assertIn("Premium energy intelligence", html)
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
        self.assertIn("Dane demonstracyjne", html)


if __name__ == "__main__":
    unittest.main()
