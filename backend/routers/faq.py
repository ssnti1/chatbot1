import re
from fastapi import APIRouter

router = APIRouter(prefix="/faq", tags=["faq"])

# Respuestas exactas tomadas de la página "Nosotros" de Ecolite
# https://ecolite.com.co/nosotros/

FAQ_RESPONSES = [

    # Quiénes somos / Sobre Ecolite
    {
        "patterns": [
            r"qu[eé]\s+es\s+ecolite",
            r"(?:h[aá]blame|hablame)\s+de\s+ecolite",
            r"qui[eé]nes?\s+son\s+ecolite",
            r"(?:acerca|sobre)\s+ecolite",
            r"empresa.*ecolite",
            r"ecolite\s+qu[eé]\s+es",
        ],
        "response": (
            "En Ecolite, somos líderes en la comercialización de soluciones de iluminación LED de alta calidad. Ofrecemos un extenso portafolio de productos diseñados para satisfacer las necesidades de iluminación en diversas aplicaciones, incluyendo proyectos comerciales, industriales, residenciales y decorativos, tanto en interiores como en exteriores."
        ),
    },

    # Qué hacemos / Enfoque
    {
        "patterns": [
            r"qu[eé]\s+hacen",
            r"a\s+qu[eé]\s+se\s+dedican",
            r"qu[eé]\s+ofrecen",
            r"servicios?",
        ],
        "response": (
            "Se dedican a ofrecer soluciones innovadoras y eficientes en iluminación LED, "
            "con productos desarrollados bajo estándares de calidad ISO 9001:2015 y cumpliendo RETILAP."
        ),
    },

    # Misión
    {
        "patterns": [
            r"misi[oó]n",
            r"para\s+qu[eé]",
        ],
        "response": (
            "Su misión es identificar y proveer las mejores alternativas en iluminación que permitan ahorrar energía, "
            "reducir costos y proteger el medio ambiente."
        ),
    },

    # Marca
    {
        "patterns": [
            r"marca",
            r"logo",
            r"girasol",
        ],
        "response": (
            "La marca representa la unión de la tecnología con la naturaleza. "
            "El girasol del logo se fusiona con iluminación limpia y eficiente que genera ahorro y cuida el planeta."
        ),
    },

    # Valores
    {
        "patterns": [
            r"valores?",
            r"principios",
        ],
        "response": (
            "Valores Ecolite:\n"
            "• Comercializar productos de excelente calidad\n"
            "• Ofrecer la mejor relación costo‑beneficio del mercado\n"
            "• Ayudar al máximo a los clientes y ser conscientes de sus necesidades\n"
            "• Ser honestos, responsables y ordenados\n"
            "• Construir relaciones comerciales a largo plazo"
        ),
    },

    # Tecnología LED
    {
        "patterns": [
            r"qu[eé]\s+es\s+led",
            r"tecnolog[ií]a\s+led",
            r"ventajas.*led",
        ],
        "response": (
            "LED (Light Emitting Diode) es un dispositivo semiconductor que emite luz eficiente y de alto rendimiento "
            "al recibir una corriente eléctrica de baja intensidad. "
            "Ventajas: bajo consumo, 40.000h de vida útil, resistencia a golpes, baja emisión de calor, "
            "sin mercurio ni plomo, alto IRC, encendido instantáneo, libre de mantenimiento, programable y diseño compacto."
        ),
    },

]


def faq_try_answer(message: str):
    """
    Devuelve una respuesta si encuentra coincidencia con el FAQ, o None si no hay match.
    """
    text = (message or "").lower()
    for item in FAQ_RESPONSES:
        for pattern in item["patterns"]:
            if re.search(pattern, text):
                return item["response"]
    return None


@router.get("/")
async def get_all_faqs():
    return {"faqs": [i["response"] for i in FAQ_RESPONSES]}
