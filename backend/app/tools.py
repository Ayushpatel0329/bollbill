"""The things the AI is allowed to do for a shop.

READ tools answer questions from the shop's own data.
The only WRITE tool is propose_mark_paid, and it does not change anything:
it saves a pending action that runs only when the owner taps "Haan" in the app."""
import re
from datetime import datetime
from zoneinfo import ZoneInfo

from . import analytics
from .calc import inr
from .errors import DBError

_PERIOD_ENUM = list(analytics.PERIODS)

TOOLS = [
    {
        "name": "get_sales_summary",
        "description": "Total sales, number of bills, average bill, GST collected, discount given and "
                       "cash/UPI/udhaar split for a period.",
        "input_schema": {"type": "object", "properties": {"period": {"type": "string", "enum": _PERIOD_ENUM}},
                         "required": ["period"]},
    },
    {
        "name": "get_udhaar_summary",
        "description": "Unpaid udhaar (credit) grouped by customer, biggest first. "
                       "Optionally filter by part of a customer name.",
        "input_schema": {"type": "object", "properties": {"customer": {"type": "string"}}},
    },
    {
        "name": "get_low_stock",
        "description": "Items whose tracked stock is at or below the shop's low-stock limit.",
        "input_schema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_top_items",
        "description": "Best selling items by sales amount in a period.",
        "input_schema": {"type": "object",
                         "properties": {"period": {"type": "string", "enum": _PERIOD_ENUM},
                                        "limit": {"type": "integer", "minimum": 1, "maximum": 10}},
                         "required": ["period"]},
    },
    {
        "name": "find_bills",
        "description": "Look up recent bills by customer name (partial match) or exact bill number.",
        "input_schema": {"type": "object",
                         "properties": {"customer": {"type": "string"}, "bill_no": {"type": "integer"},
                                        "limit": {"type": "integer", "minimum": 1, "maximum": 10}}},
    },
    {
        "name": "propose_mark_paid",
        "description": "Ask the owner to confirm that udhaar was paid. Give EITHER bill_no OR customer "
                       "(exact name from get_udhaar_summary). Nothing changes until the owner confirms.",
        "input_schema": {"type": "object",
                         "properties": {"bill_no": {"type": "integer"}, "customer": {"type": "string"}}},
    },
]


def _clean(text) -> str:
    """Keep letters (any language), digits, spaces and . - only; safe to put in a database filter."""
    return re.sub(r"[^\w\s.\-]", "", str(text or ""), flags=re.UNICODE).strip()[:60]


def _iso_utc(dt: datetime) -> str:
    return dt.astimezone(ZoneInfo("UTC")).isoformat()


