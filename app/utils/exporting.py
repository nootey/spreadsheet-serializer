from decimal import Decimal, ROUND_HALF_UP

class ExportUtils:

    @staticmethod
    def sum_as_str(values):
        total = Decimal("0.00")
        for v in values:
            total += Decimal(v)
        return str(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))