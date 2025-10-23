from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import os
import re
import difflib

from backend.services.product_loader import load_products
from backend.services.search_service import search_candidates, singularize_es
from backend.services.openai_client import chat as llm_chat

router = APIRouter(prefix="/chat", tags=["chat"])

# --- Catálogo / Portafolio (no altera el resto del flujo) ---
CATALOG_URL = os.getenv("ECOLITE_CATALOG_URL", "https://ecolite.com.co/")
# Usamos texto normalizado (sin tildes/ñ)
CATALOG_KEYWORDS = {
    "catalogo", "catalogos",
    "portafolio", "portafolios",
    "brochure", "folleto", "catalogue"
}

QUOTE_WHATSAPP_URL = os.getenv(
    "ECOLITE_QUOTE_WHATSAPP_URL",
    "https://wa.me/573168759639?text=Hola%20quiero%20cotizar" 
)

COTIZAR_KEYWORDS = {
    # Raíces y verbos
    "cotiz", "cotiza", "cotizo", "cotizas", "cotizan", "cotizame", "coticen", "cotizador",
    # Presupuesto
    "presupuesto", "presupuestar", "presupuesta", "presupuesten",
    "quiero un presupuesto", "necesito presupuesto", "hacer un presupuesto", "presupuesto formal",
    # Frases típicas de solicitud
    "quiero cotizar", "puedes cotizar", "me puedes cotizar", "me cotizas", "me cotiza", "me cotizan",
    "solicitar cotizacion", "solicitud de cotizacion", "hacer una cotizacion", "enviar cotizacion",
    "enviame una cotizacion", "mandame una cotizacion", "comparteme una cotizacion", "coticen por favor",
    # Lista / unitario / cuánto
    "lista de precios", "precio unitario", "cuanto cuesta", "cuanto vale", "cuanto sale",
    "me regalas precio", "me das precio", "me pasas precio",
    # Documentos comerciales
    "proforma", "factura proforma", "oferta economica", "propuesta economica", "propuesta comercial",
    # Inglés / RFQ
    "quote", "quotation", "request for quote", "rfq"
}


# ===== Modelos =====
class ChatIn(BaseModel):
    session_id: str
    message: str
    page: int = 0

class ChatOut(BaseModel):
    content: str
    products: List[Dict[str, Any]]
    page: int
    last_query: str
    has_more: bool = False

# ===== Constantes / patrones =====
PAGE_SIZE = 5
_MORE_RE = re.compile(r"\b(m[aá]s|siguientes?|ver\s+m[aá]s|otra(?:s)?)\b", re.I)
_CODE_RE = re.compile(r"[A-Z0-9-]{3,}")

FOLLOWUP_RE = re.compile(r"^\s*(si|sí|ok|vale|normal|blanca[s]?|calida|cálida|fria|fría|neutra)\s*$", re.I)
ABUSE_RE = re.compile(r"\b(idiota|imb[eé]cil|est[uú]pid[oa]|tont[oa])\b", re.I)

# --- Coincidencia "suave" (para filtros por tokens de frase/categoría) ---
_SOFT_MIN_LEN = 4
_SOFT_RATIO   = 0.80
_SOFT_OVERLAP = 0.80

# --- Detección de preguntas/dudas (FAQ) ---
QUESTION_RE = re.compile(
    r"[\?]|"
    r"\b(que|qué|cual|cu[aá]l|como|c[oó]mo|cuando|cu[aá]ndo|donde|d[oó]nde|por\s+qu[eé]|por\s+que|"
    r"es\s+mejor|mejor\s+para|diferencia|sirve|funciona|compatible|se\s+puede|conviene|recomienda|"
    r"precio|garant[ií]a|flujo|voltaje|cri|apertura|óptica|vida\s+[úu]til|duraci[oó]n|vs|versus)\b",
    re.I
)

def _is_question(msg: str) -> bool:
    m = (msg or "").strip()
    if not m:
        return False
    if "?" in m or m.startswith("¿") or m.endswith("?"):
        return True
    return bool(QUESTION_RE.search(m))

