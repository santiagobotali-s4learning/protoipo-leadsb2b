"""
Enriquecimiento de empresas vía búsqueda web (Serper.dev) + análisis con
Claude (Anthropic): LinkedIn, señales de actividad/riesgo, y búsqueda de
contactos por rol cuando el DENUE no trae un correo utilizable.
"""
from typing import Optional

import anthropic
import requests
import streamlit as st
from pydantic import BaseModel, Field

from config import MODELO_ENRIQUECIMIENTO, ROLES_CONTACTO, SERPER_URL, TODOS_LOS_ROLES


def roles_a_buscar(rol_elegido):
    """dict {rol: términos} a recorrer según lo elegido en el selector."""
    if rol_elegido == TODOS_LOS_ROLES:
        return ROLES_CONTACTO
    return {rol_elegido: ROLES_CONTACTO[rol_elegido]}


def _dedup_contactos(contactos):
    """Saca duplicados cuando la misma persona aparece en más de un rol (ej.
    'Director Comercial' matchea tanto Dirección general como Ventas).
    Identifica por LinkedIn si hay, si no por nombre normalizado."""
    vistos = set()
    unicos = []
    for contacto in contactos:
        clave = (contacto.linkedin_url or contacto.nombre or "").strip().lower()
        if clave and clave not in vistos:
            vistos.add(clave)
            unicos.append(contacto)
    return unicos


class EnriquecimientoEmpresa(BaseModel):
    linkedin_url: Optional[str] = Field(
        default=None, description="URL de la página de LinkedIn de la empresa, si se encontró"
    )
    sitio_web: Optional[str] = Field(
        default=None,
        description=(
            "URL del sitio web oficial de la empresa (no LinkedIn ni un directorio de "
            "terceros), si se encontró en los resultados de búsqueda. None si no hay certeza."
        ),
    )
    empleados_linkedin: Optional[str] = Field(
        default=None,
        description=(
            "Mejor señal de tamaño de plantilla encontrada: rango de empleados de "
            "LinkedIn (ej. '201-500 employees'), seguidores de LinkedIn, o cantidad "
            "de sucursales/tiendas mencionada. Indicá la fuente entre paréntesis. "
            "None si no se encontró nada útil."
        ),
    )
    actividad_reciente: bool = Field(
        description="True si hay evidencia de actividad reciente: noticias, expansión, nueva sucursal, contratación"
    )
    resumen_actividad: Optional[str] = Field(
        default=None, description="Resumen breve en español de la señal de actividad encontrada"
    )
    senales_riesgo: bool = Field(
        description="True si hay evidencia de riesgo: cierre, quiebra, demanda"
    )
    resumen_riesgo: Optional[str] = Field(
        default=None, description="Resumen breve en español de la señal de riesgo, si aplica"
    )
    confianza_coincidencia: str = Field(
        description=(
            "'alta', 'media' o 'baja': qué tan seguro estás de que los resultados de "
            "búsqueda corresponden a ESTA empresa y no a un homónimo, según si coinciden "
            "actividad económica y ubicación. No mide qué tan confiable es el dato de "
            "empleados en sí, solo si encontraste a la empresa correcta."
        )
    )
    evidencia: str = Field(
        description="Cita textual breve (1-3 frases) de los snippets que respaldan las conclusiones"
    )
    tipo_empresa: Optional[str] = Field(
        default=None,
        description=(
            "Clasificación de la empresa en UNA de estas categorías exactas — deben "
            "quedar EXACTAS, sin acentos, así calzan con los labels reales del board "
            "de Cuentas en Monday: "
            "'Empresa privada', 'Empresa publica', 'Institucion educativa publica', "
            "'Institucion educativa privada', 'Secretarias de Gobierno', 'Alcaldias', "
            "'Municipios', 'DIF', 'Confederaciones', 'Camaras empresariales', "
            "'Sindicatos', 'Fundaciones', 'Capitales Mixtos'. Inferí a partir de la "
            "razón social y la actividad económica (DENUE) — no hace falta evidencia "
            "de los resultados de búsqueda para esto. Si no hay ninguna señal de que "
            "sea otra cosa, usá 'Empresa privada' (es la categoría más común en el DENUE)."
        ),
    )
    rfc: Optional[str] = Field(
        default=None,
        description=(
            "RFC (Registro Federal de Contribuyentes mexicano) de la empresa, SOLO si "
            "aparece explícitamente y de forma legible en los resultados de búsqueda, "
            "con certeza de que corresponde a ESTA empresa. Nunca lo inventes, lo "
            "deduzcas del nombre ni lo completes a medias. None si no aparece."
        ),
    )


