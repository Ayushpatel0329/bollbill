"""BOLL BILL Backend Service (FastAPI).
Includes:
- AI Voice Bill & Chat Assistant
- Release 2: Purchase File Import & Commit & Undo (Feature 2)
- Release 2: Udhaar Agent & Inbox Approval Flow (Feature 6)
"""
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from typing import Optional, List, Dict, Any

import anthropic
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import agent
from .auth import User, current_user
from .config import load_settings
from .db import DB
from .errors import AgentError, DBError
from .tools import ToolBox, execute_action
from .importer import (
    parse_csv_content,
    detect_columns,
    match_and_preview,
    normalize_name
)
from .udhaar_agent import (
    draft_reminder,
    classify_reply,
    find_overdue_bills
)

log = logging.getLogger("bollbill")
logging.basicConfig(level=logging.INFO)

settings = load_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = settings
    app.state.http = httpx.AsyncClient()
    if settings.anthropic_api_key and not settings.anthropic_api_key.startswith("sk-ant-test"):
        app.state.claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    else:
        app.state.claude = None
    app.state.limiter = RateLimiter(settings.rate_limit_per_min, settings.daily_ai_limit)
    yield
    await app.state.http.aclose()


class RateLimiter:
    """Per user, in memory rate limiter."""
    def __init__(self, per_min: int, per_day: int):
        self.per_min, self.per_day = per_min, per_day
        self.recent = defaultdict(deque)
        self.daily: dict = {}

    def check(self, user_id: str, tz: str):
        now = time.monotonic()
        dq = self.recent[user_id]
        while dq and now - dq[0] > 60:
            dq.popleft()
        if len(dq) >= self.per_min:
            raise HTTPException(429, "Too many requests. Please wait a minute.")
        day = datetime.now(ZoneInfo(tz)).date().isoformat()
        d, n = self.daily.get(user_id, (day, 0))
        if d != day:
            d, n = day, 0
        if n >= self.per_day:
            raise HTTPException(429, "Daily AI limit reached for today.")
        dq.append(now)
        self.daily[user_id] = (d, n + 1)


app = FastAPI(title="BOLL BILL API", version="2.0.0", lifespan=lifespan)

# Setup CORS
origins = settings.allowed_origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if "*" in origins else origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _db(request: Request, user: User) -> DB:
    return DB(request.app.state.settings.supabase_url,
              request.app.state.settings.supabase_anon_key,
              user.token, request.app.state.http)


async def _shop(db: DB) -> dict:
    rows = await db.select("shops", [("limit", "1")])
    if not rows:
        raise HTTPException(404, "Shop details not found.")
    return rows[0]


def _http(e: Exception) -> HTTPException:
    if isinstance(e, DBError):
        return HTTPException(e.status, e.message)
    if isinstance(e, AgentError):
        return HTTPException(400, e.message)
    return HTTPException(500, "Internal server error")


# ---------------- HEALTH & ROOT ----------------

@app.get("/health")
async def health(request: Request):
    s = request.app.state.settings
    return {
        "status": "ok",
        "service": "bollbill-api",
        "release": "2.0.0",
        "supabase_configured": bool(s.supabase_url and s.supabase_anon_key),
        "ai_configured": bool(request.app.state.claude)
    }


# ---------------- RELEASE 2: FEATURE 2 (PURCHASE FILE IMPORT) ----------------