# ===== Estado por sesión =====
_SESS: Dict[str, Dict[str, Any]] = {}
def _st(sid: str) -> Dict[str, Any]:
    if sid not in _SESS:
        _SESS[sid] = {
            "last_query": "",
            "server_page": 0,
            "had_evidence": False,
            "topic_tokens": [],
            "seen_by_query": {},
        }
    _SESS[sid].setdefault("seen_by_query", {})
    return _SESS[sid]

# ===== Utils texto =====
def _norm(s: str) -> str:
    import unicodedata
    s = (s or "").strip()
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _product_key(p: Dict[str, Any]) -> str:
    return (
        str(p.get("sku") or p.get("code") or p.get("id") or p.get("link") or p.get("url")
            or _norm(p.get("name", "")))
    )

def _parts(text: str) -> List[str]:
    return [_norm(t) for t in (text or "").replace("/", " ").split() if t]

def _ngrams(tokens: List[str], n: int) -> List[str]:
    return [" ".join(tokens[i:i+n]) for i in range(len(tokens)-n+1)]

def _product_blob(p: Dict[str, Any]) -> str:
    name = str(p.get("name") or "")
    category = str(p.get("category") or "")
    tags = " ".join(map(str, p.get("tags", [])))
    desc = str(p.get("description") or "")
    return _norm(" ".join([name, category, tags, desc]))

# ===== Vocabularios data-driven (sin señales técnicas) =====
def _cat_tag_vocab(products: List[Dict[str, Any]]) -> set:
    vocab = set()
    for p in products:
        parts_cat = []
        c = p.get("category")
        if isinstance(c, str):
            parts_cat.extend(_parts(c))
        elif isinstance(c, list):
            for s in c:
                parts_cat.extend(_parts(str(s)))
        for part in parts_cat:
            if len(part) >= 3:
                vocab.add(part)
            sg = singularize_es(part)
            if sg and len(sg) >= 3:
                vocab.add(sg)

        for t in (p.get("tags") or []):
            for part in _parts(str(t)):
                if len(part) >= 3:
                    vocab.add(part)
                sg = singularize_es(part)
                if sg and len(sg) >= 3:
                    vocab.add(sg)
    return vocab

def _phrase_vocab(products: List[Dict[str, Any]]) -> set:
    vocab = set()
    for p in products:
        toks = _product_blob(p).split()
        for w in toks:
            if len(w) >= 3:
                vocab.add(w)
        for bg in _ngrams(toks, 2):
            if len(bg.replace(" ", "")) >= 6:
                vocab.add(bg)
    return vocab

# ===== Tokens de producto + match "suave" =====
def _product_tokens_set(p: Dict[str, Any]) -> set:
    return set(_product_blob(p).split())

def _soft_overlap(a: str, b: str) -> float:
    la, lb = len(a), len(b)
    L = max(la, lb)
    S = min(la, lb)
    return (S / L) if (a in b or b in a) else 0.0

def _soft_similar(a: str, b: str) -> float:
    return difflib.SequenceMatcher(None, a, b).ratio()

def _soft_token_match(qtok: str, prod_tokens: set) -> bool:
    qtok = qtok.strip()
    if not qtok:
        return False
    for tk in prod_tokens:
        if qtok == tk:
            return True
        if len(qtok) >= _SOFT_MIN_LEN and len(tk) >= _SOFT_MIN_LEN:
            if _soft_similar(qtok, tk) >= _SOFT_RATIO:
                return True
            if _soft_overlap(qtok, tk) >= _SOFT_OVERLAP:
                return True
    return False

# ===== Índice de códigos (se mantiene) =====
def _extract_codes(p: Dict[str, Any]) -> List[str]:
    vals = []
    for f in ("code", "sku", "id"):
        v = p.get(f)
        if v:
            vals.append(str(v).upper().strip())
    return vals

def _base(c: str) -> str:
    c = (c or "").upper()
    return c.split("-")[0] if "-" in c else c

