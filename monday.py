"""
Integración con la API GraphQL de Monday.com: helper genérico de consulta,
chequeo de duplicados por correo, listado de cuentas/usuarios y creación de
items en el board de Contacto (ver contacto.md para el esquema del board).
"""
import json

import requests
import streamlit as st

from config import MONDAY_API_KEY, MONDAY_BOARD_CONTACTO, MONDAY_COLUMNAS_CONTACTO, MONDAY_URL
from utils import _telefono_mx, _texto, _valor_valido


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
