import json
import os
import re
from datetime import date
from typing import Optional
from urllib.parse import quote, urlparse

import anthropic
import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv
from pydantic import BaseModel, Field

from catalogos import ENTIDADES_FEDERATIVAS, ESTRATOS, SECTOR_TODOS, SECTORES_SCIAN

st.set_page_config(
    page_title="Explorador DENUE",
    page_icon=":material/storefront:",
    layout="wide",
)

load_dotenv()
API_KEY = os.getenv("DENUE_API_KEY")
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")

BASE_URL = "https://www.inegi.org.mx/app/api/denue/v1/consulta/BuscarAreaActEstr"
SERPAPI_URL = "https://serpapi.com/search.json"
HUNTER_URL = "https://api.hunter.io/v2"
MONDAY_URL = "https://api.monday.com/v2"
# Board "pruebaContacto" (workspace "Espacio de trabajo principal"), creado
# vía API con el esquema de contacto.md. IDs de columna reales de ese board —
# no son adivinados, se armó el board a propósito con este mapeo.
MONDAY_BOARD_CONTACTO = "18429143194"
MONDAY_COLUMNAS_CONTACTO = {
    "Cuenta asociada": "text_mm6s8x5b",
    "Correo": "email_mm6szmcn",
    "Teléfono (empresa)": "phone_mm6sxj79",
    "Extensión": "text_mm6svwq7",
    "País": "text_mm6s49m7",
    "Nivel de cargo": "color_mm6sksm5",
    "Nombre de cargo": "text_mm6shaw1",
    "Link de LinkedIn": "link_mm6syh0t",
    "Rol en la decisión": "color_mm6s277r",
    "Estado": "color_mm6swhpj",
    "Fecha de inicio": "date_mm6scfky",
    "Responsable": "multiple_person_mm6shxmf",
}
MODELO_ENRIQUECIMIENTO = "claude-haiku-4-5"
ENTIDAD_TODOS = "00"
ESTRATO_TODOS = "0"
TAMANO_PAGINA = 5000
# Prototipo: solo se enriquece(n) la(s) N empresa(s) de mayor personal estimado,
# para no consumir de más las búsquedas de SerpAPI/Anthropic — bajado a 1 para
# poder probar la opción "Todos los roles" (multiplica las búsquedas por
# empresa) sin que el costo se dispare mientras se sigue probando.
N_EMPRESAS_ENRIQUECER = 1

# Grupo B (sin correo en el DENUE): rol a buscar -> términos de búsqueda.
ROLES_CONTACTO = {
    "Recursos humanos": '"recursos humanos" OR "talent acquisition" OR reclutamiento',
    "Compras": '"director de compras" OR "gerente de compras" OR procurement',
    "Dirección general": '"director general" OR CEO OR "gerente general"',
    "Ventas": '"director comercial" OR "gerente de ventas" OR "director de ventas"',
}
# Sentinela del selector de rol: en vez de uno solo, busca los 4 roles de
# ROLES_CONTACTO para la misma empresa — multiplica las búsquedas por
# empresa, por eso conviene probarlo con N_EMPRESAS_ENRIQUECER bajo.
TODOS_LOS_ROLES = "Todos los roles"


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

# Columnas que más importan para explorar resultados; el resto de las
# columnas que devuelve la API (más técnicas) se muestran igual, al final.
COLUMNAS_PRIORITARIAS = [
    "Nombre",
    "Razon_social",
    "Clase_actividad",
    "Estrato",
    "Ubicacion",
    "Tipo_vialidad",
    "Calle",
    "Num_Exterior",
    "Colonia",
    "CP",
    "Telefono",
    "Correo_e",
    "Sitio_internet",
]

COLUMN_CONFIG = {
    "Nombre": st.column_config.TextColumn("Nombre", pinned=True),
    "Razon_social": st.column_config.TextColumn("Razón social"),
    "Clase_actividad": st.column_config.TextColumn("Actividad económica"),
    "Estrato": st.column_config.TextColumn("Estrato (personal ocupado)"),
    "Ubicacion": st.column_config.TextColumn("Localidad, municipio, estado"),
    "Telefono": st.column_config.TextColumn("Teléfono"),
    "Correo_e": st.column_config.TextColumn("Correo"),
    "Sitio_internet": st.column_config.LinkColumn("Sitio web"),
}


COLUMNAS_ENRIQUECIMIENTO = {
    "linkedin_url": "LinkedIn",
    "sitio_web": "Sitio web (SerpAPI)",
    "empleados_linkedin": "Empleados (LinkedIn/web)",
    "actividad_reciente": "Actividad reciente",
    "resumen_actividad": "Resumen actividad",
    "senales_riesgo": "Señal de riesgo",
    "resumen_riesgo": "Resumen riesgo",
    "contacto_rrhh": "Contacto RRHH",
    "contacto_rrhh_url": "LinkedIn del contacto",
    "confianza_coincidencia": "Confianza (coincide con la empresa)",
    "evidencia": "Evidencia",
}


def reordenar_columnas(df):
    prioritarias = [c for c in COLUMNAS_PRIORITARIAS if c in df.columns]
    resto = [c for c in df.columns if c not in prioritarias]
    return df[prioritarias + resto]


# Columnas finales para la etapa de "datos limpios": las que sirven para
# el flujo de contacto B2B, ya a nivel empresa (post agrupación).
COLUMNAS_LIMPIAS = {
    "Razon_social": "Razón social",
    "Nombre": "Nombre (sucursal representativa)",
    "Sucursales": "Sucursales en DENUE",
    "Personal_estimado": "Personal estimado",
    "Banda_total": "Banda de tamaño",
    "Correo_e": "Correo",
    "Telefono": "Teléfono",
    "Sitio_internet": "Sitio web",
    "Clase_actividad": "Actividad económica",
    "CLASE_ACTIVIDAD_ID": "Código SCIAN",
    "Ubicacion": "Localidad, municipio, estado",
    "Fecha_Alta": "Fecha de alta en DENUE",
    "Grupo_corporativo_probable": "Grupo corporativo probable",
}


def build_url(entidad, sector, estrato, nombre, regini, regfin, token):
    # "0" es el comodín de "todos" para Nombre en este endpoint (a diferencia
    # del endpoint simple /Buscar, que usa la palabra "todos").
    nombre_param = quote(nombre.strip()) if nombre.strip() else "0"
    return (
        f"{BASE_URL}/{entidad}/0/0/0/0/{sector}/0/0/0/"
        f"{nombre_param}/{regini}/{regfin}/0/{estrato}/{token}"
    )


@st.cache_data(ttl="15m", show_spinner=False)
def buscar_denue(entidad, sector, estrato, nombre, regini, regfin, token):
    url = build_url(entidad, sector, estrato, nombre, regini, regfin, token)
    response = requests.get(url, timeout=90)
    response.raise_for_status()
    data = response.json()
    if isinstance(data, dict):
        raise ValueError(data.get("Message", "La API devolvió un error."))
    df = pd.DataFrame(data)
    if not df.empty:
        df = reordenar_columnas(df)
    return df, url


def rango_estrato(etiqueta):
    """Convierte el texto de Estrato de la API (ej. '31 a 50 personas') en un
    rango (mínimo, máximo) de personal para esa sucursal. Máximo None = sin
    techo (banda '251 y más')."""
    if not isinstance(etiqueta, str):
        return (0, 0)
    for base in ESTRATOS.values():
        if etiqueta.startswith(base):
            if " a " in base:
                minimo, maximo = base.split(" a ")
                return (int(minimo), int(maximo))
            return (int(base.split(" ")[0]), None)  # "251 y más"
    return (0, 0)


