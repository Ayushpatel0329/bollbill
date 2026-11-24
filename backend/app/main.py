"""BOLL BILL AI service (FastAPI).

Browser (logged in with Supabase)  ->  this service  ->  Claude
                                           |
                                           +-> Supabase, using the USER's token (Row Level Security applies)
"""
import logging
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

import anthropic
import httpx
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from . import agent
from .auth import User, current_user
from .config import load_settings
from .db import DB
from .errors import AgentError, DBError
from .tools import ToolBox, execute_action

log = logging.getLogger("bollbill")
logging.basicConfig(level=logging.INFO)


settings = load_settings()    # fails at start-up, with a clear message, if a variable is missing


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.settings = settings
    app.state.http = httpx.AsyncClient()
    app.state.claude = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
    app.state.limiter = RateLimiter(settings.rate_limit_per_min, settings.daily_ai_limit)
    yield
    await app.state.http.aclose()


class RateLimiter:
    """Per user, in memory. With more than one server process, move this to Redis."""

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
            raise HTTPException(429, "Bahut jaldi jaldi sawaal ho rahe hain. Ek minute ruk kar try karein.")
        day = datetime.now(ZoneInfo(tz)).date().isoformat()
        d, n = self.daily.get(user_id, (day, 0))
        if d != day:
            n = 0
        if n >= self.per_day:
            raise HTTPException(429, "Aaj ki AI limit poori ho gayi. Kal phir try karein.")
        dq.append(now)
        self.daily[user_id] = (day, n + 1)


app = FastAPI(title="BOLL BILL AI", docs_url=None, redoc_url=None, lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,      # empty list = no website may call this API
    allow_methods=["GET", "POST"],
    allow_headers=["Authorization", "Content-Type"],
    max_age=600,
)


# ---------- helpers ----------------------------------------------------

def _db(request: Request, user: User) -> DB:
    s = request.app.state.settings
    return DB(s.supabase_url, s.supabase_anon_key, user.token, request.app.state.http)


async def _shop(db: DB) -> dict:
    rows = await db.select("shops", [("select", "id,name,low_stock_limit"), ("limit", "1")])
    if not rows:
        raise HTTPException(403, "Pehle apni dukaan ki details save karein.")
    return rows[0]


def _guard(request: Request, user: User):
    s = request.app.state.settings
    request.app.state.limiter.check(user.id, s.timezone)


async def _start_run(db: DB, shop_id: str, user: User, kind: str, text: str, model: str):
    try:
        row = await db.insert("agent_runs", {"shop_id": shop_id, "user_id": user.id, "kind": kind,
                                             "input": text[:2000], "model": model, "status": "running"})
        return row["id"]
    except Exception:           # logging must never break the feature
        log.exception("could not start agent_run")
        return None


async def _finish_run(db: DB, run_id, **values):
    if not run_id:
        return
    try:
        await db.patch("agent_runs", [("id", f"eq.{run_id}")], values)
    except Exception:
        log.exception("could not finish agent_run")


def _http(e: Exception):
    if isinstance(e, AgentError):
        return HTTPException(e.status, e.message)
    if isinstance(e, DBError):
        return HTTPException(e.status if e.status in (400, 401, 403, 404, 409) else 502, e.message)
    return HTTPException(500, "Kuch gadbad ho gayi. Thodi der baad try karein.")


# ---------- request bodies ----------------------------------------------

class VoiceBillIn(BaseModel):
    transcript: str = Field(min_length=2, max_length=500)


class ChatMsg(BaseModel):
    role: str
    content: str = Field(max_length=1000)


class ChatIn(BaseModel):
    message: str = Field(min_length=1, max_length=1000)
    history: list[ChatMsg] = Field(default_factory=list, max_length=20)


# ---------- endpoints ----------------------------------------------------

