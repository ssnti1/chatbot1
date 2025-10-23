from __future__ import annotations
import re
from typing import Literal

Intent = Literal["search", "more", "faq"]

_SESSIONS: dict[str, dict] = {}

def _norm(s: str) -> str:
    import unicodedata
    s = unicodedata.normalize("NFKD", s).encode("ascii","ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+"," ", s)
    s = re.sub(r"\s+"," ", s).strip()
    return s

def get_state(session_id: str) -> dict:
    if session_id not in _SESSIONS:
        _SESSIONS[session_id] = {
            "espacio": None,
            "necesidad": None,
            "preferencias": {},  # ya no guardamos W/IP/K/sockets/etc.
            "historial": [],
            "page": 0,
            "last_query": None,
            "last_intent": None,
            "result_seed": None,
        }
    return _SESSIONS[session_id]

def update_state(session_id: str, message: dict) -> None:
    st = get_state(session_id)
    st["historial"].append(message)

def is_keyword_signal(msg: str) -> bool:
    low = _norm(msg)
    return any(kw in low for kw in (
        "mas", "ver mas", "muestrame mas", "otras", "otros", "siguiente", "siguientes",
        "mas para", "muestrame otras", "muestrame otros", "ver mas resultados"
    ))

def classify_intent(msg: str) -> Intent:
    if is_keyword_signal(msg):
        return "more"
    return "search"

def _parse_prefs(msg: str) -> dict:
    """
    INTENCIONALMENTE VACÍO.
    Antes extraíamos W/IP/K/sockets/etc. del texto; ahora no guardamos
    ninguna preferencia técnica desde el mensaje del usuario.
    """
    return {}

def maybe_extract_slots(msg: str, state: dict) -> None:
    prefs = _parse_prefs(msg)
    if prefs:
        state.setdefault("preferencias", {}).update(prefs)

VALID_CATEGORIES: tuple[str, ...] = ()
