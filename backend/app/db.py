"""Tiny Supabase (PostgREST) client. Every call carries the USER's login token,
so Postgres Row Level Security decides what the user (and the AI acting for them) can see."""
import httpx

from .errors import DBError


class DB:
    def __init__(self, base_url: str, anon_key: str, token: str, client: httpx.AsyncClient):
        self._url = base_url.rstrip("/") + "/rest/v1"
        self._client = client
        self._h = {"apikey": anon_key, "Authorization": f"Bearer {token}", "Content-Type": "application/json"}

    async def _send(self, method, path, *, params=None, json=None, prefer=None):
        headers = dict(self._h)
        if prefer:
            headers["Prefer"] = prefer
        try:
            r = await self._client.request(method, self._url + path, params=params, json=json,
                                           headers=headers, timeout=15)
        except httpx.HTTPError:
            raise DBError(503, "Database se connect nahi ho paya. Thodi der baad try karein.")
        if r.status_code >= 400:
            try:
                msg = r.json().get("message") or "Database error"
            except Exception:
                msg = "Database error"
            raise DBError(r.status_code, msg)
        return r.json() if r.content else None

    async def select(self, table: str, params=None) -> list:
        return await self._send("GET", f"/{table}", params=params) or []

    async def insert(self, table: str, row: dict) -> dict:
        rows = await self._send("POST", f"/{table}", json=row, prefer="return=representation")
        return rows[0]

    async def patch(self, table: str, params, values: dict) -> list:
        return await self._send("PATCH", f"/{table}", params=params, json=values,
                                prefer="return=representation") or []

    async def rpc(self, fn: str, args: dict):
        return await self._send("POST", f"/rpc/{fn}", json=args)
