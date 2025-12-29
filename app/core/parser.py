from __future__ import annotations

import json
import string
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import pandas as pd

from app.utils.month_resolver import MonthResolver
from app.utils.parsing import ParsingUtils

class SpreadsheetParser:

    def __init__(self, config: Dict, simplified: bool = False):
        self.year: int = int(config["year"])
        self.sheet_name = config.get("sheet_name", 0)
        self.header_scan_rows: int = int(config.get("header_scan_rows", 12))
        self.category_col_hint = config.get("category_col_hint", None)
        self.debug: bool = bool(config.get("debug", False))
        self.simplified = simplified

        if simplified:
            # Crypto-specific config
            self.alt_columns = config.get("columns", {
                "date": "Date",
                "coin": "Coin",
                "profit_loss": "Profit/Loss"
            })
        else:
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

    def parse_crypto_excel_file(self, file_path: Path) -> List[Dict]:
        df = pd.read_excel(file_path, engine="openpyxl", sheet_name=0, header=None)

        # Find the header row
        date_col_name = self.alt_columns["date"]
        header_row_idx = None

        for r in range(min(self.header_scan_rows, len(df))):
            for c in df.columns:
                cell_val = ParsingUtils.normalize_text(df.iloc[r][c])
                if cell_val.upper() == date_col_name.upper():
                    header_row_idx = r
                    break
            if header_row_idx is not None:
                break

        if header_row_idx is None:
            if self.debug:
                print(f"DEBUG: Could not find header row with '{date_col_name}' column")
            return []

        df.columns = [ParsingUtils.normalize_text(col) for col in df.iloc[header_row_idx]]
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)

        df = df[df.iloc[:, df.columns.get_loc(self.alt_columns["date"])] != self.alt_columns["date"]]
        df = df.reset_index(drop=True)

        if self.debug:
            print(f"DEBUG: Columns: {df.columns.tolist()}")
            print(f"DEBUG: First few data rows:")
            print(df.head())

        records: List[Dict] = []

        date_col = self.alt_columns["date"]
        coin_col = self.alt_columns["coin"]
        pl_col = self.alt_columns["profit_loss"]

        for idx, row in df.iterrows():
            date_val = row.get(date_col)
            profit_loss = ParsingUtils.coerce_amount(row.get(pl_col))
            coin = ParsingUtils.normalize_text(row.get(coin_col, ""))
            coin = coin.rstrip(string.digits)

            if self.debug:
                print(f"DEBUG: Row {idx}: date={date_val}, profit_loss={profit_loss}, coin={coin}")

            if pd.isna(date_val) or profit_loss is None or pd.isna(profit_loss):
                if self.debug:
                    print(f"DEBUG: Skipping row {idx} - missing date or profit/loss")
                continue

            # Parse date
            if isinstance(date_val, datetime):
                txn_date = date_val.strftime("%Y-%m-%dT00:00:00Z")
            else:
                try:
                    parsed = pd.to_datetime(str(date_val), dayfirst=True)
                    txn_date = parsed.strftime("%Y-%m-%dT00:00:00Z")
                except Exception as e:
                    if self.debug:
                        print(f"DEBUG: Failed to parse date: {date_val}, error: {e}")
                    continue

            txn_type = "income" if profit_loss > 0 else "expense"
            amount = abs(profit_loss)

            records.append({
                "transaction_type": txn_type,
                "amount": f"{amount:.2f}",
                "currency": "EUR",
                "txn_date": txn_date,
                "category": f"Crypto PNL" if coin else "Crypto",
                "description": f"Profit/Loss from {coin}" if coin else "Crypto trading"
            })

        if self.debug:
            print(f"DEBUG: Parsed {len(records)} crypto transactions")

        return records

    def parse_stonks_excel_file(self, file_path: Path) -> List[Dict]:
        df = pd.read_excel(file_path, engine="openpyxl", sheet_name=0, header=None)

        # Find the header row
        header_row_idx = None
        for r in range(min(self.header_scan_rows, len(df))):
            for c in df.columns:
                cell_val = ParsingUtils.normalize_text(df.iloc[r][c])
                if cell_val.upper() == "TICKER":
                    header_row_idx = r
                    break
            if header_row_idx is not None:
                break

        if header_row_idx is None:
            if self.debug:
                print("DEBUG: Could not find header row with 'Ticker' column")
            return []

        df.columns = [ParsingUtils.normalize_text(col) for col in df.iloc[header_row_idx]]
        df = df.iloc[header_row_idx + 1:].reset_index(drop=True)

        if self.debug:
            print(f"DEBUG: Columns: {df.columns.tolist()}")
            print(f"DEBUG: First few data rows:")
            print(df.head())

        records: List[Dict] = []

        date_col = self.alt_columns.get("date", "Purchase date")
        ticker_col = self.alt_columns.get("ticker", "Ticker")
        amount_col = self.alt_columns.get("amount", "Amount")
        fee_col = self.alt_columns.get("fee", "Fee")

        for idx, row in df.iterrows():
            date_val = row.get(date_col)
            ticker = ParsingUtils.normalize_text(row.get(ticker_col, ""))
            amount = ParsingUtils.coerce_amount(row.get(amount_col))
            fee = ParsingUtils.coerce_amount(row.get(fee_col))

            if self.debug:
                print(f"DEBUG: Row {idx}: date={date_val}, ticker={ticker}, amount={amount}, fee={fee}")

            if pd.isna(date_val) or amount is None or pd.isna(amount):
                if self.debug:
                    print(f"DEBUG: Skipping row {idx} - missing date or amount")
                continue

            # Parse date
            if isinstance(date_val, datetime):
                txn_date = date_val.strftime("%Y-%m-%dT00:00:00Z")
            else:
                try:
                    parsed = pd.to_datetime(str(date_val), dayfirst=True)
                    txn_date = parsed.strftime("%Y-%m-%dT00:00:00Z")
                except Exception as e:
                    if self.debug:
                        print(f"DEBUG: Failed to parse date: {date_val}, error: {e}")
                    continue

            amount = abs(amount)
            fee_str = f"{abs(fee):.2f}" if fee and not pd.isna(fee) else "0.00"

            records.append({
                "transaction_type": "buy",
                "amount": f"{amount:.6f}",
                "fee": fee_str,
                "currency": "EUR",
                "txn_date": txn_date,
                "category": f"{ticker}",
                "description": ""
            })

        if self.debug:
            print(f"DEBUG: Parsed {len(records)} stonks transactions")

        return records

    def export_to_json(self, records: List[Dict], output_path: Path) -> None:
        transactions = [
            r for r in records
            if r.get("transaction_type") in {"income", "expense"}
        ]
        investments = [
            r for r in records
            if r.get("transaction_type") == "investments"
        ]
        savings = [
            r for r in records
            if r.get("transaction_type") == "savings"
        ]
        repayments = [
            r for r in records
            if r.get("transaction_type") == "repayments"
        ]

        # Parse filename to create identifier
        filename = output_path.stem
        if filename.startswith("crypto-"):
            year = filename.split("-")[1]
            identifier = f"crypto_{year}"
        elif filename.startswith("stonks-"):
            year = filename.split("-")[1]
            identifier = f"stonks_{year}"
        else:
            identifier = f"fiat_{filename}"

        payload = {
            "identifier": identifier,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "transactions": transactions,
            "investments": investments,
            "savings": savings,
            "repayments": repayments,
        }

        if filename.startswith("stonks-"):
            trades = [
                r for r in records
                if r.get("transaction_type") in {"buy", "sell"}
            ]
            payload["trades"] = trades

        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

        trades_msg = f", {len(payload.get('trades', []))} trades" if "trades" in payload else ""
        print(
            f"Wrote {len(transactions)} transactions, {len(investments)} investment transfers, {len(savings)} savings transfers, {len(repayments)} debt repayments{trades_msg}")


def load_config(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
