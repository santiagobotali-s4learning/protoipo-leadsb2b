"""
Integración con Hunter.io: verificación y búsqueda de correos, y una
corroboración cruzada con SerpAPI (vía enrichment.buscar_serpapi) para
puntuar la confianza del correo final.
"""
import requests
import streamlit as st

from config import HUNTER_URL
from enrichment import buscar_serpapi


def _hunter_data(response):
    """Extrae la clave 'data' de una respuesta de Hunter. Si no está (ej.
    dominios sin cobertura, plan sin crédito), muestra el error real que
    manda Hunter (campo 'errors') en vez de un KeyError sin contexto."""
    cuerpo = response.json()
    if "data" not in cuerpo:
        raise ValueError(f"Hunter no devolvió datos: {cuerpo.get('errors') or cuerpo}")
    return cuerpo["data"]


@st.cache_data(ttl="24h", show_spinner=False)
def hunter_verificar_email(email, api_key):
    response = requests.get(
        f"{HUNTER_URL}/email-verifier", params={"email": email, "api_key": api_key}, timeout=30
    )
    response.raise_for_status()
    data = _hunter_data(response)
    return {"estado": data.get("status"), "score": data.get("score")}


@st.cache_data(ttl="24h", show_spinner=False)
def hunter_enriquecimiento_combinado(email, api_key):
    """Dado un correo, busca a la persona dueña (nombre, cargo, LinkedIn). None si
    Hunter no tiene información asociada a ese correo (404)."""
    response = requests.get(
        f"{HUNTER_URL}/combined/find", params={"email": email, "api_key": api_key}, timeout=30
    )
    if response.status_code == 404:
        return None
    try:
        response.raise_for_status()
    except requests.exceptions.HTTPError as exc:
        # El mensaje default de requests no trae el cuerpo de la respuesta —
        # sin esto, un 400 se ve como "Bad Request" sin decir por qué.
        raise requests.exceptions.HTTPError(f"{exc} — {response.text}", response=response) from exc
    persona = _hunter_data(response).get("person") or {}
    nombre = (persona.get("name") or {}).get("fullName")
    cargo = (persona.get("employment") or {}).get("title")
    linkedin_handle = (persona.get("linkedin") or {}).get("handle")
    return {
        "nombre": nombre,
        "cargo": cargo,
        "linkedin": f"https://www.linkedin.com/in/{linkedin_handle}" if linkedin_handle else None,
    }


@st.cache_data(ttl="24h", show_spinner=False)
def hunter_buscar_email(dominio, nombre_completo, api_key):
    """Dado un dominio y el nombre de una persona, intenta adivinar su correo.
    None si no hay dominio o Hunter no pudo estimar un correo."""
    if not dominio or not nombre_completo:
        return None
    partes = nombre_completo.strip().split(" ", 1)
    if len(partes) < 2:
        return None
    response = requests.get(
        f"{HUNTER_URL}/email-finder",
        params={
            "domain": dominio,
            "first_name": partes[0],
            "last_name": partes[1],
            "api_key": api_key,
        },
        timeout=30,
    )
    response.raise_for_status()
    data = _hunter_data(response)
    if not data.get("email"):
        return None
    fuentes = data.get("sources") or []
    urls_fuente = [
        f.get("uri") or f.get("url") or f.get("domain")
        for f in fuentes
        if isinstance(f, dict) and (f.get("uri") or f.get("url") or f.get("domain"))
    ]
    return {
        "email": data["email"],
        "score": data.get("score"),
        "sources": urls_fuente,
    }


@st.cache_data(ttl="24h", show_spinner=False)
def hunter_correos_del_dominio(dominio, api_key, limite=5):
    """Lista de correos de personas (no genéricos tipo info@) que Hunter ya
    tiene indexados para un dominio, con nombre, cargo, LinkedIn y confianza
    propios — para dar varias opciones de contacto en vez de una sola."""
    if not dominio:
        return []
    response = requests.get(
        f"{HUNTER_URL}/domain-search",
        params={"domain": dominio, "api_key": api_key, "limit": limite, "type": "personal"},
        timeout=30,
    )
    response.raise_for_status()
    emails = _hunter_data(response).get("emails") or []
    return [
        {
            "correo": e.get("value"),
            "nombre": f"{e.get('first_name') or ''} {e.get('last_name') or ''}".strip() or None,
            "cargo": e.get("position"),
            "linkedin": e.get("linkedin"),
            "confianza": e.get("confidence"),
        }
        for e in emails
    ]


def verificar_dominio_legitimo(dominio, serpapi_key):
    """Corrobora vía web que el dominio tiene presencia real (no un dominio
    inventado o mal adivinado). No corrobora el correo exacto: probamos que
    buscar la dirección literal casi nunca encuentra nada (son correos
    administrativos, no públicos) — el dominio sí se puede verificar."""
    if not dominio:
        return {"presencia_web": False, "resultados": []}
    resultados = buscar_serpapi(f"site:{dominio}", serpapi_key)
    return {"presencia_web": len(resultados) > 0, "resultados": resultados}


def calcular_score_correo(score_hunter, dominio, razon_social, serpapi_key):
    """Combina el score técnico de Hunter (servidor de correo real) con una
    corroboración web de que el dominio pertenece efectivamente a la empresa,
    y clasifica el resultado según un umbral."""
    score = score_hunter or 0
    verificacion = verificar_dominio_legitimo(dominio, serpapi_key)
    if verificacion["presencia_web"]:
        score = min(100, score + 15)
        texto = " ".join(
            f"{r['titulo']} {r['snippet']}" for r in verificacion["resultados"]
        ).lower()
        palabras_clave = [p.lower() for p in str(razon_social).split() if len(p) > 3]
        if any(p in texto for p in palabras_clave):
            score = min(100, score + 10)

    if score >= 80:
        etiqueta = "Alta confianza"
    elif score >= 50:
        etiqueta = "Revisar antes de usar"
    else:
        etiqueta = "Baja confianza — no usar sin verificar"
    return score, etiqueta
