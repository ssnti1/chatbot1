from __future__ import annotations
import requests
import hashlib
import json
from typing import Any

# ====================================
# ⚙️ CONFIGURACIÓN
# ====================================
DATACRM_URL = "https://demos.datacrm.la/demos/ecolitesas2/webservice.php"
DATACRM_USER = "gerente"
DATACRM_KEY = "I33s3VEeZ7XwTG8"
DATACRM_ASSIGNED_ID = "19x1"

# Fallback formulario público (demo)
DATACRM_WFORM_URL = "https://demos.datacrm.la/demos/ecolitesas2/index.php?module=WForms&view=SavePublicForm"
DATACRM_WFORM_ID = "MTc2NDAyNDM4Ny42MzI="


# ====================================
# 🔐 LOGIN
# ====================================
def _login() -> dict[str, Any]:
    """Login con token + accessKey (MD5)."""
    try:
        token_resp = requests.get(
            DATACRM_URL,
            params={"operation": "getchallenge", "username": DATACRM_USER},
            timeout=10,
        )
        token_data = token_resp.json()
        if not token_data.get("success"):
            raise Exception("No se pudo obtener token")

        token = token_data["result"]["token"]
        accesskey_final = hashlib.md5((token + DATACRM_KEY).encode()).hexdigest()

        login_resp = requests.post(
            DATACRM_URL,
            data={"operation": "login", "username": DATACRM_USER, "accessKey": accesskey_final},
            timeout=10,
        )
        data = login_resp.json()
        if not data.get("success"):
            raise Exception(f"Login fallido: {data}")
        return data["result"]
    except Exception as e:
        raise Exception(f"[LOGIN ERROR] {e}")


# ====================================
# 🧩 CREAR CONTACTO
# ====================================
def _create_contact(session_name: str, contact_data: dict[str, Any]) -> dict[str, Any]:
    """Crea un contacto en DataCRM usando el módulo Contacts."""
    if not contact_data.get("lastname"):
        contact_data["lastname"] = "Contacto Chatbot"
    if not contact_data.get("assigned_user_id"):
        contact_data["assigned_user_id"] = DATACRM_ASSIGNED_ID

    element = json.dumps(contact_data, ensure_ascii=False)

    payload = {
        "operation": "create",
        "sessionName": session_name,
        "elementType": "Contacts",
        "element": element,
    }

    print("[DEBUG] Payload enviado:", payload)

    resp = requests.post(DATACRM_URL, data=payload, timeout=10)
    data = resp.json()
    print("[DEBUG] Respuesta DataCRM:", data)

    if not data.get("success"):
        raise Exception(f"Error al crear contacto: {data}")

    return data["result"]


# ====================================
# 🧩 FORMULARIO DE BACKUP
# ====================================
def _create_contact_form(raw: dict[str, Any]) -> bool:
    """Envia el lead al formulario público (funciona sin permisos API)."""
    payload = {
        "publicid": DATACRM_WFORM_ID,
        "lastname": raw.get("name", ""),
        "email": raw.get("email", ""),
        "mobile": raw.get("phone", ""),
        "city": raw.get("city", ""),
        "designation": raw.get("profession", ""),
        "assigned_user_id": DATACRM_ASSIGNED_ID,
        "captcha": "5", 
    }
    r = requests.post(DATACRM_WFORM_URL, data=payload, timeout=10)
    print("[DEBUG] Fallback form status:", r.status_code)
    return r.status_code == 200


# ====================================
# 🚀 FLUJO PRINCIPAL
# ====================================
def send_contact_to_datacrm(raw: dict[str, Any]) -> None:
    """
    Envía un lead a DataCRM:
    1️⃣ Intenta por API (Contacts)
    2️⃣ Si falla, usa el formulario público
    """
    try:
        session = _login()
        session_name = session["sessionName"]


        try:
            result = _create_contact(session_name, contact)
            print("[DataCRM] ✅ Contacto creado vía API:", result.get("id"))
        except Exception as e:
            print("[DataCRM] ⚠️ Error API, usando formulario:", e)
            if _create_contact_form(raw):
                print("[DataCRM] ✅ Contacto enviado por formulario público.")
            else:
                print("[DataCRM] ❌ Falla en el formulario público también.")
    except Exception as e:
        print("[DataCRM] ❌ Error general:", e)
    