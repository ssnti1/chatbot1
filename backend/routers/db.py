import sqlite3
from pathlib import Path
from datetime import datetime

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "chat.db"

def init_db():
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()

    # Tabla de conversaciones
    cur.execute("""
        CREATE TABLE IF NOT EXISTS conversaciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            mensaje_usuario TEXT,
            respuesta_bot TEXT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # 🆕 Tabla de leads (datos del formulario)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS leads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            name TEXT,
            email TEXT,
            city TEXT,
            profession TEXT,
            phone TEXT
        )
    """)

    con.commit()
    con.close()


def guardar_conversacion(session_id: str, mensaje_usuario: str, respuesta_bot: str):
    """Guarda un mensaje en la base de datos."""
    init_db()
    con = sqlite3.connect(DB_PATH)
    cur = con.cursor()
    cur.execute("""
        INSERT INTO conversaciones (session_id, mensaje_usuario, respuesta_bot, timestamp)
        VALUES (?, ?, ?, ?)
    """, (session_id, mensaje_usuario, respuesta_bot, datetime.now().isoformat(timespec="seconds")))
    con.commit()
    con.close()