@app.post("/api/pricelist/import/parse")
async def parse_import_file(
    request: Request,
    file: UploadFile = File(...),
    margin_pct: float = Form(0.0),
    user: User = Depends(current_user)
):
    """Parses purchase CSV/TSV, detects columns, matches aliases/items, returns preview."""
    try:
        content_bytes = await file.read()
        try:
            content_str = content_bytes.decode("utf-8")
        except UnicodeDecodeError:
            content_str = content_bytes.decode("latin-1")

        headers, data_rows = parse_csv_content(content_str)
        if not data_rows:
            return {"error": "File is empty or invalid", "rows": [], "detected_columns": {}}

        col_map = detect_columns(headers)
        
        db = _db(request, user)
        items = await db.select("items")
        aliases = await db.select("item_aliases")

        preview = match_and_preview(data_rows, col_map, items, aliases, margin_pct)

        return {
            "filename": file.filename,
            "total_rows": len(preview),
            "detected_columns": col_map,
            "preview": preview
        }
    except Exception as e:
        log.exception("parse_import_file failed")
        raise _http(e)


class CommitImportRow(BaseModel):
    name: str
    qty: float
    purchase_price: float = 0.0
    selling_price: float = 0.0
    unit: str = "piece"
    hsn: Optional[str] = ""
    status: str  # 'update' or 'new'
    matched_item_id: Optional[str] = None


class CommitImportRequest(BaseModel):
    filename: str
    stock_mode: str = "add"  # 'add' or 'replace'
    rows: List[CommitImportRow]


@app.post("/api/pricelist/import/commit")
async def commit_import(
    request: Request,
    body: CommitImportRequest,
    user: User = Depends(current_user)
):
    """Commits confirmed import rows in Supabase and records batch for undo."""
    db = _db(request, user)
    try:
        shop = await _shop(db)
        shop_id = shop["id"]

        updated_count = 0
        added_count = 0
        skipped_count = 0

        # Create batch record
        batch = await db.insert("import_batches", {
            "shop_id": shop_id,
            "filename": body.filename,
            "status": "committed",
            "summary": {"stock_mode": body.stock_mode, "count": len(body.rows)}
        })
        batch_id = batch["id"]

        existing_items = {it["id"]: it for it in await db.select("items")}

        for r in body.rows:
            if not r.name or r.qty < 0:
                skipped_count += 1
                continue

            if r.status == "update" and r.matched_item_id and r.matched_item_id in existing_items:
                ex = existing_items[r.matched_item_id]
                old_stock = float(ex.get("stock") or 0.0)
                new_stock = (old_stock + r.qty) if body.stock_mode == "add" else r.qty
                
                patch_data = {
                    "stock": new_stock,
                    "purchase_price": r.purchase_price
                }
                if r.selling_price > 0:
                    patch_data["price"] = r.selling_price
                if r.unit:
                    patch_data["unit"] = r.unit
                if r.hsn:
                    patch_data["hsn_code"] = r.hsn

                await db.patch("items", [("id", f"eq.{r.matched_item_id}")], patch_data)
                
                # Record undo log
                await db.insert("import_batch_rows", {
                    "batch_id": batch_id,
                    "item_id": r.matched_item_id,
                    "before_data": ex,
                    "after_data": patch_data
                })
                updated_count += 1

            else:
                # Insert as new item
                new_item_payload = {
                    "shop_id": shop_id,
                    "name": r.name,
                    "unit": r.unit or "piece",
                    "price": r.selling_price if r.selling_price > 0 else r.purchase_price,
                    "purchase_price": r.purchase_price,
                    "stock": r.qty,
                    "hsn_code": r.hsn or ""
                }
                created = await db.insert("items", new_item_payload)
                await db.insert("import_batch_rows", {
                    "batch_id": batch_id,
                    "item_id": created["id"],
                    "before_data": None,
                    "after_data": new_item_payload
                })
                added_count += 1

        return {
            "ok": True,
            "batch_id": batch_id,
            "summary": {
                "updated": updated_count,
                "added": added_count,
                "skipped": skipped_count
            }
        }
    except Exception as e:
        log.exception("commit_import failed")
        raise _http(e)