BANDAS_TOTALES = [
    (1000, "1000 y más"),
    (250, "250 a 999"),
    (50, "50 a 249"),
    (0, "Hasta 49"),
]


def banda_total(personal_min):
    for umbral, etiqueta in BANDAS_TOTALES:
        if personal_min >= umbral:
            return etiqueta
    return BANDAS_TOTALES[-1][1]


def primero_no_vacio(serie):
    valores = serie.astype(str).str.strip()
    no_vacios = valores[(valores != "") & (valores.str.lower() != "nan")]
    return no_vacios.iloc[0] if not no_vacios.empty else ""


def clave_empresa(fila):
    """Agrupa por Razón social (identidad legal); si no existe (personas
    físicas, que el DENUE no expone por confidencialidad) cada sucursal queda
    como su propia empresa, para no mezclar negocios distintos con nombre
    genérico compartido (ej. varios locales llamados 'ABARROTES')."""
    razon_social = str(fila.get("Razon_social", "")).strip()
    if razon_social and razon_social.lower() != "nan":
        return razon_social
    return f"__individual__{fila.get('Id')}"


@st.cache_data(show_spinner=False)
def agrupar_por_empresa(df):
    """Agrupa sucursales del DENUE por empresa y estima su personal total
    sumando los rangos de estrato de cada sucursal.

    Cacheada: sin esto, al no estar decorada, Streamlit la recalculaba desde
    cero en CADA rerun de la app entera (por ejemplo, al clickear un botón
    en la pestaña Monday) — con un DENUE grande (miles de sucursales, sin
    tope) eso se sentía como lentitud generalizada en cualquier interacción,
    no solo en la pestaña de Búsqueda/Datos limpios."""
    rangos = df["Estrato"].apply(rango_estrato)
    df = df.assign(
        _estrato_min=[r[0] for r in rangos],
        _estrato_max=[r[1] for r in rangos],
        _empresa=df.apply(clave_empresa, axis=1),
    )

    filas = []
    for _empresa, sub in df.groupby("_empresa"):
        personal_min = int(sub["_estrato_min"].sum())
        sin_techo = sub["_estrato_max"].isna().any()
        personal_max = None if sin_techo else int(sub["_estrato_max"].sum())
        razon_social = sub.iloc[0]["Razon_social"]
        razon_social = razon_social if str(razon_social).strip() else primero_no_vacio(sub["Nombre"])
        filas.append(
            {
                "Razon_social": razon_social,
                "Nombre": primero_no_vacio(sub["Nombre"]),
                "Sucursales": len(sub),
                "Personal_min": personal_min,
                "Personal_max": personal_max,
                "Personal_estimado": f"{personal_min}+" if sin_techo else f"{personal_min}–{personal_max}",
                "Personal_punto_medio": None if sin_techo else round((personal_min + personal_max) / 2),
                "Banda_total": banda_total(personal_min),
                "Correo_e": primero_no_vacio(sub["Correo_e"]),
                "Telefono": primero_no_vacio(sub["Telefono"]),
                "Sitio_internet": primero_no_vacio(sub["Sitio_internet"]),
                "Clase_actividad": primero_no_vacio(sub["Clase_actividad"]),
                "CLASE_ACTIVIDAD_ID": primero_no_vacio(sub["CLASE_ACTIVIDAD_ID"]),
                "Ubicacion": primero_no_vacio(sub["Ubicacion"]),
                "Fecha_Alta": primero_no_vacio(sub["Fecha_Alta"]),
            }
        )
    columnas = [
        "Razon_social", "Nombre", "Sucursales", "Personal_estimado", "Personal_punto_medio", "Banda_total",
        "Correo_e", "Telefono", "Sitio_internet", "Clase_actividad", "CLASE_ACTIVIDAD_ID",
        "Ubicacion", "Fecha_Alta", "Personal_min", "Personal_max",
    ]
    return pd.DataFrame(filas, columns=columnas)


def dominio_de_empresa(correo, sitio_web):
    """Dominio de correo/sitio de una empresa, preferentemente del sitio web
    (más confiable que un correo suelto). None si no hay ninguno de los dos."""
    if sitio_web and str(sitio_web).strip():
        dominio = extraer_dominio(sitio_web)
        if dominio:
            return dominio.lower()
    if correo and "@" in str(correo):
        return str(correo).rsplit("@", 1)[-1].strip().lower()
    return None


# Local-parts típicos de un buzón institucional/funcional (no una persona) —
# buscar un contacto por rol para uno de estos correos vuelve vacío siempre,
# porque no hay una persona detrás, sino un área (ej. archivogeneral@dgsg.unam.mx).
LOCAL_PARTS_CORREO_GENERAL = {
    "info", "contacto", "ventas", "atencion", "atencionaclientes", "general",
    "archivo", "archivogeneral", "admin", "administracion", "recepcion",
    "soporte", "ayuda", "servicios", "tramites", "notificaciones",
    "correspondencia", "buzon", "informacion", "rrhh", "recursoshumanos",
}


def es_correo_general(correo):
    """True si la parte local del correo (antes del @) es un buzón funcional
    típico (info@, contacto@, archivogeneral@...) y no una persona."""
    if not correo or "@" not in str(correo):
        return False
    local = re.sub(r"[^a-z]", "", str(correo).split("@", 1)[0].lower())
    return any(clave in local for clave in LOCAL_PARTS_CORREO_GENERAL)


# Clasificación de "Nombre de cargo" (texto libre) a los 4 niveles fijos del
# board de Contacto en Monday — orden de mayor a menor jerarquía, la primera
# clave que matchea gana (evita que "director" pise a "ceo" o viceversa).
NIVELES_CARGO = [
    ("CEO, Presidente y/o similares",
     ["ceo", "cfo", "coo", "cto", "chief", "president", "presidente", "fundador", "founder", "dueño", "dueno"]),
    ("Director, Gerente, Jefe, Líder y/o similares",
     ["director", "gerente", "jefe", "lider", "líder", "manager", "head of"]),
    ("Coordinador y/o supervisor",
     ["coordinador", "supervisor", "coordinator"]),
    ("Auxiliar, Asistente, Operador ejecutivo Jr. y/o similares",
     ["auxiliar", "asistente", "assistant", "jr", "junior", "becario", "practicante", "trainee", "operador"]),
]


def nivel_de_cargo(cargo_texto):
    """Mapea un cargo en texto libre (ej. 'Gerente de Recursos Humanos') a uno
    de los 4 niveles fijos del board de Monday. Matchea por PALABRA COMPLETA
    (\\b), no substring: con substring simple, "director" caía en el nivel de
    CEO porque la palabra contiene literalmente "cto" (dire-CTO-r). None si no
    matchea ninguno — es una heurística por palabras clave, no un dato certero."""
    if not cargo_texto:
        return None
    texto = str(cargo_texto).lower()
    for nivel, claves in NIVELES_CARGO:
        if any(re.search(rf"\b{re.escape(clave)}\b", texto) for clave in claves):
            return nivel
    return None


