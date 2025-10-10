# main.py
from __future__ import annotations
import argparse
from pathlib import Path
import sys

from app.core.parser import SpreadsheetParser, load_config

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
    records = parser.parse_excel_file(xlsx_path)
    parser.export_to_json(records, out_path)

    print(f"OK → {out_path}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())