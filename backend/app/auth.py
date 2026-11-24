"""Checks the Supabase login token the browser sends in `Authorization: Bearer <token>`.
We ask Supabase itself (/auth/v1/user), so it works with any signing-key setup."""
import hashlib
import time
from dataclasses import dataclass

import httpx
from fastapi import HTTPException, Request


@dataclass
class User:
    id: str
    email: str | None
    token: str


_CACHE: dict = {}      # sha256(token) -> (expires_at, id, email); never stores the raw token
_TTL = 60
_MAX = 2000


def _bearer(request: Request) -> str:
    h = request.headers.get("authorization", "")
    if not h.lower().startswith("bearer ") or len(h) < 20:
        raise HTTPException(401, "Login zaroori hai.")
    return h[7:].strip()


async def current_user(request: Request) -> User:
    token = _bearer(request)
    key = hashlib.sha256(token.encode()).hexdigest()
    now = time.monotonic()
    hit = _CACHE.get(key)
    if hit and hit[0] > now:
        return User(hit[1], hit[2], token)

    s = request.app.state
    try:
        r = await s.http.get(
            f"{s.settings.supabase_url}/auth/v1/user",
            headers={"apikey": s.settings.supabase_anon_key, "Authorization": f"Bearer {token}"},
            timeout=10,
        )
    except httpx.HTTPError:
        raise HTTPException(503, "Login check nahi ho paya. Thodi der baad try karein.")
    if r.status_code != 200:
        raise HTTPException(401, "Login expire ho gaya. Dobara login karein.")
    data = r.json()
    if len(_CACHE) >= _MAX:
        for k in [k for k, v in _CACHE.items() if v[0] <= now] or list(_CACHE)[: _MAX // 2]:
            _CACHE.pop(k, None)
    _CACHE[key] = (now + _TTL, data["id"], data.get("email"))
    return User(data["id"], data.get("email"), token)