def _build_code_index(products: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    idx: Dict[str, List[Dict[str, Any]]] = {}
    for p in products:
        for c in _extract_codes(p):
            for k in {c, _base(c), c.replace("-", ""), _base(c).replace("-", "")}:
                if k:
                    idx.setdefault(k, []).append(p)
    return idx

def _find_code_hit(message: str, idx: Dict[str, List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
    toks = _parts((message or "").upper())
    raw = re.findall(r"[A-Z0-9-]{3,}", " ".join(toks))
    keys: set = set()
    for t in raw:
        keys |= {t, t.replace("-", ""), _base(t), _base(t).replace("-", "")}
    for k in sorted(keys, key=len, reverse=True):
        if k in idx:
            return idx[k]
    return None

# ===== Señales (solo categorías y frases; SIN watts/IP/K/lm/sockets) =====
def _cat_tokens(q: str, cat_vocab: set) -> List[str]:
    toks = _parts(q)
    out: List[str] = []
    seen = set()
    for t in toks:
        for cand in (t, singularize_es(t)):
            if cand in cat_vocab and cand not in seen:
                out.append(cand)
                seen.add(cand)
    return out

def _phrase_tokens(q: str, phrase_vocab: set) -> List[str]:
    toks = _parts(q)

    uni_hits: List[str] = []
    seen = set()
    for t in toks:
        for cand in {t, singularize_es(t)}:
            if cand in phrase_vocab and cand not in seen:
                seen.add(cand)
                uni_hits.append(cand)

    base_sg = [singularize_es(t) for t in toks]
    bi_candidates = _ngrams(base_sg, 2) + _ngrams(toks, 2)

    bi_hits: List[str] = []
    for bg in bi_candidates:
        if bg in phrase_vocab and bg not in seen:
            seen.add(bg)
            bi_hits.append(bg)

    return bi_hits + uni_hits

# ===== Empaque al frontend =====
def _pick_image(p: Dict[str, Any]) -> Optional[str]:
    return (
        p.get("image") or p.get("img_url") or p.get("image_url") or p.get("img")
        or p.get("thumbnail") or p.get("thumb")
    )

def _pick_url(p: Dict[str, Any]) -> Optional[str]:
    return p.get("url") or p.get("link") or p.get("href")

def _pick_price(p: Dict[str, Any]) -> Any:
    return p.get("price") or p.get("precio") or p.get("valor")

def _pack_products(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for p in items:
        out.append({
            "id": p.get("sku") or p.get("id") or p.get("code"),
            "title": p.get("name"),
            "price": _pick_price(p),
            "image": _pick_image(p),
            "url": _pick_url(p),
            "category": p.get("category"),
            "tags": p.get("tags", []),
        })
    return out

def _filtered_page(
    products: List[Dict[str, Any]],
    query: str,
    page: int,
    filter_tokens: List[str],
    exclude_keys: Optional[set] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    need = (page + 1) * PAGE_SIZE + 400
    pool = search_candidates(products, query, limit=need)

    filtered = pool
    toks = [t for t in (filter_tokens or []) if t]
    if toks:
        def _hit(p: Dict[str, Any]) -> bool:
            ptoks = _product_tokens_set(p)
            return any(_soft_token_match(t, ptoks) for t in toks)

        tmp = [p for p in pool if _hit(p)]
        if tmp:
            filtered = tmp

    unique_items: List[Dict[str, Any]] = []
    seen_local = set()
    exclude = exclude_keys or set()
    for p in filtered:
        k = _product_key(p)
        if k in seen_local or k in exclude:
            continue
        seen_local.add(k)
        unique_items.append(p)

    if exclude:
        start = 0
    else:
        start = max(0, page) * PAGE_SIZE

    end = start + PAGE_SIZE
    page_items = unique_items[start:end]

    has_more = len(unique_items) > end if not exclude else len(unique_items) > PAGE_SIZE
    return page_items, has_more

# ===== Conversación / prompts (sin sugerir W/IP/K) =====
def _build_vocab_dynamic(products: List[Dict[str, Any]]) -> set:
    vocab = set()
    for p in products:
        for t in _product_blob(p).split():
            if len(t) >= 3:
                vocab.add(t)
    return vocab

def _classify_kind(msg: str, vocab: set, cats: List[str], phr: List[str]) -> str:
    m = (msg or "").strip()
    toks = _parts(m)
    if not toks:
        return "smalltalk"

    hits = 0
    for t in toks:
        for cand in (t, singularize_es(t)):
            if cand in vocab:
                hits += 1
                break

    coverage = hits / max(1, len(toks))
    if cats or phr or coverage >= 0.25:
        return "inscope"

    if len(m) <= 16 or len(toks) <= 3:
        return "smalltalk"
    return "offtopic"

def _catalog_context(products: List[Dict[str, Any]], vocab: set, top_k: int = 10) -> str:
    cat_counter = Counter()
    for p in products:
        cats = []
        c = p.get("category")
        if isinstance(c, str):
            cats.append(_norm(c))
        elif isinstance(c, list):
            cats.extend([_norm(s) for s in c if isinstance(s, str)])
        for t in p.get("tags", []) or []:
            if isinstance(t, str):
                cats.append(_norm(t))
        for x in cats:
            if x:
                cat_counter[x] += 1
    top_cats = [k for k, _ in cat_counter.most_common(top_k)]
    parts = []
    if top_cats:
        parts.append("CATEGORIAS_RELEVANTES=" + ", ".join(top_cats))
    # Ya no incluimos listado de tokens técnicos (W/IP/K/lm).
    return "\n".join(parts)

def _build_system_prompt(kind: str, ctx: str) -> str:
    style = os.getenv("ECOLITE_STYLE_GUIDE", "Asesor de iluminación Ecolite (CO), respuestas breves y claras.")
    tone = os.getenv("ECOLITE_TONE", "cercano y profesional")
    base = f"{style} Tono: {tone}. No inventes especificaciones. Si faltan datos, pide 1 dato concreto."
    rules = []
    if kind == "faq":
        rules.append("Modo FAQ: responde a la duda en 2–4 líneas, sin listar productos ni enlaces.")
        rules.append("Termina con 1 pregunta corta para avanzar (ej. uso, espacio, presupuesto).")
    elif kind == "offtopic":
        rules.append("Tema fuera de iluminación: redirige en 1 frase y termina con 1 pregunta para retomar iluminación.")
    elif kind == "inscope":
        rules.append("En tema de productos: da una micro-orientación (1 frase) y ofrece 1 pregunta de seguimiento (espacio de uso o presupuesto).")
    else:
        rules.append("Charla breve (1 frase) y conduce a la asesoría de iluminación con 1 pregunta simple.")
    return "\n".join([base, ctx, "REGLAS:"] + [f"- {r}" for r in rules])

def _fallback_dynamic(msg: str, products: List[Dict[str, Any]], vocab: set) -> str:
    # Sin mencionar W/IP/K. Mantén guía mínima.
    return "Para ayudarte mejor, cuéntame el espacio a iluminar y si tienes un presupuesto aproximado."

# ===== Endpoint =====
@router.post("/", response_model=ChatOut)
def chat(in_: ChatIn) -> ChatOut:
    try:
        msg_raw = (in_.message or "").strip()
        if not msg_raw:
            raise HTTPException(status_code=400, detail="message is required")

        msg_norm = _norm(msg_raw)
        if any(k in msg_norm for k in CATALOG_KEYWORDS):
            text = f"Puedes ver el catálogo y portafolio aquí: {CATALOG_URL}"
            return ChatOut(content=text, products=[], page=0, last_query="", has_more=False)
        
        msg_norm = _norm(msg_raw)
        if any(k in msg_norm for k in COTIZAR_KEYWORDS):
            text = f"Para cotizaciones y presupuestos, escríbenos por [[a|WhatsApp|{QUOTE_WHATSAPP_URL}]]"
            return ChatOut(content=text, products=[], page=0, last_query="", has_more=False)


        st = _st(in_.session_id)

        # Cargar catálogo y vocab/datos dinámicos
        catalog, _path = load_products()
        products = list(catalog.values())
        cat_vocab = _cat_tag_vocab(products)
        phrase_vocab = _phrase_vocab(products)
        vocab = _build_vocab_dynamic(products)
        ctx = _catalog_context(products, vocab)

        # Señales (SIN técnicos)
        cats = _cat_tokens(msg_raw, cat_vocab)
        phr = _phrase_tokens(msg_raw, phrase_vocab)
        kind = _classify_kind(msg_raw, vocab, cats, phr)

        # “Ver más”
        client_page = max(0, int(getattr(in_, "page", 0) or 0))
        is_more = bool(_MORE_RE.search(msg_raw))
        abused = bool(ABUSE_RE.search(msg_raw))

        # FAQ: solo texto, sin productos
        if not is_more and _is_question(msg_raw) and not abused:
            sys_prompt = _build_system_prompt("faq", ctx)
            ai = llm_chat(sys_prompt, msg_raw) or _fallback_dynamic(msg_raw, products, vocab)
            return ChatOut(content=ai, products=[], page=0, last_query="", has_more=False)

        # Smalltalk / offtopic sin “más”
        if not is_more and not abused and kind in {"smalltalk", "offtopic"}:
            sys_prompt = _build_system_prompt(kind, ctx)
            ai = llm_chat(sys_prompt, msg_raw) or _fallback_dynamic(msg_raw, products, vocab)
            return ChatOut(content=ai, products=[], page=0, last_query="", has_more=False)

        # Gestionar página/consulta (búsqueda normal)
        if is_more and st["last_query"]:
            q = st["last_query"]
            st["server_page"] = max(st.get("server_page", 0) + 1, client_page)
            page = st["server_page"]
        else:
            q = msg_raw
            if FOLLOWUP_RE.match(q) and st["topic_tokens"]:
                q = " ".join(st["topic_tokens"] + [q])
            st["last_query"] = q
            st["server_page"] = client_page
            page = client_page

        # Códigos/SKU (se mantiene)
        code_idx = _build_code_index(products)
        code_hit = _find_code_hit(q, code_idx)
        if code_hit:
            item = sorted(code_hit, key=lambda p: len("".join(_extract_codes(p))), reverse=True)[0]
            st["had_evidence"] = True
            st["topic_tokens"] = list(set(cats + phr))
            sys_prompt = _build_system_prompt("inscope", ctx)
            ai = llm_chat(sys_prompt, msg_raw) or _fallback_dynamic(msg_raw, products, vocab)
            return ChatOut(
                content=ai,
                products=_pack_products([item]),
                page=0,
                last_query=q,
                has_more=False
            )

        # Filtros derivados solo de categorías/frases (SIN técnicos)
        filter_tokens = list(dict.fromkeys(phr + cats))

        # Evitar repetidos por consulta
        st.setdefault("seen_by_query", {})
        q_key = _norm(q)
        if page == 0:
            st["seen_by_query"][q_key] = set()
        seen = st["seen_by_query"].setdefault(q_key, set())

        # Página de resultados
        page_items, has_more = _filtered_page(
            products=products,
            query=q,
            page=page,
            filter_tokens=filter_tokens,
            exclude_keys=seen,
        )
        for p in page_items:
            seen.add(_product_key(p))

        if page_items:
            st["had_evidence"] = True
            st["topic_tokens"] = filter_tokens or st.get("topic_tokens", [])
            sys_prompt = _build_system_prompt("inscope", ctx)
            ai = llm_chat(sys_prompt, msg_raw) or _fallback_dynamic(msg_raw, products, vocab)
            return ChatOut(
                content=ai,
                products=_pack_products(page_items),
                page=page,
                last_query=q,
                has_more=has_more
            )

        # Sin resultados
        if st.get("had_evidence") and (is_more or page > 0):
            sys_prompt = _build_system_prompt("inscope", ctx)
            msg = llm_chat(sys_prompt, f"{msg_raw}\nNo hubo más resultados para la consulta anterior.") or _fallback_dynamic(msg_raw, products, vocab)
            return ChatOut(content=msg, products=[], page=page, last_query=q, has_more=False)

        # Último recurso
        sys_prompt = _build_system_prompt(kind, ctx)
        ai = llm_chat(sys_prompt, msg_raw) or _fallback_dynamic(msg_raw, products, vocab)
        return ChatOut(content=ai, products=[], page=0, last_query=q, has_more=False)

    except HTTPException:
        raise
    except Exception:
        # Nunca 500 al cliente
        return ChatOut(
            content="Tuvimos un inconveniente técnico. Intenta de nuevo.",
            products=[],
            page=0,
            last_query=in_.message or "",
            has_more=False
        )
