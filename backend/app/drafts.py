"""Checks what the AI returned for a voice bill. The AI is never trusted:
every item must exist in the shop's price list and every number must be sane."""
import math

PAYMENTS = {"Cash", "UPI", "Udhaar"}
SPOKEN_UNITS = {"g", "ml", "dozen", "rs"}   # the app converts these to the item's own unit


def _num(x):
    if isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) else None


def sanitize_draft(raw: dict, items: list) -> dict:
    by_name = {i["name"]: i for i in items}
    by_lower = {i["name"].lower(): i for i in items}
    lines, unmatched = [], [str(x)[:60] for x in (raw.get("unmatched") or [])][:10]

    for l in (raw.get("lines") or [])[:30]:
        if not isinstance(l, dict):
            continue
        name = l.get("item")
        spoken = str(l.get("spoken") or name or "")[:60]
        it = by_name.get(name) or by_lower.get(str(name).lower())
        qty = _num(l.get("qty"))
        if not it or qty is None or not (0 < qty <= 100000):
            if spoken:
                unmatched.append(spoken)
            continue
        unit = l.get("unit")
        if unit not in SPOKEN_UNITS and unit != it.get("unit"):
            unit = it.get("unit")
        lines.append({"name": it["name"], "qty": round(qty, 4), "unit": unit})

    customer = str(raw.get("customer") or "").strip()[:80] or None
    payment = raw.get("payment") if raw.get("payment") in PAYMENTS else None
    disc = _num(raw.get("discount_pct"))
    gst = _num(raw.get("gst_pct"))
    return {
        "lines": lines,
        "unmatched": unmatched,
        "customer": customer,
        "payment": payment,
        "discount_pct": disc if disc is not None and 0 <= disc <= 100 else None,
        "gst_pct": gst if gst is not None and 0 <= gst <= 100 else None,
    }
