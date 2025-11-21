from __future__ import annotations
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Any, Optional, Tuple
from collections import Counter
import os
import re
import difflib
from urllib.parse import quote_plus

# Servicios con fallback (sin auto-importarse a sí mismo)
try:
    from backend.services.product_loader import load_products
    from backend.services.search_service import search_candidates, singularize_es
    from backend.services.openai_client import chat as llm_chat
except Exception:
    from product_loader import load_products
    from search_service import search_candidates, singularize_es
    from openai_client import chat as llm_chat

router = APIRouter(prefix="/chat", tags=["chat"])


CATALOG_URL = os.getenv("ECOLITE_CATALOG_URL", "https://ecolite.com.co/")
CATALOG_KEYWORDS = {
    "catalogo", "catalogos",
    "portafolio", "portafolios",
    "brochure", "folleto", "catalogue"
}

QUOTE_WHATSAPP_URL = os.getenv(
    "ECOLITE_QUOTE_WHATSAPP_URL",
    "https://wa.me/573168759639"
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

# === Guardas de marca / temática ===
COMPETITOR_KEYWORDS = {
    # agrega/quita según necesites
    "sylvania", "sylvannia", "philips", "osram", "ge lighting",
    "schneider", "siemens", "opple", "xiaomi", "yeelight",
    "panasonic", "abb", "legrand", "lumenac", "techlight", "luxion", "tecnolite", "roy alpha",
    "nipponflex", "ilumax", "mercury", "vatiu", "safiro", "lumek", "evergreen", "eglo", "lumenex",
    "delta light", "luminex", "luxion", "lirvan", "alutrafic", "inadisa", "celsa", "lumen", "ledvance"
}
def _mentions_competitor(msg_norm: str) -> bool:
    return any(k in msg_norm for k in COMPETITOR_KEYWORDS)

OFFSCOPE_REPLY = (
    "Puedo ayudarte únicamente con iluminación de Ecolite. "
    "Cuéntame el espacio (oficina, piscina, bodega) o el producto Ecolite que buscas."
)

# —— Mensaje fijo para búsquedas de “ventilador” ——
VENTILADOR_NOTE = (
    "Estas luminarias incluyen ventilación integrada 💡🌀\n"
    "Son ideales para sala, alcoba o comedor.\n"
    "Te muestro las opciones disponibles:"
)

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

FOLLOWUP_RE = re.compile(
    r"^\s*(si|sí|ok|vale|normal|blanca[s]?|calida|cálida|fria|fría|neutra"
    r"|muestrame(?:\s+mas)?|muéstrame(?:\s+más)?|muestramel[ao]s?|muéstramel[ao]s?)\s*$",
    re.I
)

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

# === FAQ: import robusto (soporta distintas estructuras del proyecto) ===
try:
    from backend.routers.faq import faq_try_answer
except Exception:
    try:
        from faq import faq_try_answer
    except Exception:
        def faq_try_answer(_msg: str):
            return None

def _is_question(msg: str) -> bool:
    m = (msg or "").strip()
    if not m:
        return False
    if "?" in m or m.startswith("¿") or m.endswith("?"):
        return True
    return bool(QUESTION_RE.search(m))

# ⬇️ NUEVO: Intenciones explícitas (mostrar vs sugerir) y guard de “muéstrame …”
SHOW_RE     = re.compile(r'\b(muestrame|quiero|muéstrame|muestra|ver|ens[eé]ñame|listar|ensename)\b', re.I)
SUGGEST_RE = re.compile(
    r'\b(sugiereme|sugi[eé]reme|quiero|recomiendame|recomi[eé]ndame|recomienda(?:s)?|sugerir)\b',
    re.I
)
ASK_PREFIX_RE = re.compile(r'^\s*(muestrame|muéstrame|muestra|ver|ens[eé]ñame)\b', re.I)

# ⬇️ NUEVO: Stopwords que NO deben ser categoría/tag
STOP_TAGS = {
    "para","de","en","con","por","sin","y","o",
    "la","el","los","las","un","una","unos","unas",
    "iluminacion","iluminación","luminaria","luminarias",
    "luz","luces","led","producto","productos"
}

def _looks_like_product_intent(msg: str, vocab: set, cats: list[str], phr: list[str]) -> bool:
    """Devuelve True si el mensaje parece pedir/ comparar productos.
    Señales: tokens de categoría/frases o coincidencias con vocabulario de catálogo."""
    try:
        if cats or phr:
            return True
        return _any_token_in_vocab(msg, vocab)
    except Exception:
        # fallback súper conservador
        return False

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
            "lead_name": "",
        }
    _SESS[sid].setdefault("seen_by_query", {})
    return _SESS[sid]

