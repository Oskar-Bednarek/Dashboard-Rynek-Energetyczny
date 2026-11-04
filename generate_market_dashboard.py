from __future__ import annotations

import argparse
from datetime import date, datetime
import json
from pathlib import Path
from typing import Any

from openpyxl import load_workbook


ROOT = Path(__file__).resolve().parent
DEFAULT_WORKBOOK = ROOT / "DataMaster.xlsx"
DEFAULT_TEMPLATE = ROOT / "market_dashboard_template.html"
DEFAULT_OUTPUT = ROOT / "market_dashboard.html"
CHARTJS_SCRIPT = ROOT / "vendor" / "chart.umd.min.js"

SHEETS = {
    "gas_rdn": ("GAZ_RDN", ("trading_date", "data_id", "instrument", "price_pln_mwh", "volume_mwh", "change_pct", "retrieved_at")),
    "gas_otf": ("GAZ_OTF", ("trading_date", "data_id", "instrument", "dkr_pln_mwh", "max_pln_mwh", "volume_mwh", "retrieved_at")),
    "power_rdn": ("EE_RDN", ("trading_date", "data_id", "instrument", "price_pln_mwh", "volume_mwh", "change_pct", "retrieved_at")),
    "power_otf": ("EE_OTF", ("trading_date", "data_id", "instrument", "dkr_pln_mwh", "max_pln_mwh", "volume_mwh", "retrieved_at")),
    "coal": ("WEGIEL", ("trading_date", "data_id", "instrument", "price", "open", "high", "low", "volume", "change_pct", "retrieved_at")),
    "eua": ("EUA", ("trading_date", "data_id", "instrument", "price", "open", "high", "low", "volume", "change_pct", "retrieved_at")),
}

SAMPLE_BIOMASS = [
    {"date": "2026-11-02", "buyer": "Przykładowy odbiorca A", "kind": "Zrębka leśna", "volume": 420, "price": 148.0, "source": "Dane demonstracyjne"},
    {"date": "2026-11-02", "buyer": "Przykładowy odbiorca B", "kind": "Zrębka energetyczna", "volume": 275, "price": 154.5, "source": "Dane demonstracyjne"},
    {"date": "2026-10-30", "buyer": "Przykładowy odbiorca C", "kind": "Zrębka przemysłowa", "volume": 180, "price": 139.0, "source": "Dane demonstracyjne"},
    {"date": "2026-10-29", "buyer": "Przykładowy odbiorca A", "kind": "Zrębka leśna", "volume": 360, "price": 146.0, "source": "Dane demonstracyjne"},
]


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise TypeError(f"Nieobsługiwany typ komórki Excela: {type(value).__name__}")


def load_dashboard_data(workbook_path: Path) -> dict[str, Any]:
    workbook = load_workbook(workbook_path, read_only=True, data_only=True)
    try:
        result: dict[str, Any] = {"sample_biomass": SAMPLE_BIOMASS}
        all_dates: list[str] = []
        retrieval_times: list[datetime] = []
        for key, (sheet_name, expected_headers) in SHEETS.items():
            if sheet_name not in workbook.sheetnames:
                raise ValueError(f"W pliku Excela brakuje arkusza {sheet_name}.")
            worksheet = workbook[sheet_name]
            row_iterator = worksheet.iter_rows(values_only=True)
            headers = next(row_iterator, None)
            missing_headers = set(expected_headers) - set(headers or ())
            if headers is None or missing_headers:
                raise ValueError(
                    f"Arkusz {sheet_name} nie zawiera wymaganych nagłówków: "
                    f"{sorted(missing_headers)!r}."
                )
            records = []
            for row in row_iterator:
                values = dict(zip(headers, row))
                if not values.get("trading_date"):
                    continue
                normalized = {
                    field: _json_value(values.get(field))
                    for field in expected_headers
                }
                if not normalized["trading_date"]:
                    continue
                records.append(normalized)
                all_dates.append(normalized["trading_date"][:10])
                retrieved_at = normalized.get("retrieved_at")
                if isinstance(retrieved_at, str) and retrieved_at.strip():
                    retrieval_times.append(datetime.fromisoformat(retrieved_at))
            records.sort(key=lambda item: (item["trading_date"], item.get("data_id", "")))
            result[key] = records
        if not all_dates:
            raise ValueError("W arkuszach nie znaleziono żadnych dat notowań.")
        result["min_date"] = min(all_dates)
        result["max_date"] = max(all_dates)
        result["updated_at"] = (
            max(retrieval_times).isoformat() if retrieval_times else None
        )
        return result
    finally:
        workbook.close()


def render_dashboard(
    workbook_path: Path = DEFAULT_WORKBOOK,
    template_path: Path = DEFAULT_TEMPLATE,
    output_path: Path = DEFAULT_OUTPUT,
) -> Path:
    data = load_dashboard_data(workbook_path)
    template = template_path.read_text(encoding="utf-8")
    chartjs = CHARTJS_SCRIPT.read_text(encoding="utf-8")
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    serialized = (
        serialized.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
    )
    if template.count("__DASHBOARD_DATA__") != 1:
        raise ValueError("Szablon musi zawierać dokładnie jeden znacznik danych.")
    if template.count("__CHARTJS_SCRIPT__") != 1:
        raise ValueError("Szablon musi zawierać dokładnie jeden znacznik biblioteki Chart.js.")
    output_path.write_text(
        template.replace("__CHARTJS_SCRIPT__", chartjs).replace(
            "__DASHBOARD_DATA__", serialized
        ),
        encoding="utf-8",
    )
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generuje samodzielny dashboard HTML z danych w DataMaster.xlsx."
    )
    parser.add_argument("--workbook", type=Path, default=DEFAULT_WORKBOOK)
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    output = render_dashboard(args.workbook, args.template, args.output)
    print(f"Dashboard zapisano: {output}")


if __name__ == "__main__":
    main()