@st.cache_data(ttl="24h", show_spinner=False)
def buscar_serper(query, api_key):
    payload = {"q": query, "hl": "es", "gl": "mx", "num": 8}
    headers = {"X-API-KEY": api_key, "Content-Type": "application/json"}
    # Un timeout de 30s en Serper suele ser un bache transitorio — se
    # reintenta una vez antes de darlo por perdido.
    response = None
    for intento in range(2):
        try:
            response = requests.post(SERPER_URL, json=payload, headers=headers, timeout=30)
            break
        except requests.exceptions.Timeout:
            if intento == 1:
                raise
    response.raise_for_status()
    data = response.json()
    # A diferencia de SerpAPI, Serper no marca "sin resultados" con un campo
    # "error" — devuelve "organic": [] directamente (confirmado empíricamente).
    return [
        {
            "titulo": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
        }
        for r in data.get("organic", [])
    ]


def _buscar_serper_seguro(query, api_key):
    """Como buscar_serper, pero una falla (ej. timeout tras el reintento) no
    tira una excepción — devuelve None para que el resto de las búsquedas de
    la empresa sigan corriendo en vez de perderse todas por una sola falla."""
    try:
        return buscar_serper(query, api_key)
    except Exception:
        return None


def _formatear_resultados(resultados):
    if resultados is None:
        return "(no se pudo buscar — error de conexión)"
    if not resultados:
        return "(sin resultados)"
    return "\n".join(f"- {r['titulo']}: {r['snippet']} ({r['link']})" for r in resultados)


@st.cache_data(ttl="24h", show_spinner=False)
def enriquecer_empresa(razon_social, actividad, ubicacion, serper_api_key, anthropic_key):
    # Sin comillas: la razón social del DENUE (nombre legal, ej. "DISTRIBUIDORA
    # LIVERPOOL") casi nunca coincide textualmente con el nombre comercial que
    # usa la empresa en LinkedIn/prensa (ej. "El Puerto de Liverpool") — forzar
    # coincidencia exacta hacía fallar la búsqueda casi siempre.
    # "empleados" sumado a la búsqueda de LinkedIn (en vez de una búsqueda de
    # vacantes aparte) empuja a Google a mostrar la sub-página "Vida en la
    # empresa" de LinkedIn, que expone la cifra real de plantilla cuando
    # está pública — confirmado empíricamente. Sin ese término, la única
    # alternativa probada devolvía ruido de bolsas de trabajo (Indeed,
    # Computrabajo), sin ningún dato de plantilla real.
    resultados_linkedin = _buscar_serper_seguro(
        f"{razon_social} site:linkedin.com/company/ empleados", serper_api_key
    )
    resultados_actividad = _buscar_serper_seguro(
        f'{razon_social} (cierre OR quiebra OR demanda OR expansión OR "nueva sucursal" OR contratando)',
        serper_api_key,
    )
    resultados_sitio = _buscar_serper_seguro(f"{razon_social} México sitio oficial", serper_api_key)
    resultados_rfc = _buscar_serper_seguro(f'"{razon_social}" RFC', serper_api_key)

    contexto = (
        f"Empresa (según DENUE): {razon_social}\n"
        f"Actividad económica (DENUE): {actividad}\n"
        f"Ubicación (DENUE): {ubicacion}\n\n"
        f"Resultados de búsqueda 'LinkedIn':\n{_formatear_resultados(resultados_linkedin)}\n\n"
        f"Resultados de búsqueda 'actividad/riesgo':\n{_formatear_resultados(resultados_actividad)}\n\n"
        f"Resultados de búsqueda 'sitio oficial':\n{_formatear_resultados(resultados_sitio)}\n\n"
        f"Resultados de búsqueda 'RFC':\n{_formatear_resultados(resultados_rfc)}"
    )

    client = anthropic.Anthropic(api_key=anthropic_key)
    response = client.messages.parse(
        model=MODELO_ENRIQUECIMIENTO,
        max_tokens=1024,
        system=(
            "Analizás resultados de búsqueda web para enriquecer datos de una empresa "
            "mexicana extraída del DENUE. Antes de usar un resultado, verificá que "
            "corresponda a la MISMA empresa (misma actividad económica y ubicación "
            "aproximada) — si no hay certeza, marcá confianza baja. No inventes datos "
            "que no estén respaldados por los resultados de búsqueda. Para sitio_web: "
            "solo el dominio propio de la empresa, nunca linkedin.com, directorios de "
            "terceros (páginas amarillas, cámaras empresariales) ni redes sociales. "
            "Para rfc: es el único campo donde una alucinación es especialmente grave "
            "(se usa en documentos formales) — dejalo en None ante cualquier duda."
        ),
        messages=[{"role": "user", "content": contexto}],
        output_format=EnriquecimientoEmpresa,
    )
    return response.parsed_output


