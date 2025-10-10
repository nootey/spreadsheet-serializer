from __future__ import annotations

import re
import unicodedata
from typing import Dict, Iterable, Optional, Tuple

def _norm_text(s: object) -> str:
    if s is None:
        return ""
    t = str(s).strip()
    t = unicodedata.normalize("NFKC", t)
    t = re.sub(r"\s+", " ", t)
    return t

class MonthResolver:
    def __init__(self, months_config: Dict[str, Iterable[str]]):
        if not months_config or not isinstance(months_config, dict):
            raise ValueError("MonthResolver requires a 'months' dict in config")

        alias_map: Dict[str, int] = {}
        for k, aliases in months_config.items():
            try:
                month_idx = int(k)
            except Exception as e:
                raise ValueError(f"Month key must be int-like (1..12), got {k!r}") from e
            if month_idx < 1 or month_idx > 12:
                raise ValueError(f"Month index out of range: {month_idx}")

            # include the numeric index itself as an alias too
            for alias in set(list(aliases) + [str(month_idx)]):
                key = _norm_text(alias).upper()
                if key:
                    alias_map[key] = month_idx

        self._alias_to_idx = alias_map

    def match(self, text: object) -> Optional[int]:
        key = _norm_text(text).upper()
        if not key:
            return None
        return self._alias_to_idx.get(key)

    def find_months_in_row(self, row) -> Dict[int, int]:
        """Return mapping {month_index: column_index} for this header row."""
        out: Dict[int, int] = {}
        for col in row.index:
            m = self.match(row[col])
            if m is not None:
                out[m] = col
        return out