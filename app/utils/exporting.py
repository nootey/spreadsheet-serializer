from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from typing import Dict, List, Tuple

class ExportUtils:

    @staticmethod
    def sum_as_str(values):
        total = Decimal("0.00")
        for v in values:
            total += Decimal(v)
        return str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    @staticmethod
    def _to_decimal(x) -> Decimal:
        try:
            return Decimal(str(x))
        except (InvalidOperation, ValueError, TypeError):
            return Decimal("0.00")

    @staticmethod
    def totals_from_records(records: List[Dict], include_all: bool = True) -> Dict[str, str]:
        buckets: Dict[str, List[str]] = {}
        for r in records:
            buckets.setdefault(r["transaction_type"], []).append(r["amount"])

        totals = {k: ExportUtils.sum_as_str(vs) for k, vs in buckets.items()}
        if include_all and buckets:
            totals["ALL"] = ExportUtils.sum_as_str([a for vs in buckets.values() for a in vs])
        return totals

    @staticmethod
    def validate_totals(
            actual: Dict[str, str],
            expected: Dict[str, str] | None,
            policy: str = "fail",
    ) -> Tuple[bool, List[str]]:
        expected = expected or {}
        if not expected:
            return True, ["Validation: no expected_totals provided — skipping."]

        report: List[str] = ["Validation (expected vs actual):"]
        ok = True
        for key, exp_str in expected.items():
            exp = ExportUtils._to_decimal(exp_str)
            act = ExportUtils._to_decimal(actual.get(key))
            if act != exp:
                ok = False
                report.append(f"  - {key}: EXPECTED {exp_str}  !=  ACTUAL {actual.get(key)}")
            else:
                report.append(f"  - {key}: OK ({ExportUtils.sum_as_str([str(act)])})")

        if not ok and policy.lower() != "warn":
            report.append("ERROR: Totals mismatch and mismatch_policy != 'warn' → aborting.")
            return False, report

        if not ok:
            report.append("WARNING: Totals mismatch (policy='warn') → continuing to write output.")

        return True, report