class ContactoEncontrado(BaseModel):
    nombre: Optional[str] = Field(
        default=None, description="Nombre completo de la persona encontrada en ese rol, si se encontró"
    )
    cargo: Optional[str] = Field(default=None, description="Cargo/título encontrado")
    linkedin_url: Optional[str] = Field(
        default=None, description="URL del perfil de LinkedIn de esa persona, si se encontró"
    )
    confianza_coincidencia: str = Field(
        description="'alta', 'media' o 'baja': qué tan seguro estás de que esta persona trabaja realmente en esta empresa"
    )


@st.cache_data(ttl="24h", show_spinner=False)
def buscar_contacto_por_rol(razon_social, terminos_rol, serper_api_key, anthropic_key):
    resultados = buscar_serper(
        f"{razon_social} México ({terminos_rol}) site:linkedin.com/in/", serper_api_key
    )
    contexto = (
        f"Empresa: {razon_social}\n\n"
        f"Resultados de búsqueda de perfiles de LinkedIn:\n{_formatear_resultados(resultados)}"
    )
    client = anthropic.Anthropic(api_key=anthropic_key)
    response = client.messages.parse(
        model=MODELO_ENRIQUECIMIENTO,
        max_tokens=512,
        system=(
            "Identificás, a partir de resultados de búsqueda web, a una persona real que "
            "trabaje en el rol pedido en la empresa indicada. Verificá que el perfil "
            "mencione efectivamente esa empresa antes de darlo por válido — si no hay "
            "certeza, marcá confianza baja. No inventes nombres ni cargos."
        ),
        messages=[{"role": "user", "content": contexto}],
        output_format=ContactoEncontrado,
    )
    return response.parsed_output


class LinkedInPersona(BaseModel):
    linkedin_url: Optional[str] = Field(
        default=None,
        description="URL del perfil de LinkedIn de esta persona en esta empresa, si se encontró",
    )
    confianza_coincidencia: str = Field(
        description=(
            "'alta', 'media' o 'baja': qué tan seguro estás de que el perfil encontrado "
            "corresponde a ESTA persona en ESTA empresa (no un homónimo en otra empresa "
            "o ciudad)."
        )
    )


@st.cache_data(ttl="24h", show_spinner=False)
def buscar_linkedin_de_persona(nombre, razon_social, serper_api_key, anthropic_key):
    """Busca el LinkedIn de una persona ya identificada (con nombre real) cuando
    la fuente que la trajo (Hunter Combined Enrichment o Domain Search) no traía
    ese dato — mismo patrón que buscar_contacto_por_rol, pero la búsqueda parte
    de un nombre concreto en vez de un rol genérico."""
    resultados = buscar_serper(f"{nombre} {razon_social} site:linkedin.com/in/", serper_api_key)
    contexto = (
        f"Persona: {nombre}\n"
        f"Empresa: {razon_social}\n\n"
        f"Resultados de búsqueda de perfiles de LinkedIn:\n{_formatear_resultados(resultados)}"
    )
    client = anthropic.Anthropic(api_key=anthropic_key)
    response = client.messages.parse(
        model=MODELO_ENRIQUECIMIENTO,
        max_tokens=256,
        system=(
            "Identificás, a partir de resultados de búsqueda web, el perfil de LinkedIn de "
            "una persona concreta que trabaja en una empresa concreta. Verificá que el "
            "perfil mencione efectivamente esa empresa antes de darlo por válido — si no "
            "hay certeza (ej. homónimo en otra empresa), marcá confianza baja y dejá "
            "linkedin_url en None. No inventes URLs."
        ),
        messages=[{"role": "user", "content": contexto}],
        output_format=LinkedInPersona,
    )
    return response.parsed_output
