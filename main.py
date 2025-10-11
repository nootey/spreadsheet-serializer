from __future__ import annotations
import argparse
from pathlib import Path
import sys

from app.core.parser import SpreadsheetParser, load_config
from app.utils.exporting import ExportUtils

def main() -> int:
    ap = argparse.ArgumentParser(description="Serialize budget spreadsheet year → JSON")
    ap.add_argument("year", type=int, help="e.g. 2022")
    args = ap.parse_args()

    base = Path(__file__).resolve().parent
    xlsx_path = base / "input" / f"{args.year}.xlsx"
    cfg_path  = base / "input" / f"{args.year}.json"
    out_path  = base / "output" / f"{args.year}.json"

    if not xlsx_path.exists():
        print(f"ERR: XLSX not found: {xlsx_path}", file=sys.stderr)
        return 2
    if not cfg_path.exists():
        print(f"ERR: Config not found: {cfg_path}", file=sys.stderr)
        return 2

    config = load_config(cfg_path)
    config["year"] = args.year

    parser = SpreadsheetParser(config)

    try:
        records = parser.parse_excel_file(xlsx_path)
    except Exception as e:
        print(f"ERR: Failed to parse Excel: {e}", file=sys.stderr)
        return 3

    if not records:
        print("ERR: No transactions parsed. Check header detection/month map/sheet name.", file=sys.stderr)
        return 4

    actual_totals = ExportUtils.totals_from_records(records)
    expected_totals = config.get("expected_totals") or {}
    policy = (config.get("mismatch_policy") or "fail").lower()

    ok, report_lines = ExportUtils.validate_totals(actual_totals, expected_totals, policy)

    for line in report_lines:
        print(line)

    if not ok:
        mismatched = [
            k for k, v in expected_totals.items()
            if abs(float(actual_totals.get(k, 0)) - float(v)) > 0.01
        ]

        if mismatched == ["savings"] or mismatched == []:
            print("NOTE: Ignoring savings mismatch, continuing export...")
        else:
            return 5

    try:
        parser.export_to_json(records, out_path)
    except Exception as e:
        print(f"ERR: Failed to write output: {e}", file=sys.stderr)
        return 6

    print(f"Output saved to: {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())