# Columnas del board de Contacto en Monday (ver contacto.md), en su orden.
COLUMNAS_CONTACTO_MONDAY = [
    "Cuenta asociada", "Nombre", "Correo", "Teléfono (empresa)", "Extensión", "País",
    "Nivel de cargo", "Nombre de cargo", "Link de LinkedIn", "Rol en la decisión",
    "Estado", "Responsable", "Fecha de inicio",
]
# Columnas propias, fuera del esquema de Monday — quedan al final del CSV como
# contexto para decidir cuál candidato usar antes de importar (score, de dónde
# salió, si es el principal de la empresa o una alternativa).
COLUMNAS_CONTACTO_INTERNAS = [
    "Es principal", "Estado del correo", "Score del correo", "Confianza del correo",
    "Fuente", "Fuentes del correo",
]
# Marcado manual en el panel de gestión — no se envía a Monday tal cual, pilotea
# si/cómo se exporta cada fila.
COLUMNAS_CONTACTO_GESTION = ["Contactado", "No existe / desvinculado", "Exportado a Monday"]


def _valor_valido(valor):
    """False para None, NaN de pandas o string vacío. Hace falta porque
    bool(float('nan')) es True en Python puro — un 'if fila.get(x):' no
    alcanza para filtrar los None que pandas convierte a NaN al armar un
    DataFrame desde una lista de dicts (columna mixta string/None)."""
    if valor is None:
        return False
    try:
        if pd.isna(valor):
            return False
    except (TypeError, ValueError):
        pass
    return str(valor).strip() != ""


def _texto(valor, default="—"):
    return str(valor) if _valor_valido(valor) else default


def fila_contacto(
    razon_social, nombre, correo, telefono_empresa, cargo, linkedin, es_principal,
    estado_correo=None, score_correo=None, confianza_correo=None, fuente=None, sources=None,
):
    """Arma una fila de contacto con el esquema del board de Monday (ver
    contacto.md) + columnas propias de diagnóstico al final."""
    return {
        "Cuenta asociada": razon_social,
        "Nombre": nombre,
        "Correo": correo,
        "Teléfono (empresa)": telefono_empresa,
        "Extensión": None,
        "País": "México",
        "Nivel de cargo": nivel_de_cargo(cargo),
        "Nombre de cargo": cargo,
        "Link de LinkedIn": linkedin,
        "Rol en la decisión": None,
        "Estado": None,
        "Responsable": None,
        "Fecha de inicio": date.today().isoformat(),
        "Es principal": es_principal,
        "Estado del correo": estado_correo,
        "Score del correo": score_correo,
        "Confianza del correo": confianza_correo,
        "Fuente": fuente,
        "Fuentes del correo": sources,
    }


@st.cache_data(show_spinner=False)
def marcar_grupo_corporativo(df_grupos):
    """Marca empresas (razones sociales distintas) que comparten dominio de
    correo/sitio con otra empresa del mismo resultado — señal de que podrían
    pertenecer al mismo grupo corporativo operando marcas distintas (ver caso
    OPERADORA EXE / OPERADORA DE FRANQUICIAS AGN, ambas de Grupo Nicxa)."""
    dominios = df_grupos.apply(
        lambda r: dominio_de_empresa(r["Correo_e"], r["Sitio_internet"]), axis=1
    )
    conteo = dominios.value_counts()
    df_grupos = df_grupos.copy()
    df_grupos["Grupo_corporativo_probable"] = [
        f"Sí — comparte dominio ({d}) con otra(s) empresa(s) de este resultado"
        if d and conteo.get(d, 0) > 1
        else "No"
        for d in dominios
    ]
    return df_grupos


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


def extraer_dominio(url):
    if not url or not str(url).strip():
        return None
    url = str(url).strip()
    if "://" not in url:
        url = f"http://{url}"
    dominio = urlparse(url).netloc.lower().replace("www.", "")
    return dominio or None


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


@st.cache_data(ttl="24h", show_spinner=False)
def sitio_web_valido(url):
    """Chequeo directo de que una URL responde (a diferencia de
    verificar_dominio_legitimo, que solo mira si Google indexa algo del
    dominio). Un sitio del DENUE puede estar desactualizado y ya no existir."""
    if not url or not str(url).strip():
        return False
    url_completa = str(url).strip()
    if "://" not in url_completa:
        url_completa = f"http://{url_completa}"
    try:
        respuesta = requests.head(url_completa, timeout=8, allow_redirects=True)
        if respuesta.status_code >= 400:
            respuesta = requests.get(url_completa, timeout=8, allow_redirects=True)
        return respuesta.status_code < 400
    except requests.RequestException:
        return False


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


def monday_graphql(query, variables=None):
    """POST genérico a la API de Monday. Levanta ValueError con el mensaje
    real de Monday si la respuesta trae 'errors' (no es un HTTP 4xx/5xx —
    Monday devuelve 200 con errores adentro del body)."""
    response = requests.post(
        MONDAY_URL,
        headers={"Authorization": MONDAY_API_KEY, "Content-Type": "application/json"},
        json={"query": query, "variables": variables or {}},
        timeout=30,
    )
    response.raise_for_status()
    data = response.json()
    if "errors" in data:
        raise ValueError(f"Monday: {data['errors']}")
    return data["data"]


def monday_correo_existe(correo):
    """True si ya hay un item en el board de Contacto con ese correo — evita
    duplicar en exports repetidos (contacto.md pide deduplicar por correo)."""
    if not correo:
        return False
    query = """
    query ($boardId: ID!, $correo: String!) {
      boards(ids: [$boardId]) {
        items_page(query_params: {rules: [{
          column_id: "%s", compare_value: [$correo], operator: any_of
        }]}) { items { id } }
      }
    }
    """ % MONDAY_COLUMNAS_CONTACTO["Correo"]
    data = monday_graphql(query, {"boardId": MONDAY_BOARD_CONTACTO, "correo": correo})
    return len(data["boards"][0]["items_page"]["items"]) > 0


@st.cache_data(show_spinner="Consultando empresas ya cargadas en Monday...")
def monday_listar_cuentas():
    """Nombres normalizados (strip + lower) de 'Cuenta asociada' de TODOS los
    items del board de Contacto — para descartar en Etapa 3 las empresas que
    ya tienen al menos un contacto cargado en Monday. Cacheada: paginar todo
    el board en cada rerun de Streamlit sería lento; se refresca a mano con
    el botón "Actualizar cartera de Monday" (ver tab_limpios)."""
    columna_id = MONDAY_COLUMNAS_CONTACTO["Cuenta asociada"]
    cuentas = set()

    def _sumar(items):
        for item in items:
            texto = item["column_values"][0]["text"]
            if texto and texto.strip():
                cuentas.add(texto.strip().lower())

    query_inicial = """
    query ($boardId: ID!, $columnaId: [String!]) {
      boards(ids: [$boardId]) {
        items_page(limit: 100) {
          cursor
          items { column_values(ids: $columnaId) { text } }
        }
      }
    }
    """
    data = monday_graphql(query_inicial, {"boardId": MONDAY_BOARD_CONTACTO, "columnaId": [columna_id]})
    pagina = data["boards"][0]["items_page"]
    cursor = pagina["cursor"]
    _sumar(pagina["items"])

    query_siguiente = """
    query ($cursor: String!, $columnaId: [String!]) {
      next_items_page(cursor: $cursor, limit: 100) {
        cursor
        items { column_values(ids: $columnaId) { text } }
      }
    }
    """
    while cursor:
        data = monday_graphql(query_siguiente, {"cursor": cursor, "columnaId": [columna_id]})
        pagina = data["next_items_page"]
        cursor = pagina["cursor"]
        _sumar(pagina["items"])

    return cuentas


