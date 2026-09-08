"""
Helpers genéricos compartidos entre los módulos de integración y la UI:
parsing de dominios/teléfonos, validación de valores "vacíos" al estilo
pandas, y armado de filas con el esquema del board de Contacto en Monday.
"""
import re
from datetime import date
from urllib.parse import quote, urlparse

import pandas as pd
import requests
import streamlit as st

from config import LOCAL_PARTS_CORREO_GENERAL, NIVELES_CARGO


def extraer_dominio(url):
    if not url or not str(url).strip():
        return None
    url = str(url).strip()
    if "://" not in url:
        url = f"http://{url}"
    dominio = urlparse(url).netloc.lower().replace("www.", "")
    return dominio or None


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


def es_correo_general(correo):
    """True si la parte local del correo (antes del @) es un buzón funcional
    típico (info@, contacto@, archivogeneral@...) y no una persona."""
    if not correo or "@" not in str(correo):
        return False
    local = re.sub(r"[^a-z]", "", str(correo).split("@", 1)[0].lower())
    return any(clave in local for clave in LOCAL_PARTS_CORREO_GENERAL)


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
