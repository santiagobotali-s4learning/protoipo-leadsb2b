"""
Integración con la API del DENUE (INEGI): construcción de la URL de consulta,
descarga paginada de establecimientos, agrupación de sucursales por empresa
(estimando personal total) y detección de grupos corporativos probables.
"""
from urllib.parse import quote

import pandas as pd
import requests
import streamlit as st

from catalogos import ESTRATOS
from config import (
    BANDAS_TOTALES,
    BASE_URL,
    COLUMNAS_PRIORITARIAS,
    SECTOR_MONDAY_PALABRAS_CLAVE,
    SECTOR_MONDAY_POR_SCIAN,
    TAMANOS_MONDAY,
)
from utils import dominio_de_empresa


def reordenar_columnas(df):
    prioritarias = [c for c in COLUMNAS_PRIORITARIAS if c in df.columns]
    resto = [c for c in df.columns if c not in prioritarias]
    return df[prioritarias + resto]


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


def banda_total(personal_min):
    for umbral, etiqueta in BANDAS_TOTALES:
        if personal_min >= umbral:
            return etiqueta
    return BANDAS_TOTALES[-1][1]


def tamano_monday(personal_min):
    """Micro/Pequeña/Mediana/Grande para la columna 'Tamano' del board de
    Cuentas — cortes simples y únicos (no por sector), definidos por el
    usuario, distintos de BANDAS_TOTALES (que sirve para filtrar/mostrar en
    la UI, no para exportar a Monday)."""
    for techo, etiqueta in TAMANOS_MONDAY:
        if personal_min <= techo:
            return etiqueta
    return "Grande"


def sector_monday(clase_actividad, clase_actividad_id):
    """Uno de los 25 sectores del dropdown 'Sector' del board de Cuentas, a
    partir de la Clase_actividad (texto SCIAN) y su código. Primero prueba
    palabras clave (para sub-sectores que el SCIAN de 2 dígitos no separa,
    ej. Automotriz dentro de Manufactureras); si ninguna matchea, cae al
    sector SCIAN de 2 dígitos. 'Servicios' es el default si no hay
    código o no está en la tabla — no hay 'sector desconocido' en el dropdown."""
    texto = str(clase_actividad or "").lower()
    for claves, etiqueta in SECTOR_MONDAY_PALABRAS_CLAVE:
        if any(clave in texto for clave in claves):
            return etiqueta
    prefijo = str(clase_actividad_id or "")[:2]
    return SECTOR_MONDAY_POR_SCIAN.get(prefijo, "Servicios")


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
        clase_actividad = primero_no_vacio(sub["Clase_actividad"])
        clase_actividad_id = primero_no_vacio(sub["CLASE_ACTIVIDAD_ID"])
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
                "Tamano_monday": tamano_monday(personal_min),
                "Correo_e": primero_no_vacio(sub["Correo_e"]),
                "Telefono": primero_no_vacio(sub["Telefono"]),
                "Sitio_internet": primero_no_vacio(sub["Sitio_internet"]),
                "Clase_actividad": clase_actividad,
                "CLASE_ACTIVIDAD_ID": clase_actividad_id,
                "Sector_monday": sector_monday(clase_actividad, clase_actividad_id),
                "Ubicacion": primero_no_vacio(sub["Ubicacion"]),
                "Fecha_Alta": primero_no_vacio(sub["Fecha_Alta"]),
            }
        )
    columnas = [
        "Razon_social", "Nombre", "Sucursales", "Personal_estimado", "Personal_punto_medio", "Banda_total",
        "Tamano_monday", "Correo_e", "Telefono", "Sitio_internet", "Clase_actividad", "CLASE_ACTIVIDAD_ID",
        "Sector_monday", "Ubicacion", "Fecha_Alta", "Personal_min", "Personal_max",
    ]
    return pd.DataFrame(filas, columns=columnas)


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
