from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

# Routers (están en backend/routers/)
from backend.routers import faq as faq_router
from backend.routers import chat as chat_router

from backend.routers import leads as leads_router

# Servicios (producto)
from backend.services.product_loader import load_products


app = FastAPI(title="Ecolite Assistant", version="3.3")

app.include_router(leads_router.router)  
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Montar routers
app.include_router(faq_router.router)
app.include_router(chat_router.router)
if leads_router:
    app.include_router(leads_router.router)
from backend.routers import history as history_router

app.include_router(history_router.router)

# Archivos estáticos (frontend)
try:
    app.mount("/static", StaticFiles(directory="frontend"), name="static")
except Exception:
    pass

@app.get("/")
def index():
    try:
        return FileResponse("frontend/chatbox.html")
    except Exception:
        return {"ok": True, "message": "Ecolite API"}

@app.get("/healthz")
def healthz():
    return {"ok": True}

@app.get("/__debug/catalog")
def debug_catalog():
    prod, path = load_products()
    return {"count": len(prod), "path": str(path)}
