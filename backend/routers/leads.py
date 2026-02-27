from __future__ import annotations
from typing import Any, Mapping

from fastapi import APIRouter, Request
from pydantic import BaseModel

# 👇 Importa tu cliente de DataCRM
from backend.services.datacrm_client import send_contact_to_datacrm

router = APIRouter(prefix="/leads", tags=["Leads"])


class LeadIn(BaseModel):
    name: str
    email: str
    phone: str
    profession: str
    city: str
    session_id: str = ""


@router.post("/")
async def guardar_lead(lead: LeadIn, request: Request):
    """
    Recibe el lead del chatbot, lo puede guardar en tu BD
    y luego lo envía a DataCRM.
    """
    user_agent = request.headers.get("User-Agent", "Unknown")
    created_at = request.headers.get("Date", "")

    raw = lead.dict()

    # 1️⃣ (Opcional) Guardar en tu BASE DE DATOS LOCAL
    # aquí iría la llamada a tu función de BD si ya la tienes,
    # por ejemplo:
    # save_lead_in_db(raw, user_agent, created_at)

    # 2️⃣ Enviar a DataCRM
    send_contact_to_datacrm(raw)

    return {"status": "ok", "message": "Lead procesado correctamente"}
