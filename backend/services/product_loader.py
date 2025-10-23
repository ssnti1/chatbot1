from __future__ import annotations
import json
from pathlib import Path
from typing import Dict, Tuple

_CANDIDATES = [
    Path(__file__).parent.parent / "data" / "productos.json", 
    Path.cwd() / "backend" / "data" / "productos.json",  
    Path.cwd() / "data" / "productos.json", 
    Path.cwd() / "productos.json",
]

PRODUCTOS: Dict[str, dict] = {}
DATA_PATH: Path | None = None

def _find_path() -> Path:
    for p in _CANDIDATES:
        if p.exists():
            return p
    raise FileNotFoundError(
        "No se encontró productos.json en: " + ", ".join(str(p) for p in _CANDIDATES)
    )

def _load_from_disk() -> Dict[str, dict]:
    global DATA_PATH
    DATA_PATH = _find_path()
    with DATA_PATH.open("r", encoding="utf-8") as f:
        raw = json.load(f)

    if isinstance(raw, dict):
        return raw
    if isinstance(raw, list):
        productos: Dict[str, dict] = {}
        for item in raw:
            key = str(item.get("sku") or item.get("id") or item.get("name"))
            productos[key] = item
        return productos

    raise ValueError("Formato de productos.json no soportado (usa dict o lista).")

def load_products() -> Tuple[Dict[str, dict], Path]:
    """Carga y cachea el catálogo; retorna (productos, ruta_encontrada)."""
    global PRODUCTOS, DATA_PATH
    if not PRODUCTOS:
        PRODUCTOS = _load_from_disk()
    return PRODUCTOS, DATA_PATH or _find_path()

def reload_products() -> Tuple[Dict[str, dict], Path]:
    """Recarga desde disco (útil para debug)."""
    global PRODUCTOS
    PRODUCTOS = _load_from_disk()
    return PRODUCTOS, DATA_PATH 