def _telefono_mx(telefono):
    """Normaliza un teléfono del DENUE (10 dígitos, sin código de país) al
    formato E.164 que pide la columna 'phone' de Monday. None si no hay
    suficientes dígitos para ser un teléfono real."""
    digitos = re.sub(r"\D", "", str(telefono or ""))
    if not digitos:
        return None
    if not digitos.startswith("52"):
        digitos = f"52{digitos}"
    return f"+{digitos}" if len(digitos) >= 12 else None


def _gmail_compose_url(correo):
    """Link que abre el compositor de Gmail en el navegador con el
    destinatario ya cargado — en vez de 'mailto:', que abre lo que sea el
    cliente de correo default del sistema (ej. Outlook)."""
    return f"https://mail.google.com/mail/?view=cm&fs=1&to={quote(correo)}"


@st.cache_data(ttl="1h", show_spinner=False)
def monday_listar_usuarios():
    """Usuarios reales del workspace de Monday — {nombre: id}. El campo
    'Responsable' es una columna 'people', que en la API de Monday necesita
    el ID real de un usuario, no texto libre; por eso el selector se arma
    con esta lista en vez de dejar escribir cualquier nombre."""
    try:
        data = monday_graphql("{ users { id name } }")
        return {u["name"]: u["id"] for u in data["users"]}
    except Exception:
        return {}


def monday_crear_contacto(fila, responsable_id=None):
    """Crea un item en el board de Contacto a partir de una fila con el
    esquema de COLUMNAS_CONTACTO_MONDAY. 'Estado' queda en 'Contactado' —
    se llama a esta función solo al exportar un contacto ya contactado.
    'responsable_id' es el ID real de un usuario de Monday (ver
    monday_listar_usuarios), no un nombre — se omite si no se pasa."""
    columnas = dict(MONDAY_COLUMNAS_CONTACTO)
    valores = {columnas["Cuenta asociada"]: _texto(fila.get("Cuenta asociada"), "")}

    correo = fila.get("Correo")
    correo_valido = _valor_valido(correo)
    if correo_valido:
        valores[columnas["Correo"]] = {"email": correo, "text": correo}

    telefono = _telefono_mx(fila.get("Teléfono (empresa)"))
    if telefono:
        valores[columnas["Teléfono (empresa)"]] = {"phone": telefono, "countryShortName": "MX"}

    if _valor_valido(fila.get("País")):
        valores[columnas["País"]] = str(fila["País"])

    # Sin nombre de cargo (correo institucional, o nadie identificado): se
    # deja una etiqueta que diga por qué, en vez de un campo vacío o "nan".
    cargo = fila.get("Nombre de cargo")
    if _valor_valido(cargo):
        valores[columnas["Nombre de cargo"]] = str(cargo)
    else:
        fuente = str(fila.get("Fuente") or "").lower()
        valores[columnas["Nombre de cargo"]] = (
            "Correo general / institucional" if "general" in fuente else "Contacto no identificado"
        )

    if _valor_valido(fila.get("Nivel de cargo")):
        valores[columnas["Nivel de cargo"]] = {"label": fila["Nivel de cargo"]}
    if _valor_valido(fila.get("Link de LinkedIn")):
        valores[columnas["Link de LinkedIn"]] = {"url": fila["Link de LinkedIn"], "text": "LinkedIn"}
    if _valor_valido(fila.get("Fecha de inicio")):
        valores[columnas["Fecha de inicio"]] = {"date": fila["Fecha de inicio"]}
    if responsable_id:
        valores[columnas["Responsable"]] = {
            "personsAndTeams": [{"id": int(responsable_id), "kind": "person"}]
        }
    valores[columnas["Estado"]] = {"label": "Contactado"}

    mutation = """
    mutation ($boardId: ID!, $itemName: String!, $columnValues: JSON!) {
      create_item(
        board_id: $boardId, item_name: $itemName, column_values: $columnValues,
        create_labels_if_missing: true
      ) { id }
    }
    """
    nombre = fila.get("Nombre")
    if _valor_valido(nombre):
        nombre_item = str(nombre)
    elif correo_valido:
        nombre_item = correo
    else:
        nombre_item = "Contacto sin nombre"
    item_name = nombre_item
    data = monday_graphql(mutation, {
        "boardId": MONDAY_BOARD_CONTACTO,
        "itemName": item_name,
        "columnValues": json.dumps(valores),
    })
    return data["create_item"]["id"]


@st.dialog("Confirmar exportación a Monday")
def dialog_exportar_monday(idx, etiqueta, cuenta, responsable_id):
    st.write(f"¿Seguro que querés exportar a **{etiqueta}** ({cuenta}) a Monday?")
    col_si, col_no = st.columns(2)
    with col_si:
        if st.button("Sí, exportar", key=f"dialog_si_{idx}", type="primary"):
            fila = st.session_state["df_contactos"].loc[idx]
            try:
                if _valor_valido(fila["Correo"]) and monday_correo_existe(fila["Correo"]):
                    st.session_state["_monday_aviso"] = (
                        "warning", f"{etiqueta} ya existe en Monday (mismo correo) — no se duplica."
                    )
                else:
                    monday_crear_contacto(fila, responsable_id=responsable_id)
                    st.session_state["_monday_aviso"] = ("success", f"{etiqueta} exportado correctamente.")
                st.session_state["df_contactos"].loc[idx, "Exportado a Monday"] = True
            except Exception as exc:
                st.session_state["_monday_aviso"] = ("error", f"{etiqueta} — error al exportar: {exc}")
            st.rerun()
    with col_no:
        if st.button("Cancelar", key=f"dialog_no_{idx}"):
            st.rerun()


def _renderizar_tarjeta_contacto(idx, fila, usuarios_monday):
    """Una tarjeta por contacto. El contenido de abajo (gestión vs. resumen
    de solo lectura) depende de si ya se exportó o se marcó como inexistente
    — separa las 3 categorías de la pestaña Monday en un solo lugar."""
    etiqueta = _texto(fila["Nombre"], "Contacto sin nombre")
    exportado = bool(fila["Exportado a Monday"])
    marcado_no_existe = bool(fila["No existe / desvinculado"])

    with st.container(border=True):
        col_info, col_correo, col_linkedin = st.columns([2.6, 1.2, 1.2])
        with col_info:
            st.markdown(f"#### {etiqueta}")
            subtitulo = " · ".join(
                t for t in (
                    _texto(fila["Cuenta asociada"], ""),
                    _texto(fila["Nivel de cargo"], ""),
                    _texto(fila["Nombre de cargo"], ""),
                ) if t
            )
            if subtitulo:
                st.caption(subtitulo)
            if _valor_valido(fila["Correo"]):
                st.caption(fila["Correo"])
        with col_correo:
            if _valor_valido(fila["Correo"]):
                st.link_button(
                    "Enviar correo", _gmail_compose_url(fila["Correo"]),
                    icon=":material/mail:", use_container_width=True,
                )
            else:
                st.caption("Sin correo")
        with col_linkedin:
            if _valor_valido(fila["Link de LinkedIn"]):
                st.link_button(
                    "Ver LinkedIn", fila["Link de LinkedIn"],
                    icon=":material/open_in_new:", use_container_width=True,
                )
            else:
                st.caption("Sin LinkedIn")

        st.divider()

        if exportado:
            st.success("Ya exportado a Monday", icon=":material/check_circle:")
        elif marcado_no_existe:
            st.caption("Marcado como no existente / desvinculado — no se exporta.")
            if st.button("Reactivar", key=f"reactivar_{idx}", icon=":material/restart_alt:"):
                st.session_state["df_contactos"].loc[idx, "No existe / desvinculado"] = False
                st.rerun()
        else:
            col_resp, col_contactado, col_no_existe, col_exportar = st.columns([2, 1.3, 1.8, 1.8])
            with col_resp:
                responsable_nombre = st.selectbox(
                    "Responsable", options=[""] + list(usuarios_monday.keys()), key=f"responsable_{idx}",
                )
            with col_contactado:
                contactado = st.checkbox(
                    "Contactado", value=bool(fila["Contactado"]), key=f"contactado_{idx}"
                )
            with col_no_existe:
                marcar_no_existe = st.checkbox(
                    "No existe / desvinculado", value=False, key=f"no_existe_{idx}"
                )
            st.session_state["df_contactos"].loc[idx, "Contactado"] = contactado
            st.session_state["df_contactos"].loc[idx, "No existe / desvinculado"] = marcar_no_existe
            with col_exportar:
                st.write("")
                if st.button(
                    "Exportar a Monday", key=f"exportar_{idx}",
                    disabled=(not contactado) or marcar_no_existe,
                    icon=":material/cloud_upload:", use_container_width=True,
                ):
                    dialog_exportar_monday(
                        idx, etiqueta, fila["Cuenta asociada"], usuarios_monday.get(responsable_nombre)
                    )


