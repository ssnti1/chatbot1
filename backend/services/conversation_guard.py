from __future__ import annotations
import re
import unicodedata
from typing import Dict, List, Set
from collections import Counter


# -----------------------
# Normalización y tokens
# -----------------------
def _norm(text: str) -> str:
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s\-\._#/]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _tokens(text: str) -> List[str]:
    t = _norm(text)
    t = re.sub(r"(\d+)\s*w", r"\1w", t)
    t = re.sub(r"ip\s*(\d{2})", r"ip\1", t)
    t = re.sub(r"(\d{4})\s*k", r"\1k", t)
    return [x for x in re.split(r"[\s/_.\-#]+", t) if x]


# ---------------------------------
# Vocabulario vivo del catálogo
# ---------------------------------
def build_vocab_from_catalog(products: List[Dict]) -> Set[str]:
    vocab: Set[str] = set()
    fields = (
        "name",
        "nombre",
        "category",
        "categoria",
        "categorias",
        "tags",
        "etiquetas",
    )
    for p in products or []:
        for f in fields:
            v = p.get(f)
            if isinstance(v, str):
                vocab.update(_tokens(v))
            elif isinstance(v, list):
                for s in v:
                    if isinstance(s, str):
                        vocab.update(_tokens(s))

    # Señales genéricas de iluminación
    vocab.update(
        _tokens(
            "led luminaria reflector panel cinta perfil downlight campana highbay aplique bombillo riel dicroico driver fotocelda poste"
        )
    )
    vocab.update(
        _tokens(
            "3000k 4000k 5000k 6500k ip65 ip66 ip67 ip68 5w 10w 20w 30w 50w 100w 150w 200w 400w"
        )
    )
    return vocab


def _category_counter(products: List[Dict]) -> Counter:
    c = Counter()
    for p in products or []:
        for key in ("categoria", "categorias", "category"):
            v = p.get(key)
            if isinstance(v, str):
                c[_norm(v)] += 1
            elif isinstance(v, list):
                for s in v:
                    if isinstance(s, str):
                        c[_norm(s)] += 1
    return c


def build_catalog_context(products: List[Dict], top_k: int = 10) -> str:
    """
    Devuelve un snippet de contexto (sin frases fijas de respuesta)
    con categorías y tokens frecuentes del catálogo.
    """
    cats = [k for k, _ in _category_counter(products).most_common(top_k)]
    vocab = build_vocab_from_catalog(products)
    common_tokens = [
        t
        for t in sorted(list(vocab))
        if re.match(r"^\d+w$|^ip\d{2}$|^\d{4}k$|^[a-z]{4,}$", t)
    ]
    common_tokens = common_tokens[:40]

    ctx = []
    if cats:
        ctx.append("CATEGORIAS_RELEVANTES=" + ", ".join(cats))
    if common_tokens:
        ctx.append("TOKENS_UTILES=" + ", ".join(common_tokens))
    return "\n".join(ctx)


# ---------------------------------
# Clasificación (sin listas fijas por palabra)
# ---------------------------------
_SMALLTALK = re.compile(
    r"\b(hola|buen[oa]s|gracias|muchas gracias|adios|hasta luego|buen dia|buenas tardes|buenas noches|que tal|como estas)\b",
    re.IGNORECASE,
)


def classify_message(msg: str, catalog_vocab: Set[str]) -> str:
    """
    'smalltalk' | 'inscope' | 'offtopic'
    - No hay reglas por término del negocio; se usa cobertura del vocabulario del catálogo.
    """
    if not msg:
        return "smalltalk"
    if _SMALLTALK.search(msg):
        return "smalltalk"

    toks = _tokens(msg)
    if not toks:
        return "smalltalk"

    hits = sum(
        1
        for t in toks
        if t in catalog_vocab or re.match(r"^\d+w$|^ip\d{2}$|^\d{4}k$", t)
    )
    coverage = hits / max(1, len(toks))

    if hits >= 1 or coverage >= 0.25:
        return "inscope"

    # Si no hay cobertura suficiente >> offtopic
    return "offtopic"