class ToolBox:
    def __init__(self, db, shop: dict, timezone: str, run_id: str | None = None):
        self.db, self.shop, self.tz, self.run_id = db, shop, ZoneInfo(timezone), run_id
        self.pending_actions: list = []

    async def run(self, name: str, args: dict) -> dict:
        fn = getattr(self, f"_t_{name}", None) if name in {t["name"] for t in TOOLS} else None
        if fn is None:
            return {"error": f"unknown tool {name}"}
        try:
            return await fn(args if isinstance(args, dict) else {})
        except DBError as e:
            return {"error": e.message}
        except ValueError as e:
            return {"error": str(e)}

    # ---- helpers -----------------------------------------------------
    def _bounds(self, period):
        if period not in analytics.PERIODS:
            raise ValueError("period must be one of: " + ", ".join(analytics.PERIODS))
        start, end = analytics.period_bounds(period, datetime.now(self.tz))
        return start, end

    async def _bills_in(self, period, columns):
        start, end = self._bounds(period)
        rows = await self.db.select("bills", [
            ("select", columns), ("billed_at", f"gte.{_iso_utc(start)}"),
            ("billed_at", f"lt.{_iso_utc(end)}"), ("order", "billed_at.desc"), ("limit", "5000")])
        return rows, start, end

    # ---- read tools --------------------------------------------------
    async def _t_get_sales_summary(self, a):
        rows, start, end = await self._bills_in(a.get("period"), "bill_no,billed_at,total,gst,disc,pay_method")
        out = analytics.sales_summary(rows)
        out.update(period=a["period"], from_date=start.date().isoformat(),
                   to_date=(end.date()).isoformat() + " (exclusive)")
        return out

    async def _t_get_udhaar_summary(self, a):
        rows = await self.db.select("bills", [
            ("select", "bill_no,billed_at,total,customer,paid,pay_method"),
            ("pay_method", "eq.Udhaar"), ("paid", "eq.false"), ("limit", "5000")])
        groups = analytics.udhaar_by_customer(rows, a.get("customer"))
        return {"total_due": round(sum(g["due"] for g in groups), 2), "customers": len(groups),
                "top": groups[:20]}

    async def _t_get_low_stock(self, a):
        limit = int(self.shop.get("low_stock_limit", 5))
        rows = await self.db.select("items", [
            ("select", "name,stock,unit"), ("stock", f"lte.{limit}"), ("order", "stock.asc"), ("limit", "200")])
        return {"limit": limit, "items": analytics.low_stock(rows, limit)}

    async def _t_get_top_items(self, a):
        rows, start, _ = await self._bills_in(a.get("period"), "bill_no,billed_at,lines")
        lim = max(1, min(10, int(a.get("limit") or 5)))
        return {"period": a["period"], "items": analytics.top_items(rows, lim)}

    async def _t_find_bills(self, a):
        params = [("select", "bill_no,billed_at,total,pay_method,customer,paid,lines"),
                  ("order", "billed_at.desc"), ("limit", str(max(1, min(10, int(a.get("limit") or 5)))))]
        if a.get("bill_no") is not None:
            params.append(("bill_no", f"eq.{int(a['bill_no'])}"))
        elif a.get("customer"):
            c = _clean(a["customer"])
            if not c:
                raise ValueError("customer name is empty")
            params.append(("customer", f"ilike.*{c}*"))
        else:
            raise ValueError("give customer or bill_no")
        rows = await self.db.select("bills", params)
        return {"bills": [analytics.compact_bill(b) for b in rows]}

    # ---- the one write tool (needs owner confirmation) ----------------
    async def _t_propose_mark_paid(self, a):
        if a.get("bill_no") is not None:
            n = int(a["bill_no"])
            rows = await self.db.select("bills", [
                ("select", "bill_no,total,customer,paid,pay_method"), ("bill_no", f"eq.{n}")])
            if not rows or rows[0]["pay_method"] != "Udhaar":
                return {"error": f"Bill #{n} udhaar ka nahi mila."}
            if rows[0]["paid"]:
                return {"error": f"Bill #{n} pehle se paid hai."}
            who = rows[0]["customer"] or "customer"
            summary = f"Bill #{n} ({who}) ke {inr(rows[0]['total'])} paid mark karein?"
            params = {"bill_no": n}
        elif a.get("customer"):
            c = _clean(a["customer"])
            if not c:
                raise ValueError("customer name is empty")
            rows = await self.db.select("bills", [
                ("select", "bill_no,total,customer"), ("pay_method", "eq.Udhaar"), ("paid", "eq.false"),
                ("customer", f"ilike.{c}"), ("limit", "500")])
            if not rows:
                return {"error": f"{c} ka koi baaki udhaar nahi mila."}
            who = rows[0]["customer"]
            total = sum(float(r["total"]) for r in rows)
            summary = f"{who} ke {len(rows)} bill, kul {inr(total)}, paid mark karein?"
            params = {"customer": who}
        else:
            raise ValueError("give bill_no or customer")

        row = await self.db.insert("agent_actions", {
            "shop_id": self.shop["id"], "run_id": self.run_id, "kind": "mark_paid",
            "params": params, "summary": summary})
        self.pending_actions.append({"id": row["id"], "summary": summary})
        return {"status": "waiting_for_owner_confirmation", "action_id": row["id"], "summary": summary}


async def execute_action(db, action: dict) -> str:
    """Runs a CONFIRMED action. Only called from the confirm endpoint."""
    if action["kind"] == "mark_paid":
        p = action["params"]
        if p.get("bill_no") is not None:
            await db.rpc("mark_bill_paid", {"p_bill_no": int(p["bill_no"])})
            return f"Bill #{p['bill_no']} paid mark ho gaya."
        n = await db.rpc("mark_customer_paid", {"p_customer": p["customer"]})
        return f"{p['customer']} ke {n} bill paid mark ho gaye."
    raise ValueError("unknown action")