st.title("Explorador DENUE")
st.caption("Consulta y filtra el Directorio Estadístico Nacional de Unidades Económicas (INEGI).")

if not API_KEY:
    st.error("No se encontró DENUE_API_KEY en el archivo .env.")
    st.stop()

with st.sidebar:
    st.header("Filtros")
    with st.form("filtros_form"):
        sector_options = [SECTOR_TODOS] + list(SECTORES_SCIAN.keys())
        sector_labels = {SECTOR_TODOS: "Todos los sectores", **SECTORES_SCIAN}
        sector = st.selectbox(
            "Sector económico (SCIAN)",
            options=sector_options,
            format_func=lambda code: f"{code} — {sector_labels[code]}" if code != SECTOR_TODOS else sector_labels[code],
        )

        entidad_options = [ENTIDAD_TODOS] + list(ENTIDADES_FEDERATIVAS.keys())
        entidad_labels = {ENTIDAD_TODOS: "Todo el país", **ENTIDADES_FEDERATIVAS}
        entidad = st.selectbox(
            "Estado",
            options=entidad_options,
            format_func=lambda code: entidad_labels[code],
        )

        nombre = st.text_input(
            "Palabra clave (nombre del negocio)",
            placeholder="Vacío = todos",
        )

        st.caption(
            "Trae todos los registros disponibles para el sector/estado elegido "
            "(sin tope), en páginas de 5,000. Puede tardar si el universo es grande."
        )

        buscar = st.form_submit_button("Buscar", icon=":material/search:")

if buscar:
    st.session_state["ultima_busqueda"] = {
        "entidad": entidad,
        "sector": sector,
        "nombre": nombre,
    }

busqueda = st.session_state.get("ultima_busqueda")

if not busqueda:
    st.info("Configurá los filtros en la barra lateral y presioná **Buscar**.")
    st.stop()

try:
    dfs_paginas = []
    regini = 1
    pagina = 1
    ultima_url = None
    corte_anormal = False
    with st.status("Descargando registros del DENUE...", expanded=True) as status:
        while True:
            regfin = regini + TAMANO_PAGINA - 1
            status.update(label=f"Página {pagina} — registros {regini} a {regfin}...")
            try:
                df_pagina, ultima_url = buscar_denue(
                    busqueda["entidad"],
                    busqueda["sector"],
                    ESTRATO_TODOS,
                    busqueda["nombre"],
                    regini,
                    regfin,
                    API_KEY,
                )
            except requests.exceptions.RequestException:
                # La API del DENUE responde con un HTTP corrupto (en vez de una
                # lista vacía) cuando se piden páginas más allá del último
                # registro disponible. Si ya trajimos algo, lo tratamos como
                # fin de los datos en vez de descartar todo lo acumulado.
                if dfs_paginas:
                    corte_anormal = True
                    break
                raise
            if df_pagina.empty:
                break
            dfs_paginas.append(df_pagina)
            total_hasta_ahora = sum(len(p) for p in dfs_paginas)
            st.write(f"Página {pagina}: {len(df_pagina)} registros (acumulado: {total_hasta_ahora})")
            if len(df_pagina) < TAMANO_PAGINA:
                break
            regini += TAMANO_PAGINA
            pagina += 1
        total_final = sum(len(p) for p in dfs_paginas)
        if corte_anormal:
            status.update(
                label=f"Listo — {total_final} registros (corte al final de los disponibles)",
                state="complete",
            )
        else:
            status.update(label=f"Listo — {total_final} registros en total", state="complete")
    df = pd.concat(dfs_paginas, ignore_index=True) if dfs_paginas else pd.DataFrame()
    url_usada = ultima_url
except requests.exceptions.RequestException as exc:
    st.error(f"Error de conexión con la API del DENUE: {exc}")
    st.stop()
except ValueError as exc:
    st.error(f"La API respondió con un error: {exc}")
    st.stop()

if df.empty:
    st.warning("La búsqueda no arrojó resultados. Probá con otros filtros.")
    st.stop()

tab_busqueda, tab_limpios, tab_enriquecimiento, tab_monday = st.tabs(
    ["Búsqueda", "Datos limpios", "Enriquecimiento", "Monday"]
)

with tab_busqueda:
    st.metric("Establecimientos encontrados", len(df), border=True)

    st.dataframe(df, column_config=COLUMN_CONFIG, hide_index=True)

    st.download_button(
        "Descargar CSV",
        data=df.to_csv(index=False).encode("utf-8-sig"),
        file_name="denue_resultados.csv",
        mime="text/csv",
        icon=":material/download:",
    )

    with st.expander("Detalles de la consulta"):
        token_oculto = API_KEY[:4] + "…" + API_KEY[-4:]
        st.code(url_usada.replace(API_KEY, token_oculto), language="text")

