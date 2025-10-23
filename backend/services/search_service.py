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

    # Excepciones frecuentes
    EXC = {"leds": "led"}
    if t in EXC:
        return EXC[t]

    # Evitar falsos positivos en tokens muy cortos
    if len(t) <= 4:
        return t

    vowels = set("aeiou")

    # luces -> luz (ces -> z)
    if t.endswith("ces") and len(t) > 3:
        return t[:-3] + "z"

    # Caso 1: plural tipo 'paneles' -> 'panel' (consonante + 'es')
    # Solo si el stem termina en consonantes naturales en español
    if t.endswith("es") and len(t) > 3:
        stem = t[:-2]
        if stem and stem[-1] in {"l", "r", "n", "d", "z"}:
            return stem
        # Si no cumple, probamos con regla de vocal + 's' (p.ej. 'postes' -> 'poste')

    # Caso 2: plural tipo 'postes', 'nichos', 'muebles' -> quitar la 's' si hay vocal antes
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

    _VOCAB = {t for t in vocab if len(t) >= 3}
    _INDEX = idx
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
    """Top-N por similitud global (sin offset). La paginación la hace el router."""
    _ensure_index(products)
    terms = _expand_query(query)
    if not terms:
        return []
    scored: List[Tuple[float, Dict]] = []
    for row in _INDEX:
        s = _score(row, terms)
        if s > 0:
            scored.append((s, row["ref"]))
    scored.sort(key=lambda x: (-x[0], _norm(x[1].get("name", ""))))
    return [p for _, p in scored[:limit * 5]] 
