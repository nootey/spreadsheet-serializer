from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd

from app.utils.month_resolver import MonthResolver
from app.utils.parsing import ParsingUtils

class SpreadsheetParser:

    def __init__(self, config: Dict):
        self.year: int = int(config["year"])
        self.sheet_name = config.get("sheet_name", 0)
        self.header_scan_rows: int = int(config.get("header_scan_rows", 12))
        self.category_col_hint = config.get("category_col_hint", None)
        self.debug: bool = bool(config.get("debug", False))

        months_cfg = config.get("months")
        self.months = MonthResolver(months_cfg)

        cfg_sec = config.get("section_prefixes") or []
        if not cfg_sec:
            raise ValueError("Config must include 'section_prefixes' list")
        self.section_prefixes: List[Tuple[str, str]] = [
            (str(p).strip(), str(k).strip()) for p, k in cfg_sec
        ]
        self.section_kind: Dict[str, str] = {p: k for p, k in self.section_prefixes}

        self.ignored_row_prefixes = set(x.upper() for x in config.get("ignored_prefixes", []))
        self.ignored_row_exact = set(x.upper() for x in config.get("ignored_exact", []))
        self.used_col_aliases = set(x.upper() for x in config.get("used_col_aliases", ["USED"]))

    def _find_used_column(self, df: pd.DataFrame, header_row_idx: int):
        max_rows = min(self.header_scan_rows, len(df))
        for c in df.columns:
            t = ParsingUtils.normalize_text(df.iloc[header_row_idx][c]).upper()
            if t in self.used_col_aliases:
                return c

        start = max(0, header_row_idx - 2)
        end = min(len(df), header_row_idx + 3)
        for r in range(start, end):
            for c in df.columns:
                t = ParsingUtils.normalize_text(df.iloc[r][c]).upper()
                if t in self.used_col_aliases:
                    return c

        for r in range(max_rows):
            for c in df.columns:
                t = ParsingUtils.normalize_text(df.iloc[r][c]).upper()
                if t in self.used_col_aliases:
                    return c

        return None

    def detect_section(self, label: object) -> Optional[str]:
        t = ParsingUtils.normalize_text(label).upper()
        if not t:
            return None
        if t.startswith("NET OSTANEK"):
            return "NET OSTANEK"
        for prefix, _kind in self.section_prefixes:
            if t.startswith(prefix.upper()):
                return prefix
        return None

    def find_header_row_and_month_map(
        self, df: pd.DataFrame
    ) -> Tuple[Optional[int], Dict[int, int]]:
        for r in range(min(self.header_scan_rows, len(df))):
            row = df.iloc[r]
            found = self.months.find_months_in_row(row)
            if len(found) >= 3:
                return r, found
        return None, {}

    def pick_category_column(self, df: pd.DataFrame, header_row_idx: int, month_map: Dict[int, int]):
        if self.category_col_hint is not None:
            return df.columns[int(self.category_col_hint)]

        month_cols = set(month_map.values())
        first_month_pos = min(df.columns.get_loc(c) for c in month_cols)

        preferred_idx = max(0, first_month_pos - 1)
        return df.columns[preferred_idx]

    def parse(self, df: pd.DataFrame, source_sheet: str | None = None) -> List[Dict]:
        df = df.copy()
        header_row_idx, month_map = self.find_header_row_and_month_map(df)
        if not month_map:
            if self.debug:
                print("DEBUG: No month header row found.")
            return []

        category_col = self.pick_category_column(df, header_row_idx, month_map)

        if self.debug:
            dbg_months = {k: month_map[k] for k in sorted(month_map)}
            print(f"DEBUG: header_row_idx={header_row_idx}")
            print(f"DEBUG: month_map (month→col)={dbg_months}")
            print(f"DEBUG: category_col idx={df.columns.get_loc(category_col)} "
                  f"header_cell='{ParsingUtils.normalize_text(df.iloc[header_row_idx][category_col])}'")

        used_col = self._find_used_column(df, header_row_idx)
        if self.debug:
            if used_col is None:
                print("DEBUG: used_col not found within header scan area.")
            else:
                print(f"DEBUG: used_col idx={df.columns.get_loc(used_col)} "
                      f"header_cell='{ParsingUtils.normalize_text(df.iloc[header_row_idx][used_col])}'")

        initial_label = df.iloc[header_row_idx][category_col]
        section = self.detect_section(initial_label)
        txn_type = self.section_kind.get(section) if section else None

        if self.debug:
            print(f"DEBUG: initial section on header row → {section} ({txn_type})")

        records: List[Dict] = []

        for ridx, row in df.iloc[header_row_idx + 1:].iterrows():
            first_cell = row[category_col]
            sec = self.detect_section(first_cell)

            if sec:
                section = sec
                txn_type = self.section_kind.get(section)
                if self.debug:
                    print(
                        f"DEBUG: section at row {ridx}: '{ParsingUtils.normalize_text(first_cell)}' → {section} ({txn_type})")
                if section == "NET OSTANEK":
                    break
                continue

            if txn_type is None:
                continue

            label = ParsingUtils.normalize_text(first_cell)
            if not label:
                continue

            u = label.upper()
            if u in self.ignored_row_exact:
                continue
            if any(u.startswith(p) for p in self.ignored_row_prefixes):
                continue
            if u in {"TOTAL"}:
                continue  # <-- Skip total rows

            for month_idx, col in month_map.items():
                header_val = ParsingUtils.normalize_text(df.iloc[header_row_idx][col]).upper()
                if "LAST" in header_val and "YEAR" in header_val:
                    continue

                amount = ParsingUtils.coerce_amount(row[col])
                if amount is None:
                    continue
                records.append({
                    "transaction_type": txn_type,
                    "amount": f"{amount:.2f}",
                    "currency": "EUR",
                    "txn_date": f"{self.year}-{month_idx:02d}-01T00:00:00Z",
                    "category": label,
                    "description": ""
                })

            if txn_type == "savings" and used_col is not None:
                used_amt = ParsingUtils.coerce_amount(row[used_col])
                if used_amt is not None and abs(used_amt) > 1e-9:
                    used_amt = -abs(used_amt)
                    records.append({
                        "transaction_type": "savings",
                        "amount": f"{used_amt:.2f}",
                        "currency": "EUR",
                        "txn_date": f"{self.year}-12-31T00:00:00Z",
                        "category": label,
                        "description": "USED"
                    })

        if self.debug and source_sheet:
            # lightweight per-sheet totals
            from app.utils.exporting import ExportUtils
            by_type = {}
            for r in records:
                by_type.setdefault(r["transaction_type"], []).append(r["amount"])
            print(f"DEBUG: sheet '{source_sheet}' totals → " +
                  ", ".join(f"{k}={ExportUtils.sum_as_str(v)}" for k, v in by_type.items()))
        return records

    def parse_excel_file(self, file_path: Path) -> List[Dict]:
        # Support single sheet, list of sheets, or ALL sheets
        sn = self.sheet_name
        if isinstance(sn, str) and sn.strip().upper() == "ALL":
            sheet_arg = None  # pandas: None -> all sheets
        else:
            sheet_arg = sn

        dfs = pd.read_excel(file_path, engine="openpyxl", header=None, sheet_name=sheet_arg)

        # pandas returns a DataFrame for single sheet, or a dict[str|int, DataFrame] for multiple
        if isinstance(dfs, pd.DataFrame):
            return self.parse(dfs)

        all_records: List[Dict] = []
        for name, df in dfs.items():
            if self.debug:
                print(f"DEBUG: parsing sheet → {name}")
            all_records.extend(self.parse(df, source_sheet=str(name)))
        return all_records

    def export_to_json(self, records: List[Dict], output_path: Path) -> None:
        transactions = [
            r for r in records
            if r.get("transaction_type") in {"income", "expense"}
        ]
        transfers = [
            r for r in records
            if r.get("transaction_type") == "investments"
        ]

        payload = {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "transactions": transactions,
            "transfers": transfers,
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"Wrote {len(transactions)} transactions, {len(transfers)} transfers")


def load_config(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