@app.post("/api/pricelist/import/{batch_id}/undo")
async def undo_import(batch_id: str, request: Request, user: User = Depends(current_user)):
    """Reverts an import batch back to its previous stock and price state."""
    db = _db(request, user)
    try:
        batches = await db.select("import_batches", [("id", f"eq.{batch_id}"), ("status", "eq.committed")])
        if not batches:
            raise HTTPException(404, "Batch not found or already undone.")
        
        batch_rows = await db.select("import_batch_rows", [("batch_id", f"eq.{batch_id}")])
        reverted = 0

        for br in batch_rows:
            item_id = br["item_id"]
            before = br.get("before_data")
            if before is None:
                # Newly inserted item -> delete or zero stock
                await db.patch("items", [("id", f"eq.{item_id}")], {"stock": 0})
            else:
                # Restore previous values
                await db.patch("items", [("id", f"eq.{item_id}")], {
                    "stock": before.get("stock"),
                    "price": before.get("price"),
                    "purchase_price": before.get("purchase_price", 0)
                })
            reverted += 1

        await db.patch("import_batches", [("id", f"eq.{batch_id}")], {"status": "undone"})
        return {"ok": True, "reverted_items": reverted}
    except Exception as e:
        log.exception("undo_import failed")
        raise _http(e)


# ---------------- RELEASE 2: FEATURE 6 (UDHAAR AGENT & INBOX) ----------------

@app.get("/api/inbox/count")
async def get_inbox_count(request: Request, user: User = Depends(current_user)):
    """Lightweight counter for pending reminder approvals badge."""
    db = _db(request, user)
    try:
        reminders = await db.select("udhaar_reminders", [("status", "eq.pending")])
        return {"pending_count": len(reminders)}
    except Exception as e:
        raise _http(e)


@app.get("/api/inbox")
async def list_inbox(
    request: Request,
    status: str = "pending",
    user: User = Depends(current_user)
):
    """Retrieve inbox reminders filtered by status."""
    db = _db(request, user)
    try:
        params = [("order", "created_at.desc"), ("limit", "50")]
        if status:
            params.append(("status", f"eq.{status}"))
        items = await db.select("udhaar_reminders", params)
        return {"items": items}
    except Exception as e:
        raise _http(e)


@app.post("/api/inbox/scan")
async def scan_overdue_udhaar(request: Request, user: User = Depends(current_user)):
    """Runs daily scan logic to identify overdue Udhaar and generate pending drafts."""
    db = _db(request, user)
    try:
        shop = await _shop(db)
        settings_rows = await db.select("agent_settings")
        agent_cfg = settings_rows[0] if settings_rows else {
            "remind_after_days": 7,
            "language": "hinglish"
        }

        bills = await db.select("bills", [("pay_method", "eq.Udhaar"), ("paid", "eq.false")])
        flags_rows = await db.select("customer_flags")
        flags = {f["customer_phone"]: f for f in flags_rows if f.get("customer_phone")}

        now = datetime.now(timezone.utc)
        candidates = find_overdue_bills(bills, agent_cfg, flags, now)
        created_count = 0

        for c in candidates:
            # Check if reminder already drafted
            existing = await db.select("udhaar_reminders", [("udhaar_id", f"eq.{c['udhaar_id']}"), ("level", "eq.1")])
            if existing:
                continue

            draft_msg = draft_reminder(
                c["customer_name"],
                shop["name"],
                c["amount_due"],
                c["days_overdue"],
                level=1,
                language=agent_cfg.get("language", "hinglish")
            )

            await db.insert("udhaar_reminders", {
                "shop_id": shop["id"],
                "udhaar_id": c["udhaar_id"],
                "customer_name": c["customer_name"],
                "customer_phone": c["customer_phone"],
                "amount_due": c["amount_due"],
                "level": 1,
                "draft_text": draft_msg,
                "status": "pending"
            })
            created_count += 1

        return {"ok": True, "new_drafts": created_count, "scanned_bills": len(bills)}
    except Exception as e:
        log.exception("scan_overdue_udhaar failed")
        raise _http(e)


class AllowReminderRequest(BaseModel):
    final_text: Optional[str] = None


