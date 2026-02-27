import os, re

def _brief(s: str, max_words: int = 25) -> str:
    s = re.sub(r"\s+", " ", (s or "").strip())
    parts = re.split(r"(?<=[.!?])\s+", s)
    s = parts[0] if parts and parts[0] else s
    words = s.split()
    if len(words) > max_words:
        s = " ".join(words[:max_words]) + "."
    if s and s[-1] not in ".!?":
        s += "."
    return s or "¿Te ayudo a encontrar iluminación del catálogo?"

def chat(system_prompt: str, user_msg: str) -> str:
    """
    IA ultra-concisa y a prueba de fallos:
    - Si hay OPENAI_API_KEY y librería, usa OpenAI.
    - Si no, fallback local (una sola frase).
    """
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=api_key)
            sys = (system_prompt or "").strip() + "\n\nResponde en UNA sola frase (≤25 palabras)."
            resp = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                temperature=0.2,
                max_tokens=60,
                messages=[
                    {"role": "system", "content": sys},
                    {"role": "user", "content": user_msg or ""},
                ],
            )
            text = (resp.choices[0].message.content or "").strip()
            return _brief(text)
        except Exception:
            pass
    return _brief("Puedo ayudarte con iluminación del catálogo; dime el espacio o especificaciones.")
