"""
Integración con la API GraphQL de Monday.com: helper genérico de consulta,
chequeo de duplicados por correo, listado de usuarios y creación de
items en el board de Contacto (ver contacto.md para el esquema del board).
"""
import json

import requests
import streamlit as st

from config import MONDAY_API_KEY, MONDAY_BOARD_CONTACTO, MONDAY_COLUMNAS_CONTACTO, MONDAY_URL
from utils import _telefono_mx, _valor_valido


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


@st.cache_data(ttl="1h", show_spinner=False)
def monday_listar_usuarios():
    """Nombres de los usuarios reales del workspace de Monday. Se usa para
    armar el selector de 'Responsable' con usuarios reales en vez de dejar
    escribir cualquier nombre a mano (evita responsables inventados o mal
    escritos); el nombre elegido se guarda tal cual como texto plano en
    Monday (ver monday_crear_contacto más abajo), ya que 'Responsable' es
    una columna 'text' simple en este board, no un people-picker nativo."""
    try:
        data = monday_graphql("{ users { name } }")
        return sorted(u["name"] for u in data["users"])
    except Exception:
        return []


def monday_crear_contacto(fila, cuenta_item_id, responsable_nombre=None):
    """Crea un item en el board de Contacto a partir de una fila con el
    esquema de COLUMNAS_CONTACTO_MONDAY. 'cuenta_item_id' es el item_id
    real de la cuenta en el board de Cuentas (ver cuentas.py) — se linkea
    con un board_relation real, no con texto. 'Estado' queda en
    'Contactado' — se llama a esta función solo al exportar un contacto ya
    contactado. 'responsable_nombre' es el nombre de un usuario real de
    Monday (la app lo restringe a las opciones de monday_listar_usuarios
    vía el selectbox, así se evita un responsable inventado o mal
    escrito) — se omite si no se pasa.

    Todas las columnas de MONDAY_COLUMNAS_CONTACTO son type "text" simple
    (confirmado empíricamente en el Task 1 — ver la nota al inicio de
    structuraContacto.md), excepto
    "Cuenta asociada" que es la única columna board_relation real del
    board: a diferencia de columnas típicas de Monday con tipos dedicados
    (status/email/phone/link/date/people), acá se escribe siempre un
    string plano, nunca el dict tipado que usa la API para esas otras
    columnas. "Responsable" en particular es también type "text" en este
    board de prueba (no un people-picker real): como no hay people-picker
    que resuelva un ID a nombre, se escribe directamente el nombre del
    usuario como texto plano (antes se escribía el ID numérico, que
    quedaba ilegible en Monday)."""
    columnas = dict(MONDAY_COLUMNAS_CONTACTO)
    valores = {columnas["Cuenta asociada"]: {"item_ids": [int(cuenta_item_id)]}}

    correo = fila.get("Correo")
    correo_valido = _valor_valido(correo)
    if correo_valido:
        valores[columnas["Correo"]] = correo

    telefono = _telefono_mx(fila.get("Teléfono (empresa)"))
    if telefono:
        valores[columnas["Teléfono (empresa)"]] = telefono

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
        valores[columnas["Nivel de cargo"]] = str(fila["Nivel de cargo"])
    if _valor_valido(fila.get("Link de LinkedIn")):
        valores[columnas["Link de LinkedIn"]] = str(fila["Link de LinkedIn"])
    if _valor_valido(fila.get("Fecha de inicio")):
        valores[columnas["Fecha de inicio"]] = str(fila["Fecha de inicio"])
    if _valor_valido(responsable_nombre):
        valores[columnas["Responsable"]] = str(responsable_nombre)
    valores[columnas["Estado"]] = "Contactado"

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
