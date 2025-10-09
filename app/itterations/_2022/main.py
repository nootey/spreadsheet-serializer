import json
from pathlib import Path
import pandas as pd

MONTHS_SL = ["JANUAR","FEBRUAR","MAREC","APRIL","MAJ","JUNIJ","JULIJ",
             "AVGUST","SEPTEMBER","OKTOBER","NOVEMBER","DECEMBER"]

SECTION_TYPES = {
    "PRIHODKI": "inflow",
    "FIKSNI STROŠKI": "expense",
    "VARIABILNI STROŠKI": "expense",
    "FIKSNI PRIHRANKI": "savings",
    "VARIABILNI PRIHRANKI": "savings",
}

IGNORED_ROW_PREFIXES = {
    "Skupaj",
    "Prihodki",
    "Stroški",
    "FIKSNI PRIHRANKI",
    "VARIABILNI PRIHRANKI",
    "NET OSTANEK",
    "FIKSNI PRIHRANKI Skupaj",
}

def coerce_amount(x):
    if pd.isna(x):
        return None
    if isinstance(x, (int, float)):
        val = float(x)
    else:
        s = str(x).replace("€","").replace(" ","").replace(".","").replace(",",".")
        try:
            val = float(s)
        except ValueError:
            return None
    if abs(val) < 1e-9:
        return None
    return val

def detect_section(label):
    if label is None or (isinstance(label, float) and pd.isna(label)):
        return None
    s = str(label).strip().upper()
    for key in SECTION_TYPES:
        if s.startswith(key):
            return key
    if s.startswith("NET OSTANEK"):
        return "NET OSTANEK"
    return None

def find_header_row_and_month_map(df: pd.DataFrame, scan_rows: int = 6):
    for r in range(min(scan_rows, len(df))):
        row = df.iloc[r]
        found = {}
        for col in df.columns:
            val = str(row[col]).strip().upper()
            if val in MONTHS_SL:
                found[val] = col
        if len(found) >= 3:
            return r, found
    return None, {}

def pick_category_column(df: pd.DataFrame) -> str:
    candidates = df.columns[:5]
    scores = {}
    for col in candidates:
        vals = df[col].astype(str)
        scores[col] = (vals != "nan").sum()
    return max(scores, key=scores.get)

def parse_year(df, year):
    df = df.copy()

    header_row_idx, month_map = find_header_row_and_month_map(df)
    if not month_map:
        return []

    existing_months = [m for m in MONTHS_SL if m in month_map]
    category_col = pick_category_column(df)

    records = []
    section = None
    txn_type = None

    for _, row in df.iloc[header_row_idx+1:].iterrows():
        first_cell = row[category_col]

        sec = detect_section(first_cell)
        if sec:
            section = sec
            txn_type = SECTION_TYPES.get(section)
            if section == "NET OSTANEK":
                break
            continue

        if txn_type is None:
            continue

        if first_cell is None or (isinstance(first_cell, float) and pd.isna(first_cell)):
            continue
        desc = str(first_cell).strip()
        if not desc or any(desc.upper().startswith(p.upper()) for p in IGNORED_ROW_PREFIXES):
            continue

        for m in existing_months:
            amount = coerce_amount(row[month_map[m]])
            if amount is None:
                continue
            month_index = MONTHS_SL.index(m) + 1
            txn_date = f"{year}-{month_index:02d}-01"
            records.append({
                "transaction_type": txn_type,
                "amount": f"{amount:.2f}",
                "currency": "EUR",
                "txn_date": txn_date,
                "description": desc,
                "section": section,
                "month": m,
            })
    return records

def run():

    project_root = Path(__file__).resolve().parents[2]
    in_xlsx = project_root.parent / "input" / "2022.xlsx"
    out_json = project_root.parent / "output" / "2022.json"
    out_json.parent.mkdir(parents=True, exist_ok=True)

    if not in_xlsx.exists():
        raise FileNotFoundError(f"Input Excel not found: {in_xlsx}")

    year = 2022
    df = pd.read_excel(in_xlsx, engine="openpyxl", header=None)

    records = parse_year(df, year)

    with out_json.open("w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(records)} transactions → {out_json}")

if __name__ == "__main__":
    run()
