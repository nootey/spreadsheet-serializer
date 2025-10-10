from pathlib import Path
from app.core.parser import SpreadsheetParser, load_config

def run():
    year = 2022
    project_root = Path(__file__).resolve().parents[2]
    xlsx_path  = project_root.parent / "input" / f"{year}.xlsx"
    out_path  = project_root.parent / "output" / f"{year}.json"
    cfg_path = project_root.parent / "input" / "2022.json"

    config = load_config(cfg_path)
    parser = SpreadsheetParser(config)

    records = parser.parse_excel_file(xlsx_path)
    parser.export_to_json(records, out_path)

if __name__ == "__main__":
    run()