with tab_limpios:
    st.caption(
        "Vas angostando los resultados en etapas para ver qué se descarta en cada una "
        "y qué queda como dato útil para el flujo de contacto B2B."
    )

    df_etapa1 = df.copy()

    with st.container(border=True):
        st.markdown("**Etapa 1 — Datos extraídos**")
        st.caption("Todas las sucursales encontradas, sin agrupar todavía.")

    # Agrupación por empresa: se calcula de fondo (el DENUE mide personal por
    # sucursal, no por empresa) pero no se muestra como paso — ver Etapa 2.
    df_etapa2 = agrupar_por_empresa(df_etapa1).sort_values("Personal_min", ascending=False)
    df_etapa2 = marcar_grupo_corporativo(df_etapa2)

    with st.container(border=True):
        st.markdown("**Etapa 2 — Filtro por cantidad mínima de empleados**")
        st.caption(
            "Sobre el personal total por empresa (sumando todas sus sucursales), "
            "ordenado de mayor a menor cantidad de empleados estimados."
        )
        minimo_empleados = st.number_input(
            "Cantidad mínima de empleados estimados",
            min_value=0,
            value=0,
            step=10,
            key="minimo_empleados",
        )
        df_etapa3 = df_etapa2[df_etapa2["Personal_min"] >= minimo_empleados]
        st.caption("Hacé click en una empresa para ver sus sucursales agrupadas.")
        evento_etapa2 = st.dataframe(
            df_etapa3[["Razon_social", "Sucursales", "Personal_estimado", "Banda_total"]],
            hide_index=True,
            on_select="rerun",
            selection_mode="single-row",
            key="tabla_etapa2",
        )
        filas_seleccionadas = evento_etapa2.selection.rows
        if filas_seleccionadas:
            empresa_seleccionada = df_etapa3.iloc[filas_seleccionadas[0]]
            razon_social_normalizada = str(empresa_seleccionada["Razon_social"]).strip()
            sucursales = df_etapa1[
                df_etapa1["Razon_social"].astype(str).str.strip() == razon_social_normalizada
            ]
            with st.expander(f"Sucursales de {empresa_seleccionada['Razon_social']}", expanded=True):
                st.dataframe(
                    sucursales[["Nombre", "Ubicacion", "Estrato", "Telefono", "Correo_e"]],
                    hide_index=True,
                )

    with st.container(border=True):
        st.markdown("**Etapa 3 — Descarte de duplicados contra Monday**")
        if not MONDAY_API_KEY:
            st.warning("Falta MONDAY_API_KEY en el .env para comparar contra Monday.")
            df_etapa4 = df_etapa3
        else:
            if st.button("Actualizar cartera de Monday", icon=":material/refresh:"):
                monday_listar_cuentas.clear()
            try:
                cuentas_monday = monday_listar_cuentas()
                st.caption(f"{len(cuentas_monday)} empresa(s) ya cargadas en Monday (board de Contacto).")
                coincide_monday = (
                    df_etapa3["Razon_social"].astype(str).str.strip().str.lower().isin(cuentas_monday)
                )
                df_etapa4 = df_etapa3[~coincide_monday]
                descartadas_monday = df_etapa3[coincide_monday]
                if not descartadas_monday.empty:
                    with st.expander(f"Ver {len(descartadas_monday)} empresa(s) descartadas por Monday"):
                        st.dataframe(
                            descartadas_monday[["Razon_social", "Sucursales", "Personal_estimado", "Banda_total"]],
                            hide_index=True,
                        )
            except Exception as exc:
                st.error(f"No se pudo consultar Monday: {exc}")
                df_etapa4 = df_etapa3

    df_final_cols = [c for c in COLUMNAS_LIMPIAS if c in df_etapa4.columns]
    df_final = df_etapa4[df_final_cols].rename(columns=COLUMNAS_LIMPIAS)

    with st.container(horizontal=True):
        st.metric("Extraído (sucursales)", len(df_etapa1), border=True)
        st.metric("Agrupado (empresas)", len(df_etapa2), border=True)
        st.metric(
            "Tras filtro empleados",
            len(df_etapa3),
            delta=f"-{len(df_etapa2) - len(df_etapa3)}",
            delta_color="off",
            border=True,
        )
        st.metric(
            "Tras dedup",
            len(df_etapa4),
            delta=f"-{len(df_etapa3) - len(df_etapa4)}",
            delta_color="off",
            border=True,
        )
        st.metric("Final limpio", len(df_final), border=True)

    with st.container(border=True):
        st.markdown("**Etapa 4 — Datos limpios finales**")
        if df_final.empty:
            st.warning("No quedaron empresas después de los filtros anteriores.")
        else:
            st.dataframe(df_final, hide_index=True)
            st.download_button(
                "Descargar datos limpios (CSV)",
                data=df_final.to_csv(index=False).encode("utf-8-sig"),
                file_name="denue_limpio.csv",
                mime="text/csv",
                icon=":material/download:",
            )

