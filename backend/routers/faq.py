from fastapi import APIRouter
import re

router = APIRouter(prefix="/faq", tags=["faq"])

@router.get("/")
def faq():
    return {
        "empresa": "Somos Ecolite, expertos en iluminación LED en Colombia.",
        "mision": "Ahorrar energía, reducir costos y cuidar el medio ambiente.",
        "direccion": "Cali, Calle 41 #6-16, Bodega 2",
        "telefono": "(602) 3827064 / 316-875-9639",
        "correo": "info@ecolite.com.co",
        "garantia": "Todos los productos tienen 24 meses de garantía."
    }

FAQS = {
    "garantia": (
        "🛡️ Todos nuestros productos cuentan con 24 meses de garantía por defectos de fabricación. "
        "Para hacerla válida debes presentar la factura original, el producto en su empaque con accesorios y catálogos. "
        "El diagnóstico se realiza en máximo 15 días hábiles tras la reclamación. "
        "Si el daño es de fábrica, se reemplaza por uno igual o similar (no se devuelve dinero)."
    ),
    
    "casos_sin_garantia": (
        "❌ La garantía no aplica en casos de accidente, mal uso, instalación inadecuada, "
        "condiciones anormales de operación, alteraciones, intentos de reparación, "
        "desgaste normal o daños ocurridos en envío."
    ),
    "cambio_producto": (
        "🔄 Puedes solicitar cambio por otro producto diferente en máximo 5 días calendario después de la compra. "
        "Debe estar sin usar, con empaque original, accesorios y catálogos, presentando la factura."
    ),
    "plazo_reclamo": (
        "📅 El plazo máximo de respuesta para una solicitud de garantía es de 15 días hábiles desde su recepción."
    ),
    "politica_envios": (
        "🚚 Realizamos envíos a todo el país. El tiempo estimado de entrega es de 2 a 5 días hábiles, "
        "dependiendo de la ciudad y la transportadora."
    ),
    "politica_devoluciones": (
        "↩️ No realizamos devolución de dinero por garantía. "
        "En caso de daño de fábrica comprobado, se cambia el producto por otro del mismo modelo o similar de igual valor."
    ),
    "quienes_somos": (
        "💡 Somos Ecolite S.A.S., una empresa colombiana dedicada a soluciones de iluminación LED eficientes, "
        "modernas y sostenibles, para hogares, oficinas, industria y alumbrado público."
    ),
    "contacto": (
        "📞 Puedes comunicarte con nosotros a través de nuestra página web https://ecolite.com.co "
        "o en nuestras líneas de atención para soporte y garantías."
    ),
}

def try_answer(user_msg: str) -> str | None:
    """Devuelve una respuesta de FAQ si el mensaje del usuario coincide con una palabra clave."""
    msg = user_msg.lower()

    rules = {
        "garantia": ["garantia", "garantía"],
        "casos_sin_garantia": ["no cubre", "cuando no", "casos sin garantia"],
        "plazo_reclamo": ["plazo", "tiempo", "dias", "días"],
        "politica_envios": ["envio", "envíos", "enviar", "domicilio", "llega"],"politica_devoluciones": ["devolucion", "devolución", "reembolso", "reembolsar", "quiero reembolsar"],
        "cambio_producto": ["cambiar", "cambio", "devolver", "devolucion", "devolución", "cambiar producto"],
        "quienes_somos": ["quienes son", "empresa", "ecolite", "quiénes"],
        "contacto": ["contacto", "telefono", "correo", "atencion"],
    }

    for key, keywords in rules.items():
        if any(re.search(rf"\b{k}\b", msg) for k in keywords):
            return FAQS[key]

    return None
