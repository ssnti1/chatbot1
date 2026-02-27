from fastapi import APIRouter, Query
from fastapi.responses import HTMLResponse
import sqlite3
from pathlib import Path
import html

from .db import DB_PATH as CHAT_DB_PATH, init_db

# Reutilizamos el mismo cliente LLM que el chat
try:
    from backend.services.openai_client import chat as llm_chat
except Exception:
    try:
        from openai_client import chat as llm_chat
    except Exception:
        llm_chat = None  


router = APIRouter(prefix="/history", tags=["Historial"])

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LEADS_DB_PATH = DATA_DIR / "leads.db"


def build_session_summary(mensajes: list[tuple[str, str, str]]) -> str:
    """
    Genera un resumen breve y natural del interés del cliente usando el LLM.
    mensajes: lista de tuplas (mensaje_usuario, respuesta_bot, timestamp)
    """
    # Si por algún motivo no tenemos LLM disponible:
    if llm_chat is None:
        return "Resumen no disponible (cliente LLM no configurado en el servidor)."

    # Tomamos los turnos de conversación (usuario + bot)
    turns = []
    for user, bot, ts in mensajes:
        if user:
            turns.append(f"Usuario: {user}")
        if bot:
            turns.append(f"Asistente: {bot}")

    if not turns:
        return "No se encontraron mensajes del cliente para resumir."

    # Limitamos tamaño: si hay demasiados mensajes, nos quedamos con los primeros y los últimos
    joined = "\n".join(turns)
    if len(joined) > 6000:
        head = "\n".join(turns[:30])
        tail = "\n".join(turns[-30:])
        joined = head + "\n...\n" + tail

    system_prompt = (
        "Eres un analista de conversaciones para Ecolite, una empresa de iluminación LED en Colombia.\n"
        "Te daré la transcripción de un chat entre un cliente y un asistente.\n\n"
        "Tu tarea es escribir un RESUMEN MUY BREVE, en español neutro, en 1 o 2 frases, que responda:\n"
        "- ¿Qué está buscando el cliente? (tipo de proyecto de iluminación y espacios: bodega, oficina, casa, etc.)\n"
        "- ¿Qué tipo de productos o especificaciones le interesan? (paneles, reflectores, highbay, tiras LED, potencias, temperatura de color, etc.)\n\n"
        "No devuelvas bullets ni títulos. No repitas los mensajes literalmente. No menciones al asistente.\n"
        "Ejemplos de estilo:\n"
        "- \"El usuario quiere iluminar una bodega y un local comercial con luminarias tipo highbay y paneles LED, y pidió orientación sobre potencias y cantidad de equipos.\"\n"
        "- \"La conversación se centró en iluminación para oficina y áreas residenciales, con interés en paneles 60x60 y downlights empotrables, incluyendo precios y cotización.\"\n"
    )

    # Usamos el mismo helper llm_chat(sys_prompt, user_text) que en chat.py
    try:
        summary = llm_chat(system_prompt, joined) or ""
    except Exception:
        return "No se pudo generar el resumen automáticamente."

    summary = (summary or "").strip()
    if not summary:
        return "No se pudo generar el resumen automáticamente."

    return summary


