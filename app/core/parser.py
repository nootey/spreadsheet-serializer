from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd

from app.utils.month_resolver import MonthResolver
from app.utils.parsing import ParsingUtils
from app.utils.exporting import ExportUtils

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

        header_row = df.iloc[header_row_idx]
        month_cols = set(month_map.values())
        for col in df.columns:
            if col in month_cols:
                continue
            head = ParsingUtils.normalize_text(header_row[col]).upper()
            if head:
                return col

        first_month_pos = min(df.columns.get_loc(c) for c in month_cols)
        fallback_idx = max(0, first_month_pos - 1)
        return df.columns[fallback_idx]

    def parse(self, df: pd.DataFrame) -> List[Dict]:
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
            # exact match ignore, without catching partial columns
            if u in self.ignored_row_exact:
                continue
            # prefix ignore
            if any(u.startswith(p) for p in self.ignored_row_prefixes):
                continue

            for month_idx, col in month_map.items():
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

        if self.debug:
            by_kind = {}
            for r in records:
                by_kind[r["transaction_type"]] = by_kind.get(r["transaction_type"], 0) + 1
            print(f"DEBUG: record counts by kind: {by_kind}")
            print(f"DEBUG: total records: {len(records)}")

        return records

    def parse_excel_file(self, file_path: Path) -> List[Dict]:
        df = pd.read_excel(file_path, engine="openpyxl", header=None, sheet_name=self.sheet_name)
        return self.parse(df)

    def export_to_json(self, records: List[Dict], output_path: Path) -> None:
        buckets: Dict[str, List[str]] = {}
        for r in records:
            buckets.setdefault(r["transaction_type"], []).append(r["amount"])

        totals = {k: ExportUtils.sum_as_str(vs) for k, vs in buckets.items()}
        if buckets:
            totals["ALL"] = ExportUtils.sum_as_str(sum(buckets.values(), []))

        payload = {
            "year": self.year,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "totals": totals,
            "transactions": records
        }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        print(f"Wrote {len(records)} transactions")


def load_config(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