@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/agent/voice-bill")
async def voice_bill(body: VoiceBillIn, request: Request, user: User = Depends(current_user)):
    """Spoken sentence -> DRAFT bill. Nothing is saved; the app shows it and the owner confirms."""
    _guard(request, user)
    s = request.app.state.settings
    db = _db(request, user)
    try:
        shop = await _shop(db)
        items = await db.select("items", [("select", "name,unit,aliases"), ("order", "position.asc"),
                                          ("limit", "500")])
        if not items:
            raise HTTPException(400, "Price list khaali hai. Pehle items jodein.")
        run_id = await _start_run(db, shop["id"], user, "voice_bill", body.transcript, s.model_fast)
        try:
            draft, usage = await agent.voice_bill_draft(request.app.state.claude, s.model_fast,
                                                        items, body.transcript)
        except Exception as e:
            await _finish_run(db, run_id, status="error", error=str(e)[:500])
            raise
        await _finish_run(db, run_id, output=str(draft)[:4000], **usage)
        return draft
    except HTTPException:
        raise
    except Exception as e:
        log.exception("voice_bill failed")
        raise _http(e)


@app.post("/agent/chat")
async def chat(body: ChatIn, request: Request, user: User = Depends(current_user)):
    _guard(request, user)
    s = request.app.state.settings
    db = _db(request, user)
    try:
        shop = await _shop(db)
        run_id = await _start_run(db, shop["id"], user, "chat", body.message, s.model_smart)
        box = ToolBox(db, shop, s.timezone, run_id)
        try:
            reply, calls, usage = await agent.chat(
                request.app.state.claude, s.model_smart, box, s.timezone, body.message,
                [m.model_dump() for m in body.history], s.max_tool_rounds)
        except Exception as e:
            await _finish_run(db, run_id, status="error", error=str(e)[:500])
            raise
        await _finish_run(db, run_id, output=reply[:4000], tool_calls=calls, **usage)
        return {"reply": reply, "pending_actions": box.pending_actions}
    except HTTPException:
        raise
    except Exception as e:
        log.exception("chat failed")
        raise _http(e)


@app.get("/agent/actions")
async def list_actions(request: Request, user: User = Depends(current_user)):
    """Confirmations still waiting for the owner (so they survive a page refresh)."""
    db = _db(request, user)
    try:
        now = datetime.now(ZoneInfo("UTC")).isoformat()
        rows = await db.select("agent_actions", [
            ("select", "id,summary,created_at"), ("status", "eq.pending"),
            ("expires_at", f"gt.{now}"), ("order", "created_at.desc"), ("limit", "10")])
        return {"actions": rows}
    except Exception as e:
        raise _http(e)


async def _claim(db: DB, action_id: str, new_status: str) -> dict:
    """Atomically move pending -> new_status. Only one caller can win, so an action never runs twice."""
    now = datetime.now(ZoneInfo("UTC")).isoformat()
    rows = await db.patch("agent_actions", [
        ("id", f"eq.{action_id}"), ("status", "eq.pending"), ("expires_at", f"gt.{now}")],
        {"status": new_status, "decided_at": now})
    if not rows:
        raise HTTPException(409, "Yeh kaam pehle hi ho chuka hai ya expire ho gaya.")
    return rows[0]


@app.post("/agent/actions/{action_id}/confirm")
async def confirm_action(action_id: str, request: Request, user: User = Depends(current_user)):
    db = _db(request, user)
    try:
        action = await _claim(db, action_id, "confirmed")
        try:
            msg = await execute_action(db, action)
            await db.patch("agent_actions", [("id", f"eq.{action_id}")], {"result": msg})
            return {"ok": True, "message": msg}
        except Exception as e:
            err = e.message if isinstance(e, DBError) else "failed"
            await db.patch("agent_actions", [("id", f"eq.{action_id}")], {"status": "failed", "result": err})
            raise
    except HTTPException:
        raise
    except Exception as e:
        log.exception("confirm failed")
        raise _http(e)


@app.post("/agent/actions/{action_id}/reject")
async def reject_action(action_id: str, request: Request, user: User = Depends(current_user)):
    db = _db(request, user)
    try:
        await _claim(db, action_id, "rejected")
        return {"ok": True}
    except HTTPException:
        raise
    except Exception as e:
        raise _http(e)