@router.get("/", response_class=HTMLResponse)
def historial(session_id: str | None = Query(default=None),
              q: str | None = Query(default=None)):
    """
    Panel interno de historial de conversaciones del Ecolite Assistant.
    - Lista todas las sesiones (agrupadas por session_id).
    - Enriquecido con datos de leads cuando estén disponibles.
    - Vista de detalle tipo inbox / CRM sobre una sesión concreta.
    """
    # Aseguramos estructura de BD de chat
    init_db()

    # --- 1) Sesiones agregadas desde chat.db ---
    con_chat = sqlite3.connect(CHAT_DB_PATH)
    cur_chat = con_chat.cursor()
    cur_chat.execute(
        """
        SELECT
            session_id,
            COUNT(id)      AS total_msgs,
            MIN(timestamp) AS first_time,
            MAX(timestamp) AS last_time
        FROM conversaciones
        GROUP BY session_id
        ORDER BY last_time DESC
        """
    )
    chat_rows = cur_chat.fetchall()

    # --- 2) Enriquecer con datos de leads desde leads.db (si existe) ---
    sesiones: list[tuple] = []
    con_leads = None
    cur_leads = None
    try:
        con_leads = sqlite3.connect(LEADS_DB_PATH)
        cur_leads = con_leads.cursor()
    except Exception:
        cur_leads = None

    for sid, total_msgs, first_time, last_time in chat_rows:
        name = email = city = profession = phone = None
        if cur_leads is not None:
            try:
                cur_leads.execute(
                    """
                    SELECT name, email, city, profession, phone
                    FROM leads
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    (sid,),
                )
                row = cur_leads.fetchone()
                if row:
                    name, email, city, profession, phone = row
            except sqlite3.OperationalError:
                # Si la tabla aún no existe, seguimos sin datos de lead
                pass

        sesiones.append(
            (
                sid,         
                name,         
                email,        
                city,         
                profession,   
                phone,        
                total_msgs,   
                first_time, 
                last_time,    
            )
        )

    if con_leads is not None:
        con_leads.close()

    # --- 3) Filtro de búsqueda por texto libre ---
    if q:
        q_low = q.lower()

        def _match(val: str | None) -> bool:
            return q_low in (val or "").lower()

        sesiones = [
            s
            for s in sesiones
            if _match(str(s[0]))  
            or _match(s[1])      
            or _match(s[2])     
            or _match(s[3])      
            or _match(s[4])      
            or _match(s[5]) 
        ]

    # --- 4) Mensajes de la sesión seleccionada ---
    mensajes: list[tuple] = []
    if session_id:
        cur_chat.execute(
            """
            SELECT mensaje_usuario, respuesta_bot, timestamp
            FROM conversaciones
            WHERE session_id = ?
            ORDER BY id ASC
            """,
            (session_id,),
        )
        mensajes = cur_chat.fetchall()

    con_chat.close()

    # --- 5) Métricas generales ---
    num_sessions = len(sesiones)
    total_messages = sum(s[6] for s in sesiones) if sesiones else 0

    selected = next((s for s in sesiones if str(s[0]) == str(session_id)),
                    None) if session_id else None

    session_summary_html = ""
    if selected and mensajes:
        raw_summary = build_session_summary(mensajes)
        session_summary_html = html.escape(raw_summary).replace("\n", "<br>")

    q_display = html.escape(q or "")
    session_id_display = html.escape(str(session_id)) if session_id else ""

    def esc(value):
        return html.escape(value or "")

    # --- 6) HTML – layout 3 columnas, sidebar + main scrolleables ---
    html_out = f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8" />
<title>Ecolite Historial · Historial</title>
<meta name="viewport" content="width=device-width, initial-scale=1" />
<style>
:root {{
  --bg-page: #f5f5f7;
  --bg-shell: #f9fafb;
  --bg-surface: #ffffff;
  --bg-soft: #f3f4f6;
  --border-subtle: #e5e7eb;
  --border-strong: #d1d5db;
  --accent: #2563eb;
  --accent-soft: #eff6ff;
  --accent-strong: #1d4ed8;
  --text-main: #111827;
  --text-muted: #6b7280;
  --text-soft: #9ca3af;
  --radius-lg: 18px;
  --radius-md: 12px;
  --shadow-soft: 0 18px 40px rgba(15,23,42,0.10);
  --shadow-card: 0 10px 30px rgba(15,23,42,0.06);
  --font-sans: system-ui, -apple-system, BlinkMacSystemFont, "SF Pro Text", "Segoe UI", sans-serif;
}}

* {{
  box-sizing: border-box;
}}

body {{
  margin: 0;
  font-family: var(--font-sans);
  background: radial-gradient(circle at top, #e5e7eb 0, #f9fafb 45%, #f3f4f6 100%);
  color: var(--text-main);
  height: 100vh;
  overflow: hidden;
}}

.app-shell {{
  max-width: 1320px;
  margin: 0 auto;
  padding: 10px 16px 18px;
  height: 100vh;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}

.app-header {{
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-radius: 999px;
  background: rgba(255,255,255,0.9);
  border: 1px solid rgba(209,213,219,0.8);
  box-shadow: 0 12px 35px rgba(15,23,42,0.08);
  backdrop-filter: blur(14px);
}}

.brand {{
  display: flex;
  align-items: center;
  gap: 10px;
}}

.brand-mark {{
  width: 26px;
  height: 26px;
  border-radius: 999px;
  background: conic-gradient(from 160deg, #1d4ed8, #22c55e, #0ea5e9, #1d4ed8);
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  color: #f9fafb;
  font-weight: 600;
}}

.brand-text {{
  display: flex;
  flex-direction: column;
  gap: 2px;
}}

.brand-title {{
  font-size: 0.92rem;
  font-weight: 600;
}}

.brand-subtitle {{
  font-size: 0.76rem;
  color: var(--text-soft);
}}

.header-metrics {{
  display: flex;
  gap: 8px;
  align-items: center;
  font-size: 0.74rem;
  color: var(--text-soft);
}}

.header-pill {{
  padding: 3px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  background: #f9fafb;
}}

.header-pill strong {{
  font-weight: 600;
  color: var(--text-main);
}}

.app-main {{
  flex: 1;
  display: grid;
  grid-template-columns: 320px minmax(0, 1.7fr) minmax(0, 0.9fr);
  gap: 12px;
  min-height: 0;
}}

.surface {{
  background: var(--bg-surface);
  border-radius: 20px;
  border: 1px solid rgba(209,213,219,0.8);
  box-shadow: var(--shadow-soft);
}}

.sidebar {{
  padding: 14px 14px 16px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;       /* permite que la lista interna haga scroll */
  overflow: hidden;
}}

.sidebar-header {{
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 10px;
}}

.sidebar-title {{
  font-size: 0.9rem;
  font-weight: 600;
}}

.sidebar-subtitle {{
  font-size: 0.78rem;
  color: var(--text-muted);
}}

.search-box {{
  position: relative;
  margin-bottom: 10px;
}}

.search-box input {{
  width: 100%;
  padding: 8px 30px 8px 26px;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  font-size: 0.82rem;
  background: var(--bg-soft);
  color: var(--text-main);
  outline: none;
}}

.search-box input::placeholder {{
  color: var(--text-soft);
}}

.search-box input:focus {{
  border-color: var(--accent);
  box-shadow: 0 0 0 1px rgba(37,99,235,0.18);
  background: #ffffff;
}}

.search-icon {{
  position: absolute;
  left: 10px;
  top: 50%;
  transform: translateY(-50%);
  font-size: 0.86rem;
  color: var(--text-soft);
}}

.sidebar-footnote {{
  font-size: 0.74rem;
  color: var(--text-soft);
  margin-bottom: 6px;
}}

.session-list {{
  flex: 1 1 auto;
  overflow-y: auto;    /* scroll en la lista de chats */
  padding-right: 4px;
  margin-top: 4px;
}}

.session-empty {{
  font-size: 0.8rem;
  color: var(--text-soft);
  text-align: center;
  margin-top: 18px;
}}

.session-link {{
  text-decoration: none;
  color: inherit;
  display: block;
  margin-bottom: 6px;
}}

.session-card {{
  border-radius: 14px;
  padding: 8px 10px;
  background: #ffffff;
  border: 1px solid transparent;
  box-shadow: 0 1px 3px rgba(15,23,42,0.06);
  transition: border-color .16s ease, box-shadow .16s ease, background .16s ease, transform .12s ease;
}}

.session-card:hover {{
  border-color: var(--border-subtle);
  box-shadow: var(--shadow-card);
  transform: translateY(-1px);
}}

.session-card.active {{
  border-color: var(--accent);
  background: var(--accent-soft);
}}

.session-main {{
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 8px;
}}

.session-phone {{
  font-size: 0.86rem;
  font-weight: 600;
}}

.session-name {{
  font-size: 0.8rem;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}}

.session-meta {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 4px;
  font-size: 0.74rem;
  color: var(--text-soft);
}}

.badge-pill {{
  padding: 2px 7px;
  border-radius: 999px;
  background: var(--bg-soft);
  border: 1px solid var(--border-subtle);
}}

.main-conversation {{
  padding: 14px 16px 18px;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;       /* permite que el chat interno haga scroll */
}}

.main-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}}

.main-title-block {{
  display: flex;
  flex-direction: column;
  gap: 3px;
}}

.main-title {{
  font-size: 0.96rem;
  font-weight: 600;
}}

.main-subtitle {{
  font-size: 0.8rem;
  color: var(--text-muted);
}}

.back-link {{
  text-decoration: none;
  font-size: 0.78rem;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  background: #ffffff;
  color: var(--accent-strong);
  display: inline-flex;
  align-items: center;
  gap: 4px;
}}

.back-link:hover {{
  border-color: var(--accent);
  background: var(--accent-soft);
}}

.chat-scroll {{
  flex: 1 1 auto;
  overflow-y: auto;    /* scroll en el cuerpo del chat */
  padding-right: 4px;
  padding-top: 6px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}}

.msg-group {{
  display: flex;
  flex-direction: column;
  gap: 4px;
}}

.msg-row {{
  display: flex;
  gap: 8px;
}}

.msg-bubble {{
  max-width: 80%;
  padding: 9px 11px;
  border-radius: 12px;
  font-size: 0.9rem;
  line-height: 1.45;
  box-shadow: 0 1px 3px rgba(15,23,42,0.10);
}}

.msg-bubble.user {{
  background: #eef2ff;
  align-self: flex-start;
}}

.msg-bubble.bot {{
  background: #ecfdf3;
  align-self: flex-end;
}}

.msg-label {{
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-soft);
  margin-bottom: 2px;
}}

.msg-text {{
  white-space: pre-wrap;
  word-wrap: break-word;
  color: var(--text-main);
}}

.msg-timestamp {{
  font-size: 0.72rem;
  color: var(--text-soft);
  margin-top: 2px;
}}

.empty-main {{
  margin: auto;
  text-align: center;
  max-width: 360px;
  color: var(--text-muted);
}}

.empty-main h2 {{
  font-size: 1.02rem;
  margin-bottom: 6px;
}}

.empty-main p {{
  font-size: 0.86rem;
}}

.right-panel {{
  padding: 14px 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  min-height: 0;
  overflow-y: auto;   /* scroll en el panel derecho si se llena */
}}

.card {{
  border-radius: 16px;
  border: 1px solid var(--border-subtle);
  background: var(--bg-soft);
  padding: 10px 12px 12px;
  box-shadow: 0 1px 3px rgba(15,23,42,0.06);
}}

.card-title {{
  font-size: 0.86rem;
  font-weight: 600;
  margin-bottom: 6px;
}}

.card-subtitle {{
  font-size: 0.76rem;
  color: var(--text-soft);
  margin-bottom: 8px;
}}

.chips {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  font-size: 0.78rem;
}}

.chip {{
  padding: 4px 8px;
  border-radius: 999px;
  border: 1px solid var(--border-subtle);
  background: #ffffff;
}}

.chip strong {{
  font-weight: 600;
}}

.timeline {{
  margin-top: 4px;
  padding-left: 4px;
  font-size: 0.78rem;
  color: var(--text-muted);
}}

.timeline-item {{
  margin-bottom: 4px;
}}

.timeline-label {{
  font-weight: 500;
  color: var(--text-main);
}}

.session-summary {{
  margin-top: 8px;
  font-size: 0.8rem;
  color: var(--text-muted);
  padding-top: 6px;
  border-top: 1px dashed var(--border-subtle);
}}

.session-summary-title {{
  font-weight: 600;
  margin-bottom: 4px;
}}

@media (max-width: 1080px) {{
  .app-main {{
    grid-template-columns: 290px minmax(0, 1.5fr);
    grid-template-rows: minmax(0, 1fr) minmax(0, 0.9fr);
    grid-template-areas:
      "sidebar main"
      "sidebar right";
  }}
  .sidebar {{ grid-area: sidebar; }}
  .main-conversation {{ grid-area: main; }}
  .right-panel {{ grid-area: right; }}
}}

@media (max-width: 840px) {{
  body {{
    overflow: auto;
  }}
  .app-shell {{
    height: auto;
  }}
  .app-main {{
    grid-template-columns: 1fr;
    grid-template-rows: auto auto auto;
  }}
}}
</style>
</head>
<body>
<div class="app-shell">
  <header class="app-header">
    <div class="brand">
      <div class="brand-mark">E</div>
      <div class="brand-text">
        <div class="brand-title">Ecolite Historial</div>
        <div class="brand-subtitle">Customer Conversation Console</div>
      </div>
    </div>
    <div class="header-metrics">
      <div class="header-pill"><strong>{num_sessions}</strong>&nbsp;sesiones</div>
      <div class="header-pill"><strong>{total_messages}</strong>&nbsp;mensajes</div>
    </div>
  </header>

  <main class="app-main">
    <aside class="sidebar surface">
      <div class="sidebar-header">
        <div class="sidebar-title">Conversaciones</div>
        <div class="sidebar-subtitle">Centro de atención · mensajes</div>
      </div>

      <form method="get" class="search-box">
        <span class="search-icon">🔍</span>
        <input
          type="text"
          name="q"
          value="{q_display}"
          placeholder="Buscar 310..., nombre, correo, ciudad..."
          autocomplete="off"
        />
      </form>

      <div class="sidebar-footnote">
        Ordenado por última interacción. El identificador suele ser el <strong>número de teléfono</strong>.
      </div>

      <div class="session-list">
"""
    if not sesiones:
        html_out += "<div class='session-empty'>No hay conversaciones aún.</div>"
    else:
        for s in sesiones:
            sid, name, email, city, prof, phone, total, first_time, last_time = s
            sid_safe = esc(str(sid))
            name_safe = esc(name or "(anónimo)")
            city_safe = esc(city or "Sin ciudad")
            prof_safe = esc(prof or "Sin rol")
            phone_safe = esc(phone or str(sid) or "Sin identificador")
            last_safe = esc(str(last_time) if last_time is not None else "")

            active_cls = "session-card active" if session_id and str(sid) == str(session_id) else "session-card"

            html_out += f"""
        <a class="session-link" href="/history?session_id={sid_safe}">
          <article class="{active_cls}">
            <div class="session-main">
              <div class="session-phone">{name_safe}</div>
              <div class="session-name">{phone_safe}</div>
            </div>
            <div class="session-meta">
              <span class="badge-pill">{total} mensajes</span>
              <span class="badge-pill">{city_safe}</span>
              <span class="badge-pill">{prof_safe}</span>
              <span class="badge-pill">Último: {last_safe}</span>
            </div>
          </article>
        </a>
"""
    html_out += """
      </div>
    </aside>

    <section class="main-conversation surface">
"""
    if session_id:
        html_out += f"""
      <div class="main-header">
        <div class="main-title-block">
          <div class="main-title"># <code>{session_id_display}</code></div>
          <div class="main-subtitle">Detalle cronológico de la conversación.</div>
        </div>
        <a href="/history" class="back-link">← Volver al listado</a>
      </div>
      <div class="chat-scroll">
"""
        if not mensajes:
            html_out += """
        <div class="empty-main">
          <h2>Sin mensajes en esta sesión</h2>
          <p>Se registró el lead, pero aún no hay intercambio con el asistente.</p>
        </div>
"""
        else:
            for user_msg, bot_msg, ts in mensajes:
                user_html = esc(user_msg or "")
                bot_html = esc(bot_msg or "")
                ts_html = esc(str(ts) or "")

                html_out += f"""
        <article class="msg-group">
          <div class="msg-row">
            <div class="msg-bubble user">
              <div class="msg-label">Usuario</div>
              <div class="msg-text">{user_html}</div>
            </div>
          </div>
          <div class="msg-row">
            <div class="msg-bubble bot">
              <div class="msg-label">Ecolite Historial</div>
              <div class="msg-text">{bot_html}</div>
            </div>
          </div>
          <div class="msg-timestamp">{ts_html}</div>
        </article>
"""
        html_out += """
      </div>
"""
    else:
        html_out += """
      <div class="empty-main">
        <h2>Selecciona una conversación</h2>
        <p>En el panel izquierdo verás todas las sesiones. Elige una para revisar el intercambio completo con tu cliente.</p>
      </div>
"""

    html_out += """
    </section>

    <aside class="right-panel surface">
      <section class="card">
        <div class="card-title">Perfil del cliente</div>
        <div class="card-subtitle">Datos capturados desde el formulario de lead.</div>
"""
    if selected:
        _sid, name, email, city, prof, phone, total, first_time, last_time = selected
        name_safe = esc(name or "(anónimo)")
        email_safe = esc(email or "Sin correo")
        city_safe = esc(city or "Sin ciudad")
        prof_safe = esc(prof or "Sin rol definido")
        phone_safe = esc(phone or str(_sid) or "Sin teléfono")

        html_out += f"""
        <div class="chips">
          <div class="chip"><strong>Nombre:</strong>&nbsp;{name_safe}</div>
          <div class="chip"><strong>Teléfono:</strong>&nbsp;{phone_safe}</div>
          <div class="chip"><strong>Email:</strong>&nbsp;{email_safe}</div>
          <div class="chip"><strong>Ciudad:</strong>&nbsp;{city_safe}</div>
          <div class="chip"><strong>Rol:</strong>&nbsp;{prof_safe}</div>
          <div class="chip"><strong>Mensajes:</strong>&nbsp;{total}</div>
        </div>
"""
    else:
        html_out += """
        <div class="chips">
          <div class="chip">Selecciona una sesión para ver el perfil del cliente.</div>
        </div>
"""

    html_out += """
      </section>

      <section class="card">
        <div class="card-title">Resumen de sesión</div>
        <div class="card-subtitle">
          Visión rápida del contexto temporal y del interés principal del cliente.
        </div>
"""
    if selected:
        _sid, name, email, city, prof, phone, total, first_time, last_time = selected
        first_safe = esc(str(first_time) if first_time is not None else "")
        last_safe = esc(str(last_time) if last_time is not None else "")

        html_out += f"""
        <div class="timeline">
          <div class="timeline-item">
            <div class="timeline-label">Primera interacción</div>
            <div>{first_safe}</div>
          </div>
          <div class="timeline-item">
            <div class="timeline-label">Última interacción</div>
            <div>{last_safe}</div>
          </div>
          <div class="timeline-item">
            <div class="timeline-label">Mensajes totales</div>
            <div>{total}</div>
          </div>
        </div>
        <div class="session-summary">
          <div class="session-summary-title">Resumen del interés del cliente</div>
          <div>{session_summary_html}</div>
        </div>
"""
    else:
        html_out += """
        <div class="timeline">
          <div class="timeline-item">
            Selecciona una sesión para ver su línea de tiempo y un resumen automático.
          </div>
        </div>
"""

    html_out += """
      </section>
    </aside>
  </main>
</div>
</body>
</html>
"""
    return HTMLResponse(html_out)
