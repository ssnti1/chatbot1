import re
import unicodedata
import random
from typing import List, Dict, Tuple, Set

# -------- Utilidades --------
def _norm(s: str) -> str:
    s = (s or "").lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = re.sub(r"[^a-z0-9%.\s-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def _tok(s: str) -> List[str]:
    """
    Tokeniza y añade la forma singular de cada token
    para que 'nichos', 'postes', 'paneles', etc. coincidan con el índice.
    No hace expansiones adicionales.
    """
    base = [t for t in _norm(s).split() if t]
    out: List[str] = []
    seen = set()
    for t in base:
        if t not in seen:
            out.append(t); seen.add(t)
        sg = singularize_es(t)
        if sg and sg != t and sg not in seen:
            out.append(sg); seen.add(sg)
    return out


# --- Morfología simple (plural → singular, conservadora y data-friendly) ---
def singularize_es(token: str) -> str:
    """
    Reglas seguras para pasar de plural a singular:
      - luces      -> luz        (ces -> z)
      - paneles    -> panel      (consonante + 'es' -> ∅ si el resultado termina en l/r/n/d/z)
      - reflectores-> reflector
      - postes     -> poste      (vocal + 's' -> ∅)   [evita 'postes'->'post']
      - nichos     -> nicho
      - muebles    -> mueble
      - leds       -> led        (excepción)
    """
    t = (token or "").strip().lower()

    EXC = {"leds": "led"}
    if t in EXC:
        return EXC[t]

    if len(t) <= 4:
        return t

    vowels = set("aeiou")

    if t.endswith("ces") and len(t) > 3:
        return t[:-3] + "z"

    if t.endswith("es") and len(t) > 3:
        stem = t[:-2]
        if stem and stem[-1] in {"l", "r", "n", "d", "z"}:
            return stem

    if t.endswith("s") and len(t) > 3:
        if t[-2] in vowels:
            return t[:-1]

    return t


def _is_number_like(tok: str) -> bool:
    return bool(re.search(r"\d", tok))

def _jaro_distance(s1: str, s2: str) -> float:
    if s1 == s2:
        return 1.0
    len1, len2 = len(s1), len(s2)
    if len1 == 0 or len2 == 0:
        return 0.0
    max_dist = int(max(len1, len2) / 2) - 1
    match = 0
    h1 = [0] * len1
    h2 = [0] * len2
    for i in range(len1):
        start = max(0, i - max_dist)
        end = min(i + max_dist + 1, len2)
        for j in range(start, end):
            if s1[i] == s2[j] and h2[j] == 0:
                h1[i] = 1
                h2[j] = 1
                match += 1
                break
    if match == 0:
        return 0.0
    t = 0
    point = 0
    for i in range(len1):
        if h1[i]:
            while h2[point] == 0:
                point += 1
            if s1[i] != s2[point]:
                t += 1
            point += 1
    t //= 2
    return (match / len1 + match / len2 + (match - t) / match) / 3.0

def _jaro_winkler(s1: str, s2: str, p: float = 0.1, max_l: int = 4) -> float:
    j = _jaro_distance(s1, s2)
    l = 0
    for i in range(min(len(s1), len(s2))):
        if s1[i] == s2[i]:
            l += 1
        else:
            break
    l = min(max_l, l)
    return j + l * p * (1 - j)

# -------- Índice data-driven --------
_VOCAB: Set[str] = set()
_INDEX: List[Dict] = []
_DF: Dict[str, int] = {}    # <--- NUEVO: frecuencia documental de cada token
_DOCS: int = 0              # <--- NUEVO: cantidad de documentos
_BUILT = False


def _ensure_index(products: List[Dict]) -> None:
    """Índice y vocabulario derivados 100% del catálogo (sin sinónimos fijos)."""
    global _VOCAB, _INDEX, _BUILT
    if _BUILT and len(_INDEX) == len(products):
        return

    vocab = set()
    idx = []
    for p in products:
        name = _norm(p.get("name", ""))
        category = _norm(p.get("category", ""))
        tags = " ".join(_norm(t) for t in p.get("tags", []) if t)

        name = " ".join(t for t in name.split() if t not in {"luminaria", "luminarias"})

        desc = _norm(p.get("description", ""))
        blob = " ".join([name, category, tags, desc]).strip()

        row = {
            "ref": p,
            "name": name,
            "cat": category,
            "tags": tags,
            "desc": desc,
            "blob": blob,
            "name_tok": _tok(name),
            "cat_tok": _tok(category),
            "tags_tok": _tok(tags),
            "desc_tok": _tok(desc),
        }
        idx.append(row)
        vocab.update(row["name_tok"])
        vocab.update(row["cat_tok"])
        vocab.update(row["tags_tok"])
        vocab.update(row["desc_tok"])

    df: Dict[str, int] = {}
    for row in idx:
        # conjunto de tokens del documento (no repitas dentro del mismo doc)
        doc_tokens = set(row["name_tok"]) | set(row["cat_tok"]) | set(row["tags_tok"]) | set(row["desc_tok"])
        for t in doc_tokens:
            if len(t) >= 2:
                df[t] = df.get(t, 0) + 1

    _VOCAB = {t for t in vocab if len(t) >= 3}
    _INDEX = idx
    _DF = df              # <--- NUEVO
    _DOCS = len(idx)      # <--- NUEVO
    _BUILT = True


def _nearest_vocab_tokens(token: str, top_k: int = 4, min_sim: float = 0.90) -> List[Tuple[str, float]]:
    """Vecinos de vocabulario por similitud JW (más estricto para evitar falsos positivos como 'hola'→'solar')."""
    cands: List[Tuple[str, float]] = []
    for v in _VOCAB:
        s = _jaro_winkler(token, v)
        if s >= min_sim:
            cands.append((v, s))
    cands.sort(key=lambda x: (-x[1], x[0]))
    return cands[:top_k]


def _expand_query(query: str) -> List[str]:
    """
    Conservador: solo tokens + sus singulares (vía _tok).
    Evitamos expansión por vecinos para que no entren términos ajenos.
    """
    return _tok(query)


# --- FILTROS ESTRICTOS (añadir junto a otros helpers) ---
STRICT_TERMS = {"profesional"}  # puedes ampliar: {"profesional", "industrial", "decorativa", "solar"}

def _requires_strict(q_terms: List[str]) -> bool:
    return any(t in STRICT_TERMS for t in q_terms)

def _has_all_tokens_in_blob(blob: str, q_terms: List[str]) -> bool:
    # exige que cada token normalizado esté presente como substring en el blob ya normalizado
    return all(t in blob for t in q_terms)



def _best_token_sim(q: str, toks: List[str]) -> float:
    best = 0.0
    for ft in toks:
        s = _jaro_winkler(q, ft)
        if s > best:
            best = s
    return best

def _score(row: Dict, q_terms: List[str]) -> float:
    """Puntaje por campo + bonus por substring; sin reglas fijas."""
    if not q_terms:
        return 0.0

    W_NAME, W_TAGS, W_CAT, W_DESC = 1.0, 0.85, 0.65, 0.35
    score = 0.0
    matched = 0

    for t in q_terms:
        s_name = _best_token_sim(t, row["name_tok"])
        s_tags = _best_token_sim(t, row["tags_tok"])
        s_cat  = _best_token_sim(t, row["cat_tok"])
        s_desc = _best_token_sim(t, row["desc_tok"])
        substr_bonus = 0.15 if t in row["blob"] else 0.0

        best_s = max(s_name, s_tags, s_cat, s_desc)
        if best_s >= 0.72:
            matched += 1

        score += (s_name * W_NAME) + (s_tags * W_TAGS) + (s_cat * W_CAT) + (s_desc * W_DESC) + substr_bonus

        if _is_number_like(t) and t in row["blob"]:
            score += 0.25

    score += matched * 0.2
    return score


def search_candidates(products: List[Dict], query: str, limit: int = 12) -> List[Dict]:
    """
    Recuperación exacta pero 100% data-driven:
    - Filtra tokens del usuario por vocabulario del catálogo.
    - Exige SOLO los tokens 'informativos' (no ultra-frecuentes) según DF.
    - Los tokens muy comunes NO son obligatorios (pero sí cuentan al score).
    - Sin reglas fijas ni listas manuales.
    """
    _ensure_index(products)

    raw_terms = _expand_query(query)
    if not raw_terms:
        return []

    # tokens del query que existen en el vocabulario del catálogo
    q_terms = [t for t in raw_terms if t in _VOCAB]

    # Si no hubo cruce con catálogo, intenta recuperar con scoring libre
    if not q_terms:
        scored: List[Tuple[float, Dict]] = []
        for row in _INDEX:
            s = _score(row, raw_terms)
            if s > 0:
                scored.append((s, row["ref"]))
        scored.sort(key=lambda x: (-x[0], _norm(x[1].get("name",""))))
        return [p for _, p in scored[:limit * 5]]

    # --- Núcleo: decidir qué tokens son 'requeridos' con DF dinámico ---
    # ratio de frecuencia documental (0..1)
    def df_ratio(t: str) -> float:
        if _DOCS <= 0:
            return 1.0
        return _DF.get(t, 0) / float(_DOCS)


    REQUIRED = [t for t in q_terms if df_ratio(t) <= 0.60]
    OPTIONAL = [t for t in q_terms if t not in REQUIRED]

    scored: List[Tuple[float, Dict]] = []
    for row in _INDEX:
        blob = row["blob"]

        if REQUIRED and not all(t in blob for t in REQUIRED):
            continue

        s = _score(row, q_terms)
        if s > 0:
            scored.append((s, row["ref"]))

    scored.sort(key=lambda x: (-x[0], _norm(x[1].get("name",""))))
    return [p for _, p in scored[:limit * 5]]


