"""Pure functions that turn bill/item rows into answers. No network, easy to test."""
import math
from collections import defaultdict
from datetime import datetime, timedelta

PERIODS = ("today", "yesterday", "last_7_days", "this_week", "this_month", "last_30_days")


def parse_ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def period_bounds(period: str, now: datetime):
    """[start, end) in the shop's timezone. `now` must be timezone-aware."""
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    if period == "today":
        return today, tomorrow
    if period == "yesterday":
        return today - timedelta(days=1), today
    if period == "last_7_days":
        return today - timedelta(days=6), tomorrow
    if period == "this_week":  # Monday to now
        return today - timedelta(days=today.weekday()), tomorrow
    if period == "this_month":
        return today.replace(day=1), tomorrow
    if period == "last_30_days":
        return today - timedelta(days=29), tomorrow
    raise ValueError(f"unknown period: {period}")


def _f(x) -> float:
    try:
        v = float(x)
        return v if math.isfinite(v) else 0.0
    except (TypeError, ValueError):
        return 0.0


def sales_summary(bills: list) -> dict:
    by_pay = defaultdict(float)
    total = gst = disc = 0.0
    for b in bills:
        t = _f(b.get("total"))
        total += t
        gst += _f(b.get("gst"))
        disc += _f(b.get("disc"))
        by_pay[b.get("pay_method") or "Other"] += t
    n = len(bills)
    return {
        "bills": n,
        "total": round(total, 2),
        "average_bill": round(total / n, 2) if n else 0.0,
        "gst_collected": round(gst, 2),
        "discount_given": round(disc, 2),
        "by_payment": {k: round(v, 2) for k, v in sorted(by_pay.items())},
    }


def udhaar_by_customer(bills: list, customer: str | None = None) -> list:
    """Unpaid udhaar grouped by customer, biggest first."""
    needle = (customer or "").strip().lower()
    groups: dict = {}
    for b in bills:
        if b.get("pay_method") != "Udhaar" or b.get("paid"):
            continue
        name = (b.get("customer") or "").strip() or "Unknown"
        if needle and needle not in name.lower():
            continue
        g = groups.setdefault(name.lower(), {"customer": name, "due": 0.0, "bills": 0, "bill_nos": [], "oldest": None})
        g["due"] += _f(b.get("total"))
        g["bills"] += 1
        g["bill_nos"].append(b.get("bill_no"))
        ts = b.get("billed_at")
        if ts and (g["oldest"] is None or ts < g["oldest"]):
            g["oldest"] = ts
    out = []
    for g in groups.values():
        g["due"] = round(g["due"], 2)
        g["oldest"] = g["oldest"][:10] if g["oldest"] else None
        out.append(g)
    return sorted(out, key=lambda g: g["due"], reverse=True)


def top_items(bills: list, limit: int = 5) -> list:
    agg: dict = {}
    for b in bills:
        for l in b.get("lines") or []:
            key = (l.get("name"), l.get("unit"))
            a = agg.setdefault(key, {"item": l.get("name"), "unit": l.get("unit"), "qty": 0.0, "amount": 0.0})
            q, p = _f(l.get("qty")), _f(l.get("price"))
            a["qty"] += q
            a["amount"] += q * p
    rows = sorted(agg.values(), key=lambda a: a["amount"], reverse=True)[: max(1, limit)]
    for a in rows:
        a["qty"] = round(a["qty"], 2)
        a["amount"] = round(a["amount"], 2)
    return rows


def low_stock(items: list, limit: int) -> list:
    out = [
        {"name": i.get("name"), "stock": _f(i.get("stock")), "unit": i.get("unit")}
        for i in items
        if i.get("stock") is not None and _f(i.get("stock")) <= limit
    ]
    return sorted(out, key=lambda i: i["stock"])


def compact_bill(b: dict) -> dict:
    lines = b.get("lines") or []
    return {
        "bill_no": b.get("bill_no"),
        "date": (b.get("billed_at") or "")[:10],
        "total": _f(b.get("total")),
        "payment": b.get("pay_method"),
        "customer": b.get("customer") or None,
        "paid": bool(b.get("paid")),
        "items": ", ".join(f"{l.get('name')} {l.get('qty')} {l.get('unit')}" for l in lines[:8]),
    }
