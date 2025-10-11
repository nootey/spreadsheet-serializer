import re
import unicodedata
from typing import Optional
import pandas as pd


class ParsingUtils:

    @staticmethod
    def normalize_text(s: object) -> str:
        if s is None or (isinstance(s, float) and pd.isna(s)):
            return ""
        t = str(s).strip()
        t = unicodedata.normalize("NFKC", t)
        t = t.replace("\u2013", "-").replace("\u2014", "-")
        t = re.sub(r"\s*-\s*", " - ", t)
        t = re.sub(r"\s+", " ", t)
        return t

    @staticmethod
    def coerce_amount(x: object) -> Optional[float]:
        if x is None or (isinstance(x, float) and pd.isna(x)):
            return None
        if isinstance(x, (int, float)):
            v = float(x)
            return None if abs(v) < 1e-9 else v

        s = ParsingUtils.normalize_text(x)
        if not s:
            return None

        s = s.replace("€", "").replace("\u00A0", "").replace(" ", "")
        if s == "":
            return None

        if "." in s and "," in s:
            s = s.replace(".", "").replace(",", ".")
        elif "," in s:
            s = s.replace(",", ".")

        try:
            v = float(s)
        except ValueError:
            return None

        return None if abs(v) < 1e-9 else v