with tab_enriquecimiento:
    _texto_cantidad = (
        "solo la empresa con más personal estimado"
        if N_EMPRESAS_ENRIQUECER == 1
        else f"solo las primeras {N_EMPRESAS_ENRIQUECER} empresas de más personal estimado"
    )
    st.caption(
        f"Prototipo: busca y analiza {_texto_cantidad} de \"Datos limpios\", para no "
        "consumir de más las búsquedas de SerpAPI/Anthropic."
    )
    st.caption(
        "**Personal estimado (DENUE)** vs. **Empleados (LinkedIn/web)** miden cosas distintas: "
        "el del DENUE es la presencia física detectada en el sector/estado que buscaste (y "
        "subestima cuando hay sucursales en la banda abierta '251 y más'); el de LinkedIn es lo "
        "que la empresa reporta a nivel global, autoreportado y sin auditar. No uses uno para "
        "reemplazar al otro — mostralos juntos y priorizá con criterio."
    )

    if not SERPAPI_KEY or not ANTHROPIC_API_KEY:
        st.warning("Faltan SERPAPI_KEY y/o ANTHROPIC_API_KEY en el .env para usar esta pestaña.")
    elif df_etapa4.empty:
        st.info("No hay empresas en 'Datos limpios' para enriquecer todavía.")
    else:
        candidatas = df_etapa4.head(N_EMPRESAS_ENRIQUECER)

        st.caption(
            "Campos que se van a completar con la búsqueda: "
            + ", ".join(COLUMNAS_ENRIQUECIMIENTO.values()) + "."
        )
        st.markdown("**Datos actuales antes de enriquecer**")
        st.dataframe(df_final.head(N_EMPRESAS_ENRIQUECER), hide_index=True)

        if st.button("Enriquecer estas empresas", icon=":material/travel_explore:"):
            resultados = []
            with st.status("Enriqueciendo empresas...", expanded=True) as status:
                for i, fila in enumerate(candidatas.itertuples(), start=1):
                    status.update(label=f"Empresa {i} de {len(candidatas)} — {fila.Razon_social}...")
                    try:
                        resultado = enriquecer_empresa(
                            fila.Razon_social,
                            fila.Clase_actividad,
                            fila.Ubicacion,
                            SERPAPI_KEY,
                            ANTHROPIC_API_KEY,
                        )
                        resultados.append(resultado.model_dump())
                        st.write(f"✓ {fila.Razon_social} — coincidencia {resultado.confianza_coincidencia}")
                    except Exception as exc:
                        resultados.append(None)
                        st.write(f"✗ {fila.Razon_social} — error: {exc}")
                status.update(label="Enriquecimiento completo", state="complete")

            filas_validas = [(idx, r) for idx, r in enumerate(resultados) if r is not None]
            if filas_validas:
                indices, datos = zip(*filas_validas)
                base = df_final.head(len(candidatas)).iloc[list(indices)].reset_index(drop=True)
                enriquecido = pd.DataFrame(list(datos)).rename(columns=COLUMNAS_ENRIQUECIMIENTO)
                df_combinado = pd.concat([base, enriquecido], axis=1)

                # El sitio del DENUE puede estar vacío o desactualizado (dominio que ya
                # no responde). Si no pasa el chequeo directo, se trata como si no
                # existiera y se completa con el que encontró la búsqueda de SerpAPI.
                sitios_finales, fuentes_sitio = [], []
                for _, fila_sitio in df_combinado.iterrows():
                    sitio_denue = str(fila_sitio.get("Sitio web") or "").strip()
                    sitio_serpapi = str(fila_sitio.get("Sitio web (SerpAPI)") or "").strip()
                    if sitio_denue and sitio_web_valido(sitio_denue):
                        sitios_finales.append(sitio_denue)
                        fuentes_sitio.append("DENUE")
                    elif sitio_serpapi:
                        sitios_finales.append(sitio_serpapi)
                        fuentes_sitio.append(
                            "SerpAPI (DENUE vacío)" if not sitio_denue else "SerpAPI (el del DENUE no responde)"
                        )
                    else:
                        sitios_finales.append("")
                        fuentes_sitio.append("Sin sitio verificado")
                df_combinado["Sitio web"] = sitios_finales
                df_combinado["Fuente sitio web"] = fuentes_sitio

                st.session_state["df_enriquecido"] = df_combinado

        if "df_enriquecido" in st.session_state:
            st.dataframe(st.session_state["df_enriquecido"], hide_index=True)
            st.download_button(
                "Descargar enriquecimiento (CSV)",
                data=st.session_state["df_enriquecido"].to_csv(index=False).encode("utf-8-sig"),
                file_name="denue_enriquecido.csv",
                mime="text/csv",
                icon=":material/download:",
            )

            st.divider()
            st.subheader("Validación y contacto (Hunter)")
            if not HUNTER_API_KEY:
                st.warning("Falta HUNTER_API_KEY en el .env para esta sección.")
            else:
                df_base = st.session_state["df_enriquecido"]
                correo_col = df_base["Correo"].astype(str).str.strip()
                grupo_a = df_base[(correo_col != "") & (correo_col.str.lower() != "nan")]
                grupo_b = df_base[~df_base.index.isin(grupo_a.index)]

                st.caption(
                    f"Grupo A — ya tienen correo ({len(grupo_a)}): se verifica y se busca quién lo usa "
                    "(con respaldo de búsqueda por rol si Hunter no identifica a nadie). "
                    f"Grupo B — sin correo ({len(grupo_b)}): se busca a la persona del rol elegido y se "
                    "estima su correo. Un solo click procesa ambos grupos."
                )
                col_a, col_b = st.columns(2)
                with col_a:
                    st.markdown(f"**Grupo A ({len(grupo_a)})**")
                    if not grupo_a.empty:
                        st.dataframe(grupo_a[["Razón social", "Correo"]], hide_index=True)
                with col_b:
                    st.markdown(f"**Grupo B ({len(grupo_b)})**")
                    if not grupo_b.empty:
                        st.dataframe(grupo_b[["Razón social", "Sitio web"]], hide_index=True)

                rol_elegido = None
                if not grupo_a.empty or not grupo_b.empty:
                    rol_elegido = st.selectbox(
                        "Rol a buscar (Grupo B, y respaldo para Grupo A si Hunter no identifica a nadie)",
                        options=[TODOS_LOS_ROLES] + list(ROLES_CONTACTO.keys()),
                    )
                    if rol_elegido == TODOS_LOS_ROLES:
                        st.caption(
                            "Busca los 4 roles para cada empresa — multiplica las búsquedas de "
                            "SerpAPI/Anthropic por empresa. Usar con pocas empresas a la vez."
                        )
                verificar = st.button("Verificar y buscar contactos", icon=":material/verified:")

                if verificar:
                    roles_seleccionados = roles_a_buscar(rol_elegido)
                    filas_contactos = []
                    with st.status("Verificando correos y buscando contactos...", expanded=True) as status:
                        for _, fila in grupo_a.iterrows():
                            correo = fila["Correo"]
                            status.update(label=f"Grupo A: verificando {correo}...")
                            try:
                                # Falla propia (no todo el try): un error transitorio de
                                # Hunter acá no debe cortar el resto de la cadena (Combined
                                # Enrichment, fallback por rol, otros correos del dominio),
                                # que no dependen de que la verificación haya funcionado.
                                try:
                                    verificacion = hunter_verificar_email(correo, HUNTER_API_KEY)
                                except Exception as exc_verificacion:
                                    verificacion = {"estado": "error de verificación — reintentar", "score": None}
                                    st.write(f"⚠ {correo} — no se pudo verificar con Hunter: {exc_verificacion}")
                                persona = None
                                if verificacion["estado"] not in ("invalid", "disposable"):
                                    try:
                                        persona = hunter_enriquecimiento_combinado(correo, HUNTER_API_KEY)
                                    except Exception as exc_combinado:
                                        st.write(f"⚠ {correo} — Combined Enrichment falló, sigo sin ese dato: {exc_combinado}")
                                dominio = dominio_de_empresa(correo, fila["Sitio web"])
                                score_final, confianza_final = calcular_score_correo(
                                    verificacion["score"], dominio, fila["Razón social"], SERPAPI_KEY
                                )

                                # Sin persona vía Hunter (típico en correos institucionales
                                # tipo ventas@/info@): fallback de búsqueda por rol. Se salta
                                # si el correo ya es claramente un buzón general (ej.
                                # archivogeneral@) — buscar una persona ahí siempre vuelve
                                # vacío. El correo del DENUE sigue siendo el contacto principal
                                # de la empresa — un correo alternativo que encuentre el
                                # fallback se agrega como fila aparte, no lo reemplaza.
                                correo_general = es_correo_general(correo)
                                contactos_fallback = []
                                contacto_fallback = None
                                if not persona and dominio and not correo_general:
                                    encontrados = []
                                    for terminos_rol in roles_seleccionados.values():
                                        resultado_rol = buscar_contacto_por_rol(
                                            fila["Razón social"], terminos_rol, SERPAPI_KEY, ANTHROPIC_API_KEY
                                        )
                                        if resultado_rol.nombre:
                                            encontrados.append(resultado_rol)
                                    contactos_fallback = _dedup_contactos(encontrados)
                                    contacto_fallback = contactos_fallback[0] if contactos_fallback else None

                                if persona:
                                    nombre_contacto, cargo_contacto, linkedin_contacto = (
                                        persona["nombre"], persona["cargo"], persona["linkedin"]
                                    )
                                    fuente_contacto = "DENUE + Hunter"
                                elif contacto_fallback:
                                    nombre_contacto, cargo_contacto, linkedin_contacto = (
                                        contacto_fallback.nombre, contacto_fallback.cargo, contacto_fallback.linkedin_url
                                    )
                                    fuente_contacto = "DENUE + Hunter + búsqueda web"
                                elif correo_general:
                                    nombre_contacto = cargo_contacto = linkedin_contacto = None
                                    fuente_contacto = "Correo general/institucional — sin contacto personal"
                                else:
                                    nombre_contacto = cargo_contacto = linkedin_contacto = None
                                    fuente_contacto = "DENUE + Hunter"

                                filas_contactos.append(fila_contacto(
                                    fila["Razón social"], nombre_contacto, correo, fila["Teléfono"],
                                    cargo_contacto, linkedin_contacto, es_principal=True,
                                    estado_correo=verificacion["estado"], score_correo=score_final,
                                    confianza_correo=confianza_final, fuente=fuente_contacto,
                                ))

                                for contacto_alt in contactos_fallback:
                                    hallazgo_alt = hunter_buscar_email(dominio, contacto_alt.nombre, HUNTER_API_KEY)
                                    if hallazgo_alt and hallazgo_alt["email"] != correo:
                                        filas_contactos.append(fila_contacto(
                                            fila["Razón social"], contacto_alt.nombre, hallazgo_alt["email"],
                                            fila["Teléfono"], contacto_alt.cargo, contacto_alt.linkedin_url,
                                            es_principal=False, score_correo=hallazgo_alt["score"],
                                            fuente="Búsqueda por rol",
                                            sources="; ".join(hallazgo_alt["sources"]) if hallazgo_alt["sources"] else None,
                                        ))

                                for otro in hunter_correos_del_dominio(dominio, HUNTER_API_KEY):
                                    filas_contactos.append(fila_contacto(
                                        fila["Razón social"], otro["nombre"], otro["correo"], fila["Teléfono"],
                                        otro["cargo"], otro["linkedin"], es_principal=False,
                                        score_correo=otro["confianza"], fuente="Hunter domain search",
                                    ))

                                if correo_general:
                                    detalle = " — correo general/institucional, sin contacto personal"
                                elif nombre_contacto:
                                    detalle = f" — {nombre_contacto}"
                                else:
                                    detalle = " — sin persona identificada"
                                st.write(f"✓ {correo} — {verificacion['estado']} (score {score_final}, {confianza_final}){detalle}")
                            except Exception as exc:
                                st.write(f"✗ {correo} — error: {exc}")

                        for _, fila in grupo_b.iterrows():
                            razon = fila["Razón social"]
                            status.update(label=f"Grupo B: buscando {razon}...")
                            try:
                                dominio = extraer_dominio(fila["Sitio web"])

                                encontrados = []
                                for terminos_rol in roles_seleccionados.values():
                                    resultado_rol = buscar_contacto_por_rol(
                                        razon, terminos_rol, SERPAPI_KEY, ANTHROPIC_API_KEY
                                    )
                                    if resultado_rol.nombre:
                                        encontrados.append(resultado_rol)
                                contactos_b = _dedup_contactos(encontrados)

                                # Se resuelve el correo de cada candidato encontrado (no solo
                                # del primero) y se marca "principal" al de mejor score
                                # verificado — si ninguno tiene correo verificable, el primero.
                                candidatos = []
                                for contacto in contactos_b:
                                    correo_adivinado = None
                                    estado_correo = "sin dominio conocido para buscar" if not dominio else "no se pudo estimar un correo"
                                    score_final = None
                                    confianza_final = None
                                    fuentes_publicas = None
                                    if dominio:
                                        hallazgo = hunter_buscar_email(dominio, contacto.nombre, HUNTER_API_KEY)
                                        if hallazgo:
                                            verificacion = hunter_verificar_email(
                                                hallazgo["email"], HUNTER_API_KEY
                                            )
                                            correo_adivinado = hallazgo["email"]
                                            estado_correo = verificacion["estado"]
                                            score_final, confianza_final = calcular_score_correo(
                                                verificacion["score"], dominio, razon, SERPAPI_KEY
                                            )
                                            if hallazgo["sources"]:
                                                fuentes_publicas = "; ".join(hallazgo["sources"])
                                    candidatos.append(
                                        (contacto, correo_adivinado, estado_correo, score_final, confianza_final, fuentes_publicas)
                                    )

                                if candidatos:
                                    indice_principal = max(
                                        range(len(candidatos)),
                                        key=lambda i: candidatos[i][3] if candidatos[i][3] is not None else -1,
                                    )
                                    for i, (contacto, correo_adivinado, estado_correo, score_final, confianza_final, fuentes_publicas) in enumerate(candidatos):
                                        filas_contactos.append(fila_contacto(
                                            razon, contacto.nombre, correo_adivinado, fila["Teléfono"],
                                            contacto.cargo, contacto.linkedin_url, es_principal=(i == indice_principal),
                                            estado_correo=estado_correo, score_correo=score_final,
                                            confianza_correo=confianza_final, fuente="Búsqueda web + Hunter",
                                            sources=fuentes_publicas,
                                        ))
                                    st.write(f"✓ {razon} — " + ", ".join(c.nombre for c, *_ in candidatos))
                                else:
                                    st.write(f"✗ {razon} — sin contacto encontrado")

                                if dominio:
                                    for otro in hunter_correos_del_dominio(dominio, HUNTER_API_KEY):
                                        filas_contactos.append(fila_contacto(
                                            razon, otro["nombre"], otro["correo"], fila["Teléfono"],
                                            otro["cargo"], otro["linkedin"], es_principal=False,
                                            score_correo=otro["confianza"], fuente="Hunter domain search",
                                        ))
                            except Exception as exc:
                                st.write(f"✗ {razon} — error: {exc}")
                        status.update(label="Verificación y búsqueda completas", state="complete")
                    df_nuevo = pd.DataFrame(
                        filas_contactos, columns=COLUMNAS_CONTACTO_MONDAY + COLUMNAS_CONTACTO_INTERNAS
                    )
                    for columna_gestion in COLUMNAS_CONTACTO_GESTION:
                        df_nuevo[columna_gestion] = False
                    st.session_state["df_contactos"] = df_nuevo

                if "df_contactos" in st.session_state and not st.session_state["df_contactos"].empty:
                    df_contactos_vista = st.session_state["df_contactos"][
                        COLUMNAS_CONTACTO_MONDAY + COLUMNAS_CONTACTO_INTERNAS
                    ]
                    st.markdown(f"**Contactos encontrados ({len(df_contactos_vista)})**")
                    st.caption(
                        "Una fila por candidato de contacto, todos ligados a la misma 'Cuenta "
                        "asociada' — no solo el principal. 'Es principal' marca el más fuerte de "
                        "cada empresa; el resto son alternativas para respaldo. Columnas hasta "
                        "'Fecha de inicio' calzan con el board de Contacto en Monday; las que "
                        "siguen son contexto propio. La gestión de contacto y exportación a "
                        "Monday está en la pestaña 'Monday'."
                    )
                    st.dataframe(df_contactos_vista, hide_index=True)
                    st.download_button(
                        "Descargar contactos (CSV)",
                        data=df_contactos_vista.to_csv(index=False).encode("utf-8-sig"),
                        file_name="denue_contactos.csv",
                        mime="text/csv",
                        icon=":material/download:",
                    )