def _clean_topic(q: str) -> str:
    q = (q or "").strip()
    low = q.lower()
    for p in ("sugiereme", "sugiéreme", "recomiendame", "recomiéndame", "quiero", "necesito", "busco"):
        if low.startswith(p):
            return q[len(p):].strip(" :,-.")
    return q

def _make_quote_text(st: Dict[str, Any]) -> str:
    topic = _clean_topic(st.get("last_query") or "") or "iluminación LED"
    return f"estoy interesado en {topic}"

def _wa_url(base: str, text: str) -> str:
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}text={quote_plus(text)}"

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

    blob = _norm(" ".join([name, category, tags, desc]))
    blob = " ".join(t for t in blob.split() if t not in {"luminaria", "luminarias", "para", "de"})
    return blob

def _any_token_in_vocab(msg: str, vocab: set) -> bool:
    toks = _parts(msg)
    for t in toks:
        sg = singularize_es(t)
        if t in vocab or sg in vocab:
            return True
    return False

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
            if len(part) >= 3 and part not in STOP_TAGS:  # ⬅️ filtra stopwords
                vocab.add(part)
            sg = singularize_es(part)
            if sg and len(sg) >= 3 and sg not in STOP_TAGS:  # ⬅️ filtra stopwords
                vocab.add(sg)

        for t in (p.get("tags") or []):
            for part in _parts(str(t)):
                if len(part) >= 3 and part not in STOP_TAGS:  # ⬅️ filtra stopwords
                    vocab.add(part)
                sg = singularize_es(part)
                if sg and len(sg) >= 3 and sg not in STOP_TAGS:  # ⬅️ filtra stopwords
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
    raw_upper = (message or "").upper()
    # Extrae tokens tipo ABC-123, DC42V, HB3A2, etc. (≥3 chars)
    tokens = re.findall(r"[A-Z0-9-]{3,}", raw_upper)

    keys: set[str] = set()
    for t in tokens:
        t = t.strip("-")
        if not t:
            continue
        keys |= {
            t,
            t.replace("-", ""),
            _base(t),
            _base(t).replace("-", ""),
        }

    for k in sorted(keys, key=len, reverse=True):
        if k in idx:
            return idx[k]
    return None

# ---- Helpers para petición de "un solo código" ----
def _single_code_token(msg: str) -> Optional[str]:
    """
    Devuelve el único token tipo código si el usuario solo mencionó 1 (p.ej. DC42V).
    Acepta letras/números/guiones, >=3, y exige al menos un dígito.
    """
    toks = re.findall(r"[A-Z0-9-]{3,}", (msg or "").upper())
    toks = [t for t in toks if any(ch.isdigit() for ch in t)]
    uniq = list(dict.fromkeys(toks))
    return uniq[0] if len(uniq) == 1 else None

