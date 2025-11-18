import re
from fastapi import APIRouter

router = APIRouter(prefix="/faq", tags=["faq"])



FAQ_RESPONSES = [

    {
        "patterns": [
            r"qu[eé]\s+es\s+ecolite",
            r"h[aá]blame\s+de\s+ecolite",
            r"qui[eé]nes?\s+son\s+ecolite",
            r"sobre\s+ecolite",
            r"acerca\s+de\s+ecolite",
            r"empresa\s+ecolite",
        ],
        "response": (
            "Ecolite es una empresa dedicada a la comercialización de soluciones de iluminación LED "
            "para aplicaciones comerciales, industriales, residenciales y decorativas, en interiores y exteriores."
            "https://ecolite.com.co"
        ),
    },

    {
        "patterns": [
            r"qu[eé]\s+hacen",
            r"a\s+qu[eé]\s+se\s+dedican",
            r"qu[eé]\s+ofrecen",
            r"servicios?",
            r"actividad",
        ],
        "response": (
            "Ecolite ofrece soluciones de iluminación LED orientadas a eficiencia, durabilidad y ahorro energético. "
            "Sus productos cumplen lineamientos técnicos y normativos como RETILAP."
        ),
    },

{
    "patterns": [
        r"misi[oó]n",
        r"prop[oó]sito",
    ],
    "response": (
        "La misión de Ecolite es identificar y ofrecer las mejores alternativas de iluminación que ayuden "
        "a ahorrar energía, reducir costos y cuidar el medio ambiente.\n\n"
        "Ecolite trabaja para contribuir a la construcción de ciudades más sostenibles, apoyando la "
        "transición hacia energías limpias y enfrentando retos como la rápida urbanización, la "
        "contaminación ambiental y el cambio climático.\n\n"
        "A través de soluciones de iluminación LED para aplicaciones comerciales, industriales, "
        "residenciales y decorativas, Ecolite busca brindar productos eficientes, confiables y "
        "responsables con el entorno."
    ),
},
    {
        "patterns": [
            r"valores?",
            r"principios",
            r"filosof[ií]a",
        ],
        "response": (
            "Valores Ecolite:\n"
            "- Calidad en productos\n"
            "- Buena relación costo-beneficio\n"
            "- Acompañamiento al cliente\n"
            "- Responsabilidad y orden\n"
            "- Construcción de relaciones a largo plazo"
        ),
    },

    {
        "patterns": [
            r"logo",
            r"marca",
            r"girasol",
            r"identidad",
        ],
        "response": (
            "La marca representa la unión entre tecnología y naturaleza. "
            "El girasol simboliza energía limpia y eficiencia en iluminación."
        ),
    },

    {
        "patterns": [
            r"direcci[oó]n",
            r"ubicaci[oó]n",
            r"d[oó]nde\s+est[aá]n",
            r"d[oó]nde\s+queda",
            r"sede",
            r"ubicada",
            r"oficina",
            r"bodega",
            r"punto\s+de\s+atenci[oó]n",
        ],
        "response": (
            "Sede administrativa y centro de distribución:\n"
            "Calle 41 # 6-16, Bodega 2, Cali, Valle del Cauca, Colombia.\n"
            "Se atienden proyectos en todo el país."
        ),
    },

{
    "patterns": [
        r"env[ií]os?",
        r"despachos?",
        r"entregas?",
        r"cubren\s+todo\s+el\s+pa[ií]s",
    ],
    "response": (
        "Ecolite realiza envíos y despachos a nivel nacional en Colombia.\n\n"
        "En muchos de nuestros productos manejamos envío nacional con tiempos de entrega "
        "habituales entre 24 y 48 horas; además contamos con logística para despachos a nivel "
        "nacional con tiempos de entrega de 1 hasta 3 días en ciudades principales, dependiendo "
        "de la zona y de la transportadora.\n\n"
        "En compras realizadas bajo ciertas promociones, los pedidos pueden presentar entre 3 y "
        "6 días hábiles adicionales sobre los tiempos de entrega normales del sitio.\n\n"
        "Los envíos se realizan a través de empresas de mensajería y carga aliadas, buscando que "
        "tus productos lleguen de forma segura y en el menor tiempo posible."
    ),
},



    {
        "patterns": [
            r"garant[ií]a",
            r"c[oó]mo\s+funciona\s+la\s+garant[ií]a",
            r"tiempo\s+de\s+garant[ií]a",
            r"cubre\s+la\s+garant[ií]a",
        ],
        "response": (
            "La garantía es de 24 meses por defectos de fabricación. "
            "Se requiere la factura de compra y el producto debe ser evaluado técnicamente. "
            "La garantía no aplica en casos de mal uso, instalación inadecuada, modificaciones, daños por manejo "
            "o desgaste normal. Si se confirma defecto de fabricación, se realiza cambio por un producto de la misma "
            "referencia o características. No se realiza devolución de dinero " "https://ecolite.com.co/politicas-de-garantia"
        ),
    },

    {
        "patterns": [
            r"cambios?",
            r"cambiar",
            r"quiero\s+cambiar",
            r"quiero\s+hacer\s+un\s+cambio",
            r"quiero\s+devolver",
            r"solicitar\s+un\s+cambio",
            r"cambio\s+de\s+producto",
            r"devoluci[oó]n",
        ],
        "response": (
            "Los cambios se pueden solicitar dentro de los 5 días calendario posteriores a la compra. "
            "El producto debe estar sin uso, en su empaque original y con todos sus accesorios. "
            "Se debe presentar la factura de compra. Si el cambio es por un producto de menor valor, "
            "se entrega un bono a favor para futuras compras."
        ),
    },
    {
        "patterns": [
            r"fichas?\s+t[eé]cnicas?",
            r"ficha\s+del\s+producto",
            r"ficha?\s+t[eé]cnica?",
            r"hoja\s+t[eé]cnica",
            r"datasheet",
            r"especificaciones?\s+t[eé]cnicas?",
            r"caracter[ií]sticas?\s+t[eé]cnicas?",
            r"manual\s+(t[eé]cnico|de\s+instalaci[oó]n)",
        ],
        "response": (
            "Para ver la ficha técnica de un producto, la podrás encontrar en nuestra página web utilizando el enlace que aparece en las busquedas de producto."
        ),
    },
]

def faq_try_answer(message: str):
    text = (message or "").lower()
    for item in FAQ_RESPONSES:
        for pattern in item["patterns"]:
            if re.search(pattern, text):
                return item["response"]
    return None


@router.get("/")
async def get_all_faqs():
    return {"faqs": [i["response"] for i in FAQ_RESPONSES]}
