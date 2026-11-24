"""Bill maths. Mirrors the browser app and the SQL function calc_totals():
discount first, then GST on the amount that is left. Uses Decimal so paise never drift."""
from decimal import Decimal, ROUND_HALF_UP

_Q = Decimal("0.01")


def _d(x) -> Decimal:
    return Decimal(str(0 if x is None else x))


def r2(x) -> Decimal:
    return _d(x).quantize(_Q, rounding=ROUND_HALF_UP)


def calc_totals(lines, disc_type: str = "pct", disc_val=0, gst_pct=0) -> dict:
    sub = sum((r2(_d(l["qty"]) * _d(l["price"])) for l in lines), Decimal(0))
    dv = max(Decimal(0), _d(disc_val))
    if disc_type == "pct":
        dv = min(dv, Decimal(100))
        disc = min(sub, r2(sub * dv / 100))
    else:
        disc = min(sub, r2(dv))
    taxable = r2(sub - disc)
    g = min(Decimal(100), max(Decimal(0), _d(gst_pct)))
    gst = r2(taxable * g / 100)
    total = r2(taxable + gst)
    return {
        "sub": float(sub), "disc_type": disc_type, "disc_val": float(dv), "disc": float(disc),
        "taxable": float(taxable), "gst_pct": float(g), "gst": float(gst), "total": float(total),
    }


def inr(x) -> str:
    """12345.5 -> '₹12,345.50' with Indian digit grouping (12,34,567)."""
    v = r2(x)
    neg = v < 0
    whole, frac = f"{abs(v):.2f}".split(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    return ("-" if neg else "") + "₹" + whole + ("" if frac == "00" else "." + frac)
