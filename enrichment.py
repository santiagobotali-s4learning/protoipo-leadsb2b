"""
Enriquecimiento de empresas vía búsqueda web (SerpAPI) + análisis con Claude
(Anthropic): LinkedIn, señales de actividad/riesgo, y búsqueda de contactos
por rol cuando el DENUE no trae un correo utilizable.
"""
from typing import Optional

import anthropic
import requests
import streamlit as st
from pydantic import BaseModel, Field

from config import MODELO_ENRIQUECIMIENTO, ROLES_CONTACTO, SERPAPI_URL, TODOS_LOS_ROLES


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
    contacto_rrhh: Optional[str] = Field(
        default=None,
        description=(
            "Nombre y cargo de una persona concreta de RRHH/compras/talento en esta "
            "empresa (ej. 'Lourdes González — Jefe de recursos humanos'), si se "
            "encontró un perfil real. None si no se encontró a nadie."
        ),
    )
    contacto_rrhh_url: Optional[str] = Field(
        default=None, description="URL del perfil de LinkedIn de ese contacto, si se encontró"
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


@st.cache_data(ttl="24h", show_spinner=False)
def buscar_serpapi(query, api_key):
    params = {
        "engine": "google",
        "q": query,
        "api_key": api_key,
        "hl": "es",
        "gl": "mx",
        "num": 8,
    }
    # Un timeout de 30s en SerpAPI suele ser un bache transitorio — se
    # reintenta una vez antes de darlo por perdido.
    response = None
    for intento in range(2):
        try:
            response = requests.get(SERPAPI_URL, params=params, timeout=30)
            break
        except requests.exceptions.Timeout:
            if intento == 1:
                raise
    response.raise_for_status()
    data = response.json()
    if "error" in data:
        # SerpAPI devuelve un campo "error" (no una lista vacía) cuando Google
        # simplemente no tiene resultados para la búsqueda — no es una falla.
        if "hasn't returned any results" in data["error"].lower():
            return []
        raise ValueError(data["error"])
    return [
        {
            "titulo": r.get("title", ""),
            "link": r.get("link", ""),
            "snippet": r.get("snippet", ""),
        }
        for r in data.get("organic_results", [])
    ]


def _buscar_serpapi_seguro(query, api_key):
    """Como buscar_serpapi, pero una falla (ej. timeout tras el reintento) no
    tira una excepción — devuelve None para que el resto de las búsquedas de
    la empresa sigan corriendo en vez de perderse todas por una sola falla."""
    try:
        return buscar_serpapi(query, api_key)
    except Exception:
        return None


def _formatear_resultados(resultados):
    if resultados is None:
        return "(no se pudo buscar — error de conexión)"
    if not resultados:
        return "(sin resultados)"
    return "\n".join(f"- {r['titulo']}: {r['snippet']} ({r['link']})" for r in resultados)


@st.cache_data(ttl="24h", show_spinner=False)
def enriquecer_empresa(razon_social, actividad, ubicacion, serpapi_key, anthropic_key):
    # Sin comillas: la razón social del DENUE (nombre legal, ej. "DISTRIBUIDORA
    # LIVERPOOL") casi nunca coincide textualmente con el nombre comercial que
    # usa la empresa en LinkedIn/prensa (ej. "El Puerto de Liverpool") — forzar
    # coincidencia exacta hacía fallar la búsqueda casi siempre.
    resultados_linkedin = _buscar_serpapi_seguro(f"{razon_social} site:linkedin.com/company/", serpapi_key)
    resultados_empleo = _buscar_serpapi_seguro(
        f"{razon_social} México (empleados OR colaboradores OR vacantes)", serpapi_key
    )
    resultados_actividad = _buscar_serpapi_seguro(
        f'{razon_social} (cierre OR quiebra OR demanda OR expansión OR "nueva sucursal" OR contratando)',
        serpapi_key,
    )
    resultados_contacto = _buscar_serpapi_seguro(
        f'{razon_social} México ("recursos humanos" OR "director de compras" OR '
        '"gerente de compras" OR "talent acquisition") site:linkedin.com/in/',
        serpapi_key,
    )
    resultados_sitio = _buscar_serpapi_seguro(f"{razon_social} México sitio oficial", serpapi_key)

    contexto = (
        f"Empresa (según DENUE): {razon_social}\n"
        f"Actividad económica (DENUE): {actividad}\n"
        f"Ubicación (DENUE): {ubicacion}\n\n"
        f"Resultados de búsqueda 'LinkedIn':\n{_formatear_resultados(resultados_linkedin)}\n\n"
        f"Resultados de búsqueda 'empleo/vacantes':\n{_formatear_resultados(resultados_empleo)}\n\n"
        f"Resultados de búsqueda 'actividad/riesgo':\n{_formatear_resultados(resultados_actividad)}\n\n"
        f"Resultados de búsqueda 'contacto RRHH/compras':\n{_formatear_resultados(resultados_contacto)}\n\n"
        f"Resultados de búsqueda 'sitio oficial':\n{_formatear_resultados(resultados_sitio)}"
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
            "terceros (páginas amarillas, cámaras empresariales) ni redes sociales."
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
def buscar_contacto_por_rol(razon_social, terminos_rol, serpapi_key, anthropic_key):
    resultados = buscar_serpapi(
        f"{razon_social} México ({terminos_rol}) site:linkedin.com/in/", serpapi_key
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
