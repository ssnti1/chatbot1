from __future__ import annotations
import sqlite3, datetime
from pathlib import Path
from typing import Any, Mapping
from backend.routers import chat  
from pydantic import BaseModel
from fastapi import APIRouter, Request, Body, HTTPException

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadForm(BaseModel):
    session_id: str
    name: str

@router.post("/save")
def save_lead(form: LeadForm):
    st = chat._SESS.setdefault(form.session_id, {})
    st["lead_name"] = (form.name or "").strip()
    return {"ok": True}

DATA_DIR = Path(__file__).parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA_DIR / "leads.db"

def _conn():
    con = sqlite3.connect(DB_PATH, timeout=10, check_same_thread=False)
    con.execute("PRAGMA journal_mode=WAL;")  # Modo concurrente seguro
    con.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            name TEXT,
            email TEXT,
            phone TEXT,
            profession TEXT,
            city TEXT,
            user_agent TEXT,
            created_at TEXT
        )
    """)
    return con

_KEY_MAP = {
    "nombre": "name", "name": "name",
    "correo": "email", "email": "email", "mail": "email",
    "numero": "phone", "celular": "phone", "telefono": "phone", "tel": "phone", "phone": "phone",
    "profesion": "profession", "profesión": "profession", "profession": "profession",
    "ciudad": "city", "cuidad": "city", "city": "city",
    "session": "session_id", "session_id": "session_id",
}

def _normalize_payload(obj: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for k, v in obj.items():
        key = str(k).strip().lower()
        mapped = _KEY_MAP.get(key, key)
        if isinstance(v, str): v = v.strip()
        out[mapped] = v
    return out



@router.post("/")
async def save_lead(request: Request, payload: dict = Body(default=None)):
    raw: dict[str, Any] = {}
    if isinstance(payload, dict) and payload:
        raw = _normalize_payload(payload)
    if not raw:
        try:
            form = await request.form()
            raw = _normalize_payload(dict(form))
        except Exception:
            pass

    raw.setdefault("session_id",
        request.headers.get("x-session-id")
        or raw.get("session")
        or request.client.host
        or "web-unknown"
    )

    required = ["session_id", "name", "email", "phone", "profession", "city"]
    missing = [k for k in required if not raw.get(k)]
    if missing:
        raise HTTPException(status_code=422, detail={"error": "missing_fields", "missing": missing, "received": list(raw.keys())})

    ua = request.headers.get("user-agent", "")
    now = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"

    with _conn() as con:
        con.execute(
            """INSERT INTO leads (session_id, name, email, phone, profession, city, user_agent, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (str(raw["session_id"]), str(raw["name"]), str(raw["email"]), str(raw["phone"]),
             str(raw["profession"]), str(raw["city"]), ua, now)
        )
    return {"ok": True, "saved_at": now}
