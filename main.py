from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.routers import chat
from backend.routers import leads  # ← NUEVO

app = FastAPI(title="Ecolite Assistant", version="3.3")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Estáticos (sirve /static/* desde la carpeta frontend)
app.mount("/static", StaticFiles(directory="frontend"), name="static")

# HTML principal (usa tu HTML preferido en frontend/chatbox.html)
@app.get("/")
def index():
    return FileResponse("frontend/chatbox.html")

# Routers
app.include_router(chat.router)
app.include_router(leads.router)  # ← NUEVO

@app.get("/healthz")
def healthz():
    return {"ok": True}

from backend.services.product_loader import load_products  # noqa: E402
@app.get("/__debug/catalog")
def debug_catalog():
    prod, path = load_products()
    return {"count": len(prod), "path": str(path)}