with tab_monday:
    st.subheader("Gestión y exportación a Monday")

    if "_monday_aviso" in st.session_state:
        _tipo_aviso, _mensaje_aviso = st.session_state.pop("_monday_aviso")
        getattr(st, _tipo_aviso)(_mensaje_aviso)

    if "df_contactos" not in st.session_state or st.session_state["df_contactos"].empty:
        st.info("Todavía no hay contactos — corré \"Verificar y buscar contactos\" en la pestaña Enriquecimiento.")
    elif not MONDAY_API_KEY:
        st.warning("Falta MONDAY_API_KEY en el .env para gestionar y exportar contactos.")
    else:
        st.caption(
            "Marcá 'Contactado' cuando ya hablaste con la persona, o 'No existe / "
            "desvinculado' si el contacto no sirve. 'Exportar a Monday' solo se habilita "
            "para contactos marcados como Contactado, y pide confirmación antes de crear "
            "el item en Monday."
        )
        usuarios_monday = monday_listar_usuarios()
        df_actual = st.session_state["df_contactos"]

        pendientes = df_actual[~df_actual["Exportado a Monday"] & ~df_actual["No existe / desvinculado"]]
        exportados = df_actual[df_actual["Exportado a Monday"]]
        no_existentes = df_actual[df_actual["No existe / desvinculado"] & ~df_actual["Exportado a Monday"]]

        col_m1, col_m2, col_m3 = st.columns(3)
        col_m1.metric("Panel general", len(pendientes), border=True)
        col_m2.metric("Exportados a Monday", len(exportados), border=True)
        col_m3.metric("No existe / desvinculado", len(no_existentes), border=True)

        vista = st.segmented_control(
            "Categoría",
            options=["Panel general", "Exportados a Monday", "No existe / desvinculado"],
            default="Panel general",
            key="vista_monday",
            label_visibility="collapsed",
        )
        subset = {"Panel general": pendientes, "Exportados a Monday": exportados}.get(vista, no_existentes)

        st.divider()
        if subset.empty:
            st.caption("No hay contactos en esta categoría.")
        else:
            for idx, fila in subset.iterrows():
                _renderizar_tarjeta_contacto(idx, fila, usuarios_monday)