@app.post("/api/inbox/{reminder_id}/allow")
async def allow_reminder(
    reminder_id: str,
    body: AllowReminderRequest,
    request: Request,
    user: User = Depends(current_user)
):
    """Shopkeeper approves reminder message for sending."""
    db = _db(request, user)
    try:
        rows = await db.select("udhaar_reminders", [("id", f"eq.{reminder_id}"), ("status", "eq.pending")])
        if not rows:
            raise HTTPException(404, "Reminder not found or already processed.")
        
        rem = rows[0]
        final = body.final_text or rem["draft_text"]
        now = datetime.now(timezone.utc).isoformat()

        await db.patch("udhaar_reminders", [("id", f"eq.{reminder_id}")], {
            "status": "sent",
            "final_text": final,
            "approved_at": now,
            "sent_at": now
        })

        # Audit log
        await db.insert("agent_audit_log", {
            "shop_id": rem["shop_id"],
            "action": "reminder_sent",
            "details": {"reminder_id": reminder_id, "customer": rem["customer_name"], "text": final}
        })

        return {"ok": True, "status": "sent", "sent_text": final}
    except Exception as e:
        log.exception("allow_reminder failed")
        raise _http(e)


@app.post("/api/inbox/{reminder_id}/deny")
async def deny_reminder(
    reminder_id: str,
    request: Request,
    snooze_days: int = 7,
    user: User = Depends(current_user)
):
    """Shopkeeper denies or snoozes reminder message."""
    db = _db(request, user)
    try:
        now = datetime.now(timezone.utc)
        snooze_until = (now + timedelta(days=snooze_days)).isoformat()
        await db.patch("udhaar_reminders", [("id", f"eq.{reminder_id}")], {
            "status": "denied",
            "snooze_until": snooze_until
        })
        return {"ok": True, "status": "denied", "snooze_until": snooze_until}
    except Exception as e:
        raise _http(e)


# ---------------- AI CHAT & VOICE BILL ASSISTANT ----------------

class VoiceDraftRequest(BaseModel):
    speech: str = Field(..., max_length=500)


@app.post("/agent/voice-bill")
async def voice_bill(body: VoiceDraftRequest, request: Request, user: User = Depends(current_user)):
    s = request.app.state.settings
    request.app.state.limiter.check(user.id, s.timezone)
    db = _db(request, user)
    try:
        shop = await _shop(db)
        items = await db.select("items", [("select", "name,aliases,price,unit"), ("limit", "500")])
        if not request.app.state.claude:
            # Fallback mock draft when Anthropic key is not active
            return {"draft": {"lines": [], "unmatched": [body.speech], "customer": ""}}

        draft, usage = await agent.voice_bill_draft(
            request.app.state.claude, s.model_fast, items, body.speech)
        return {"draft": draft}
    except Exception as e:
        log.exception("voice_bill failed")
        raise _http(e)


class ChatMsg(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    message: str = Field(..., max_length=1000)
    history: List[ChatMsg] = Field(default_factory=list)


@app.post("/agent/chat")
async def chat(body: ChatRequest, request: Request, user: User = Depends(current_user)):
    s = request.app.state.settings
    request.app.state.limiter.check(user.id, s.timezone)
    db = _db(request, user)
    try:
        shop = await _shop(db)
        if not request.app.state.claude:
            return {
                "reply": "Boll Bill backend active. To enable full AI chat, configure ANTHROPIC_API_KEY.",
                "pending_actions": []
            }

        box = ToolBox(db, shop, s.timezone, "chat-run")
        reply, calls, usage = await agent.chat(
            request.app.state.claude, s.model_smart, box, s.timezone, body.message,
            [m.model_dump() for m in body.history], s.max_tool_rounds)
        return {"reply": reply, "pending_actions": box.pending_actions}
    except Exception as e:
        log.exception("chat failed")
        raise _http(e)