def _pick_code_item(candidates: List[Dict[str, Any]], message_or_code: str) -> Dict[str, Any]:
    """
    Elige el mejor candidato para un código pedido (prefiere match exacto, luego misma raíz).
    """
    target = set(re.findall(r"[A-Z0-9-]{3,}", (message_or_code or "").upper()))
    base_target = {_base(t) for t in target}
    def _score(p):
        codes = {c.upper() for c in _extract_codes(p)}
        score = 0
        if codes & target:                       # exacto
            score += 100
        if {_base(c) for c in codes} & base_target:  # misma raíz
            score += 10
        score += sum(len(c) for c in codes)      # desempate
        return score
    return max(candidates, key=_score)

def _code_substring_candidates(needle: str, products: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Busca candidatos cuando el usuario escribe un único token de tipo “código”.
    Soporta equivalencias para DCxxV: DC42V ↔ 42VDC ↔ 42 VDC ↔ DC 42V ↔ 42V.
    Se enfoca en el MISMO valor numérico (evita 12V/24V cuando se pidió 42V).
    """
    up = (needle or "").upper().strip()

    # --- Si es del tipo DCxxV, generamos variantes y un matcher por VOLTAJE exacto ---
    m = re.match(r"^DC(\d{2,3})V$", up)
    target_volt = None
    patterns = set()

    if m:
        target_volt = m.group(1)  # e.g., "42"
        # Variantes más comunes del texto libre
        patterns |= {
            f"{target_volt}V",
            f"{target_volt} V",
            f"{target_volt}VDC",
            f"{target_volt} VDC",
            f"DC {target_volt}V",
            f"DC{target_volt}V",
            f"{target_volt}V DC",
        }
        # Algunas formas con guiones o rangos (ej. 36–42V, 36-42 V)
        patterns |= {
            f"{target_volt} VDC",
            f"{target_volt}V-",
            f"{target_volt}V–",
            f"-{target_volt}V",
            f"–{target_volt}V",
            f"{target_volt}/",
            f"/{target_volt}V",
        }

    def _text_blob(p: Dict[str, Any]) -> str:
        name = str(p.get("name") or "")
        desc = str(p.get("description") or "")
        cats = p.get("category")
        if isinstance(cats, list):
            cats = " ".join(map(str, cats))
        cats = str(cats or "")
        tags = " ".join(map(str, p.get("tags", [])))
        return f"{name} {cats} {tags} {desc}".upper()

    def _scores_for_dc(p: Dict[str, Any]) -> int:
        """Prioriza drivers/fuentes que contengan el voltaje exacto."""
        blob = _text_blob(p)
        score = 0
        if target_volt:
            # Puntaje alto si aparece el número con 'V' pegado o separado
            if any(pat in blob for pat in patterns):
                score += 50
            # Bonus si menciona driver/fuente/PSU
            if re.search(r"\b(DRIVER|FUENTE|POWER|PSU)\b", blob):
                score += 25
        # Pequeño bonus por coincidencia directa del token completo
        if up in blob:
            score += 10
        return score

    out = []

    # 1) Si el código real está en code/sku/id (ideal)
    for p in products:
        if not isinstance(p, dict):
            continue
        if any(up in c for c in _extract_codes(p)):
            out.append(p)

    # 2) Texto libre: aplicar matcher especial de VOLTAJE exacto si aplica
    if not out:
        for p in products:
            if not isinstance(p, dict):
                continue
            blob = _text_blob(p)
            if target_volt:
                if any(pat in blob for pat in patterns):
                    out.append(p)
            else:
                # Caso general: usa el token literal
                if up and up in blob:
                    out.append(p)

    # Deduplicar conservando orden
    dedup, seen = [], set()
    for p in out:
        k = _product_key(p)
        if k not in seen:
            dedup.append(p); seen.add(k)

    # Si hay varios, aplica un scoring para preferir “driver/fuente” con el voltaje exacto
    if dedup and target_volt:
        dedup = sorted(dedup, key=_scores_for_dc, reverse=True)

    return dedup

def _cat_tokens(q: str, cat_vocab: set) -> List[str]:
    toks = _parts(q)
    out: List[str] = []
    seen = set()
    for t in toks:
        for cand in (t, singularize_es(t)):
            if cand in STOP_TAGS:  # ⬅️ no contaminar categorías con stopwords
                continue
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

def _tagcat_tokens(p: Dict[str, Any]) -> set:
    """Tokens SOLO de category/tags, para filtros 'duros'."""
    toks = set()
    c = p.get("category")
    raw = []
    if isinstance(c, str):
        raw.extend(_parts(c))
    elif isinstance(c, list):
        for s in c:
            raw.extend(_parts(str(s)))
    for t in (p.get("tags") or []):
        raw.extend(_parts(str(t)))

    # ⬇️ filtra stopwords
    raw = [x for x in raw if x not in STOP_TAGS]

    toks.update(raw)
    toks |= {singularize_es(t) for t in list(toks) if singularize_es(t) not in STOP_TAGS}
    return toks

def _filtered_page(
    products: List[Dict[str, Any]],
    query: str,
    page: int,
    filter_tokens: List[str],
    hard_tags: List[str] = None,
    exclude_keys: Optional[set] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    """
    Busca candidatos, aplica filtros DUROS (category/tags exactos) y luego filtros SUAVES (nombre/descr),
    deduplica, pagina y devuelve (items_pagina, has_more).
    """
    # 1) Candidatos del motor de búsqueda
    need = (page + 1) * PAGE_SIZE + 400
    pool = search_candidates(products, query, limit=need)

    filtered = pool

    # 2) Filtros DUROS: todos los 'hard_tags' deben estar en category/tags del producto
    htags = [t for t in (hard_tags or []) if t]
    if htags:
        def _must_have_tags(p: Dict[str, Any]) -> bool:
            tset = _tagcat_tokens(p)
            return all((t in tset or singularize_es(t) in tset) for t in htags)
        strict = [p for p in pool if isinstance(p, dict) and _must_have_tags(p)]
        # Si hay matches estrictos, usar sólo esos; si no hay, dejamos lista vacía (nada irrelevante).
        filtered = strict

    # 3) Filtros SUAVES: tokens de frase sobre nombre/descr (sólo si aún hay candidatos)
    toks = [t for t in (filter_tokens or []) if t]
    if filtered and toks:
        def _hit(p: Dict[str, Any]) -> bool:
            ptoks = _product_tokens_set(p)
            return any(_soft_token_match(t, ptoks) for t in toks)
        tmp = [p for p in filtered if isinstance(p, dict) and _hit(p)]
        if tmp:
            filtered = tmp

    # 4) Dedup + exclusiones
    unique_items: List[Dict[str, Any]] = []
    seen_local = set()
    exclude = exclude_keys or set()
    for p in (filtered or []):
        if not isinstance(p, dict):
            continue
        k = _product_key(p)
        if k in seen_local or k in exclude:
            continue
        seen_local.add(k)
        unique_items.append(p)

    # 5) Paginación
    start = 0 if exclude else max(0, page) * PAGE_SIZE
    end = start + PAGE_SIZE
    page_items = unique_items[start:end]

    # 6) ¿Hay más?
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

def _llm_intent(msg: str) -> str:
    """
    Clasifica la intención sin reglas fijas:
    - PRODUCTO: comparación/elección/recomendación de luminarias o specs
    - FAQ: políticas de empresa (garantía, envíos, horarios, dirección, contacto)
    - OTRO: lo demás
    Responde SOLO una palabra.
    """
    sys = (
        "Clasifica la intención del usuario. Responde con UNA SOLA palabra en mayúsculas: "
        "PRODUCTO, FAQ u OTRO. No expliques nada."
    )
    ans = (llm_chat(sys, msg) or "OTRO").strip().upper()
    if "PRODUCTO" in ans:
        return "PRODUCTO"
    if "FAQ" in ans:
        return "FAQ"
    return "OTRO"

def _llm_product_mode(msg: str) -> str:
    """
    Decide si el usuario quiere VER una lista (LISTAR) o solo ASESORÍA breve (ASESORAR).
    Responde con LISTAR o ASESORAR.
    """
    sys = ("Decide si el usuario quiere VER una lista de productos o solo recibir ASESORÍA breve. "
           "Responde con LISTAR o ASESORAR y nada más.")
    ans = (llm_chat(sys, msg) or "ASESORAR").strip().upper()
    return "LISTAR" if "LISTAR" in ans else "ASESORAR"

def _product_mode_override(msg: str) -> Optional[str]:
    # Si el usuario dice "muéstrame", "ver", "sugiereme", "recomiéndame" → quiere ver productos
    if SHOW_RE.search(msg) or SUGGEST_RE.search(msg):
        return "LISTAR"
    return None



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
    return "\n".join(parts)

def _build_system_prompt(kind: str, ctx: str) -> str:
    style = os.getenv("ECOLITE_STYLE_GUIDE", "Asesor de iluminación Ecolite (CO), respuestas breves y claras.")
    tone = os.getenv("ECOLITE_TONE", "cercano y profesional")
    base = f"{style} Tono: {tone}. No inventes especificaciones. Evita hacer preguntas; responde enunciativamente. " \
           f"Nunca hables de otras marcas o empresas y no respondas temas fuera de iluminación."
    rules = []
    if kind == "faq":
        rules.append("Modo FAQ: responde la duda en 2–4 líneas, sin listar productos ni enlaces, sin preguntas.")
    elif kind == "offtopic":
        rules.append("Tema fuera de iluminación: redirige en 1 frase, sin preguntas.")
    elif kind == "inscope":
        rules.append("En tema de productos: da una micro-orientación breve, sin preguntas.")
    else:
        rules.append("Charla breve y conduce a la asesoría sin preguntas.")
    # ⬇️ NUEVO: evita respuestas del tipo “no proporcionamos información…” para espacios del catálogo
    rules.append("Nunca digas que 'no proporcionas información' si el término pertenece a espacios del catálogo (piscina, bodega, oficina, etc.).")
    return "\n".join([base, ctx, "REGLAS:"] + [f"- {r}" for r in rules])

def _fallback_dynamic(msg: str, products: List[Dict[str, Any]], vocab: set) -> str:
    return "Para ayudarte mejor, cuéntame el espacio a iluminar y si tienes un presupuesto aproximado."

def _norm_code(s: str) -> str:
    """Normaliza códigos a MAYÚSCULAS y sin separadores (ECO-PL12WA -> ECOPL12WA)."""
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())

def _single_code_token_raw(msg: str) -> Optional[Tuple[str, str]]:
    toks = re.findall(r"[A-Z0-9-]{3,}", (msg or "").upper())

    # ❌ EXCLUIR vatios tipo “35W”, “50W”, “20W”
    watt_like = set()
    for t in toks:
        if re.fullmatch(r"\d{2,3}W", t):  # 35W / 100W / 50W
            watt_like.add(t)

    toks = [t for t in toks if t not in watt_like]

    # Reglas normales
    toks = [t for t in toks if any(ch.isdigit() for ch in t)]
    uniq = list(dict.fromkeys(toks))

    return (uniq[0], _norm_code(uniq[0])) if len(uniq) == 1 else None


def _find_exact_code_product(code_norm: str, products: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """
    Busca match EXACTO por código normalizado contra campos típicos de código.
    No cae a substrings ni familias. Devuelve 1 producto o None.
    """
    CODE_FIELDS = ("code", "sku", "id", "model", "slug")  # añade más si tu catálogo los usa
    for p in products:
        if not isinstance(p, dict):
            continue
        for f in CODE_FIELDS:
            v = p.get(f)
            if v and _norm_code(v) == code_norm:
                return p
    return None

# ===== Endpoint =====
@router.post("/", response_model=ChatOut)
def chat(in_: ChatIn) -> ChatOut:
    try:
        msg_raw = (in_.message or "").strip()
        if not msg_raw:
            raise HTTPException(status_code=400, detail="message is required")

        msg_norm = _norm(msg_raw)

        faq_text = faq_try_answer(msg_raw)
        if faq_text:
            return ChatOut(
                content=faq_text,
                products=[],
                page=0,
                last_query="",
                has_more=False
            )

        # 🚫 Bloquear menciones a otras marcas / competencia
        if any(k in msg_norm for k in [
            "sylvania", "sylvannia", "philips", "osram", "ge lighting",
            "schneider", "siemens", "opple", "xiaomi", "yeelight",
            "panasonic", "abb", "legrand", "lumenac", "techlight", "luxion",
            "tecnolite", "roy alpha", "nipponflex", "ilumax", "mercury", "vatiu",
            "safiro", "lumek", "evergreen", "eglo", "lumenex", "delta light",
            "luminex", "luxion"
        ]):
            return ChatOut(
                content="En ECOLITE contamos con un portafolio completo y disponibilidad inmediata para cubrir todas las necesidades de tu proyecto. Nuestras luminarias destacan por su calidad, eficiencia y respaldo técnico. 🔧\n"
                        "Estoy aquí para ayudarte a encontrar la mejor opción dentro de nuestra línea.",
                products=[],
                page=0,
                last_query="",
                has_more=False
            )

        st = _st(in_.session_id)

        # Catálogo
        msg_norm = _norm(msg_raw)
        if any(k in msg_norm for k in CATALOG_KEYWORDS):
            text = f"Puedes ver el catálogo y portafolio aquí: {CATALOG_URL}"
            return ChatOut(content=text, products=[], page=0, last_query="", has_more=False)

        # Cotizar (WhatsApp)
        msg_norm = _norm(msg_raw)
        if any(k in msg_norm for k in COTIZAR_KEYWORDS):
            url = QUOTE_WHATSAPP_URL
            return ChatOut(
                content=f"Abrir [[a|WhatsApp|{url}]] para continuar 👌",
                products=[], page=0, last_query=st.get("last_query") or "", has_more=False
            )

        # —— Manejo especial para ventiladores ——
        msg_norm = _norm(msg_raw)
        ventilador_mode = ("ventilador" in msg_norm) or ("ventiladores" in msg_norm)
        if ventilador_mode:
            # añadimos una marca en el mensaje para forzar el copy correcto del texto final
            in_.message = msg_raw + " (VENTILADOR_MODE)"

        # Bloquear menciones a otras marcas/empresas (competencia)
        if _mentions_competitor(msg_norm):
            return ChatOut(content=OFFSCOPE_REPLY, products=[], page=0, last_query="", has_more=False)

        # Cargar catálogo y preparar señales
        catalog, _path = load_products()
        products = list(catalog.values())
        cat_vocab = _cat_tag_vocab(products)
        phrase_vocab = _phrase_vocab(products)
        vocab = _build_vocab_dynamic(products)
        ctx = _catalog_context(products, vocab)

        cats = _cat_tokens(msg_raw, cat_vocab)
        phr  = _phrase_tokens(msg_raw, phrase_vocab)
        kind = _classify_kind(msg_raw, vocab, cats, phr)

        # “Ver más”
        client_page = max(0, int(getattr(in_, "page", 0) or 0))
        is_more = bool(_MORE_RE.search(msg_raw))
        abused  = bool(ABUSE_RE.search(msg_raw))

        # ⬇️ NUEVO: override al modo del LLM cuando el usuario es explícito
        mode = _llm_product_mode(msg_raw)
        ov   = _product_mode_override(msg_raw)
        if ov:
            mode = ov

        # Pregunta de asesoría (sin listado): si es de producto y el usuario NO pidió ver productos
        if (not is_more and not abused
                and _looks_like_product_intent(msg_raw, vocab, cats, phr)
                and mode == "ASESORAR"):
            sys_prompt = _build_system_prompt("inscope", ctx)
            sys_prompt += "\n- No listes productos ni enlaces; responde en 2–4 líneas."
            ai = llm_chat(sys_prompt, msg_raw) or (
                "Para bodegas: usa highbay en techos ≥6–7 m por uniformidad; herméticas lineales (IP65) en 3–5 m o pasillos; "
                "prioriza IP65/66 si hay polvo o humedad."
            )
            if ventilador_mode:
                ai = VENTILADOR_NOTE
            st["last_query"] = msg_raw
            st["server_page"] = 0
            return ChatOut(content=ai, products=[], page=0, last_query=msg_raw, has_more=False)

        # FAQ (solo texto) — solo si la intención es FAQ (data + LLM), no productos
        if not is_more and _is_question(msg_raw) and not abused:
            # Primero: señales de catálogo (datos), sin reglas fijas
            if not _looks_like_product_intent(msg_raw, vocab, cats, phr):
                # Segundo: desempate con LLM (una palabra)
                if _llm_intent(msg_raw) == "FAQ":
                    try:
                        faq_text = faq_try_answer(msg_raw)
                    except Exception:
                        faq_text = None
                    if faq_text:
                        return ChatOut(content=faq_text, products=[], page=0, last_query="", has_more=False)

                    sys_prompt = (
                        "Eres el asistente de Ecolite. Responde en 2–4 líneas una duda general del usuario sin listar productos. "
                        "Sé claro y conciso. Si la pregunta es sobre políticas (garantía, envíos, contacto), da una guía corta, sin preguntas."
                    )
                    ai = llm_chat(sys_prompt, msg_raw) or "Estoy disponible para ayudarte con temas de empresa, garantía o envíos."
                    if ventilador_mode:
                        ai = VENTILADOR_NOTE
                    return ChatOut(content=ai, products=[], page=0, last_query="", has_more=False)
        # Si no entró al return de arriba, continúa el flujo normal (asesoría/browsing de productos)

        # Smalltalk / offtopic sin “más”
        if not is_more and not abused and kind in {"smalltalk", "offtopic"}:
            if kind == "offtopic":
                return ChatOut(content=OFFSCOPE_REPLY, products=[], page=0, last_query="", has_more=False)
            sys_prompt = _build_system_prompt(kind, ctx)
            ai = llm_chat(sys_prompt, msg_raw) or _fallback_dynamic(msg_raw, products, vocab)
            if ventilador_mode:
                ai = VENTILADOR_NOTE
            return ChatOut(content=ai, products=[], page=0, last_query="", has_more=False)

        # Gestión de página / query
        if is_more and st["last_query"]:
            q = st["last_query"]
            st["server_page"] = max(st.get("server_page", 0) + 1, client_page)
            page = st["server_page"]
        else:
            q = msg_raw
            if FOLLOWUP_RE.match(q) and st["topic_tokens"]:
                q = " ".join(st["topic_tokens"] + [q])
            st["last_query"]  = q
            st["server_page"] = client_page
            page = client_page

        # ⬇️ NUEVO: Guard para “muéstrame <etiqueta>” inexistente → no listar irrelevantes
        if ASK_PREFIX_RE.search(msg_raw) and not is_more:
            tokens = [t for t in _parts(msg_raw) if t not in {'muestrame','muéstrame','muestra','ver','enseñame','enséñame'}]
            generic = {'iluminacion','iluminación','led','luz','luminaria','luminarias','para','de','en'}
            terms = [t for t in tokens if t not in generic and not any(ch.isdigit() for ch in t)]
            def in_cat(t: str) -> bool:
                return (t in cat_vocab) or (singularize_es(t) in cat_vocab)
            if terms and not any(in_cat(t) for t in terms):
                term = terms[0]
                return ChatOut(
                    content=f"No encontré productos con la etiqueta “{term}”.",
                    products=[],
                    page=0,
                    last_query=q,
                    has_more=False
                )

        # Coincidencia por código/SKU
        code_idx  = _build_code_index(products)
        code_hit  = _find_code_hit(q, code_idx)
        if code_hit:
            item = _pick_code_item(code_hit, q)  # elegir mejor candidato (prefiere exacto)
            st["had_evidence"]  = True
            st["topic_tokens"]  = list(set(cats + phr))
            # Intro determinista (evita respuestas raras del LLM)
            ai = "Te muestro la referencia más cercana al código indicado."
            if ventilador_mode:
                ai = VENTILADOR_NOTE
            return ChatOut(
                content=ai,
                products=_pack_products([item]),
                page=0,
                last_query=q,
                has_more=False
            )

        # === BÚSQUEDA POR CÓDIGO EXACTO (modo estricto) ===
        # Si el usuario dio UN SOLO token de código, buscamos match EXACTO.
        _sc = _single_code_token_raw(q)
        if _sc:
            orig_code, norm_code = _sc
            item = _find_exact_code_product(norm_code, products)
            if item:
                # Respuesta corta + 1 producto (el exacto)
                st["had_evidence"]  = True
                st["topic_tokens"]  = list(set(cats + phr))
                ai = "Te muestro la referencia con el código exacto solicitado."
                if ventilador_mode:
                    ai = VENTILADOR_NOTE
                return ChatOut(
                    content=ai,
                    products=_pack_products([item]),
                    page=0,
                    last_query=q,
                    has_more=False
                )
            else:
                # Si NO existe, no caemos al buscador general: avisamos que NO se encontró exacto.
                return ChatOut(
                    content=f"No encontré el código exacto: {orig_code}.",
                    products=[],
                    page=0,
                    last_query=q,
                    has_more=False
                )
        # === FIN modo estricto de código ===


        # Evidencia mínima
        if not _any_token_in_vocab(q, vocab):
            st["had_evidence"] = False
            st["topic_tokens"] = []
            st["last_query"]   = ""
            respuesta = (
                "No encontré productos que coincidan con lo que buscas. "
                "Cuéntame qué espacio quieres iluminar o qué tipo de producto necesitas 😊"
            )
            return ChatOut(content=respuesta, products=[], page=0, last_query="", has_more=False)

        # Filtros derivados de categorías/frases
        filter_tokens = phr

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
            hard_tags=cats,            # << tokens de categoría/tag (duros)
            exclude_keys=seen,
        )
        for p in page_items:
            seen.add(_product_key(p))

        if page_items:
            st["had_evidence"] = True
            st["topic_tokens"] = filter_tokens or st.get("topic_tokens", [])
            # Intro determinista (evita respuestas del tipo “no proporcionamos...”)
            if cats:
                ai = f"Te muestro opciones para {', '.join(cats)}."
            else:
                ai = "Te muestro opciones disponibles."
            if ventilador_mode:
                ai = VENTILADOR_NOTE
            return ChatOut(
                content=ai,
                products=_pack_products(page_items),
                page=page,
                last_query=q,
                has_more=has_more
            )

        # Sin resultados reales
        st["had_evidence"] = False
        st["topic_tokens"] = []
        st["last_query"]   = ""
        respuesta = (
            "No encontré productos que coincidan con lo que buscas. "
            "Cuéntame qué espacio quieres iluminar o qué tipo de producto necesitas 😊"
        )
        return ChatOut(
            content=VENTILADOR_NOTE if ventilador_mode else respuesta,
            products=[],
            page=0,
            last_query="",
            has_more=False
        )

    except HTTPException:
        raise
    except Exception:
        return ChatOut(
            content="Tuvimos un inconveniente técnico. Intenta de nuevo.",
            products=[],
            page=0,
            last_query=in_.message or "",
            has_more=False
        )
