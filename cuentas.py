"""
Integración con el board de Cuentas en Monday.com: clasificación de
empresas contra las cuentas ya cargadas, armado de perfil desde una cuenta
existente, y creación de cuentas nuevas. Ver structuraCuentas.md para el
esquema del board y docs/superpowers/specs/2026-09-09-tablero-cuentas-design.md
para las reglas de negocio.
"""
import json
from datetime import date

import pandas as pd
import streamlit as st

from config import (
    ESTADOS_CONTACTO_EXITOSO,
    MONDAY_BOARD_CONTACTO,
    MONDAY_BOARD_CUENTAS,
    MONDAY_COLUMNAS_CONTACTO,
    MONDAY_COLUMNAS_CUENTAS,
)
from monday import monday_graphql
from utils import _telefono_mx, _valor_valido


def clasificar_cuentas(df_empresas, cuentas_reales):
    """Clasifica df_empresas (con columna 'Razon_social') contra
    cuentas_reales — dict {nombre_normalizado: {item_id, tiene_convenio,
    tiene_contacto_exitoso, ...}}, ver monday_listar_cuentas_reales().
    Devuelve (df_nueva, df_existe_necesita_contacto, df_existe_gestionada),
    cada una con las columnas originales de df_empresas más 'Cuenta_item_id'
    (None si la cuenta es nueva). 'Gestionada' = tiene convenio o ya tiene
    un contacto con gestión exitosa (ver ESTADOS_CONTACTO_EXITOSO)."""
    nombres_normalizados = df_empresas["Razon_social"].astype(str).str.strip().str.lower()
    item_ids, gestionadas = [], []
    for nombre in nombres_normalizados:
        cuenta = cuentas_reales.get(nombre)
        if cuenta is None:
            item_ids.append(None)
            gestionadas.append(False)
        else:
            item_ids.append(cuenta["item_id"])
            gestionadas.append(cuenta["tiene_convenio"] or cuenta["tiene_contacto_exitoso"])

    df = df_empresas.copy()
    df["Cuenta_item_id"] = item_ids
    # dtype explícito + índice: con un df_empresas vacío, `gestionadas` es una lista
    # Python vacía y pandas infiere dtype float64 para la columna nueva (en vez de
    # bool), lo que rompe `~df_existe["_gestionada"]` más abajo (queda como una
    # Series float, no boolean) y a su vez el .drop(columns="_gestionada") posterior.
    df["_gestionada"] = pd.Series(gestionadas, index=df.index, dtype=bool)

    df_nueva = df[df["Cuenta_item_id"].isna()].drop(columns="_gestionada")
    df_existe = df[df["Cuenta_item_id"].notna()]
    df_existe_necesita_contacto = df_existe[~df_existe["_gestionada"]].drop(columns="_gestionada")
    df_existe_gestionada = df_existe[df_existe["_gestionada"]].drop(columns="_gestionada")
    return df_nueva, df_existe_necesita_contacto, df_existe_gestionada


def perfil_desde_cuenta(cuenta_monday):
    """Arma un dict con el mismo esquema que EnriquecimientoEmpresa.model_dump()
    (ver enrichment.py) a partir de los datos ya cargados en Cuentas, para
    una empresa que ya existe en Monday y no necesita re-enriquecerse.
    Mismas claves que la salida real de enriquecer_empresa() para poder
    pasar por el mismo pipeline de armado de df_enriquecido."""
    tamano = cuenta_monday.get("tamano")
    cantidad_empleados = cuenta_monday.get("cantidad_empleados")
    if cantidad_empleados and tamano:
        empleados_texto = f"{cantidad_empleados} ({tamano}, dato de Monday)"
    elif cantidad_empleados:
        empleados_texto = f"{cantidad_empleados} (dato de Monday)"
    elif tamano:
        empleados_texto = f"{tamano} (dato de Monday)"
    else:
        empleados_texto = None
    return {
        "linkedin_url": None,
        "sitio_web": cuenta_monday.get("pagina_web"),
        "empleados_linkedin": empleados_texto,
        "actividad_reciente": False,
        "resumen_actividad": None,
        "senales_riesgo": False,
        "resumen_riesgo": None,
        "confianza_coincidencia": "alta",
        "evidencia": (
            "Perfil tomado del board de Cuentas en Monday (cuenta ya existente) "
            "— no se re-enriqueció con búsqueda web."
        ),
        "tipo_empresa": None,
        "rfc": None,
    }


def _linked_item_ids(column_value):
    """item_ids (str) vinculados en una columna board_relation real — [] si no
    hay vínculos. Los ids llegan directo en 'linked_item_ids' vía el fragmento
    tipado BoardRelationValue; no hace falta parsear 'value' como JSON
    (confirmado empíricamente — 'value'/'text' son siempre null en estas
    columnas reales, a diferencia de lo que asumía la primera versión de este
    código, que intentaba leer 'linkedPulseIds' de un json.loads(value))."""
    if not column_value:
        return []
    return [str(i) for i in (column_value.get("linked_item_ids") or [])]


def _estados_contacto_por_cuenta():
    """{cuenta_item_id (str): set(labels de 'Estado')} de todos los
    contactos del board de Contacto que ya tienen una cuenta vinculada —
    trae todos los items en bulk, paginando con cursor (items_page /
    next_items_page) igual que monday_listar_cuentas_reales() más abajo."""
    columna_cuenta = MONDAY_COLUMNAS_CONTACTO["Cuenta asociada"]
    columna_estado = MONDAY_COLUMNAS_CONTACTO["Estado"]
    estados_por_cuenta = {}

    def _sumar(items):
        for item in items:
            valores = {cv["id"]: cv for cv in item["column_values"]}
            for cuenta_id in _linked_item_ids(valores[columna_cuenta]):
                estados_por_cuenta.setdefault(cuenta_id, set())
                etiqueta = valores[columna_estado]["text"]
                if etiqueta:
                    estados_por_cuenta[cuenta_id].add(etiqueta)

    query_inicial = """
    query ($boardId: ID!, $columnaIds: [String!]) {
      boards(ids: [$boardId]) {
        items_page(limit: 100) {
          cursor
          items { column_values(ids: $columnaIds) { id text value ... on BoardRelationValue { linked_item_ids } } }
        }
      }
    }
    """
    data = monday_graphql(
        query_inicial, {"boardId": MONDAY_BOARD_CONTACTO, "columnaIds": [columna_cuenta, columna_estado]}
    )
    pagina = data["boards"][0]["items_page"]
    cursor = pagina["cursor"]
    _sumar(pagina["items"])

    query_siguiente = """
    query ($cursor: String!, $columnaIds: [String!]) {
      next_items_page(cursor: $cursor, limit: 100) {
        cursor
        items { column_values(ids: $columnaIds) { id text value ... on BoardRelationValue { linked_item_ids } } }
      }
    }
    """
    while cursor:
        data = monday_graphql(query_siguiente, {"cursor": cursor, "columnaIds": [columna_cuenta, columna_estado]})
        pagina = data["next_items_page"]
        cursor = pagina["cursor"]
        _sumar(pagina["items"])

    return estados_por_cuenta


@st.cache_data(show_spinner="Consultando cuentas ya cargadas en Monday...")
def monday_listar_cuentas_reales():
    """{nombre_normalizado: {item_id, tiene_convenio, tiene_contacto_exitoso,
    pagina_web, cantidad_empleados, tamano}} de TODOS los items del board de
    Cuentas real, trayendo todo en bulk con paginación por cursor. Cacheada
    sin TTL, refresco manual (botón "Actualizar cuentas de Monday" en
    app.py llama a monday_listar_cuentas_reales.clear())."""
    columnas_a_leer = ["Convenio asociado", "Página web", "Cantidad de empleados", "Tamaño"]
    ids_columnas = [MONDAY_COLUMNAS_CUENTAS[c] for c in columnas_a_leer]
    cuentas = {}

    def _sumar(items):
        for item in items:
            valores = {cv["id"]: cv for cv in item["column_values"]}
            nombre_normalizado = item["name"].strip().lower()
            # "Tamaño" es una columna fórmula: Monday siempre devuelve "text"
            # vacío para estas columnas — el valor calculado viene en
            # "display_value", solo dentro del fragmento tipado FormulaValue
            # (confirmado empíricamente 2026-09-22, ver la nota en la query).
            tamano_valor = valores[MONDAY_COLUMNAS_CUENTAS["Tamaño"]]
            cuentas[nombre_normalizado] = {
                "item_id": item["id"],
                "tiene_convenio": len(_linked_item_ids(valores[MONDAY_COLUMNAS_CUENTAS["Convenio asociado"]])) > 0,
                "pagina_web": valores[MONDAY_COLUMNAS_CUENTAS["Página web"]]["text"] or None,
                "cantidad_empleados": valores[MONDAY_COLUMNAS_CUENTAS["Cantidad de empleados"]]["text"] or None,
                "tamano": tamano_valor.get("display_value") or None,
            }

    # "Tamaño" (formula_mm7dj04x) es una columna fórmula — su valor calculado
    # solo viene en "display_value" dentro de "... on FormulaValue", "text"
    # siempre viene vacío para este tipo de columna (confirmado empíricamente
    # contra la API 2026-09-22).
    query_inicial = """
    query ($boardId: ID!, $columnaIds: [String!]) {
      boards(ids: [$boardId]) {
        items_page(limit: 100) {
          cursor
          items {
            id name
            column_values(ids: $columnaIds) {
              id text value
              ... on BoardRelationValue { linked_item_ids }
              ... on FormulaValue { display_value }
            }
          }
        }
      }
    }
    """
    data = monday_graphql(query_inicial, {"boardId": MONDAY_BOARD_CUENTAS, "columnaIds": ids_columnas})
    pagina = data["boards"][0]["items_page"]
    cursor = pagina["cursor"]
    _sumar(pagina["items"])

    query_siguiente = """
    query ($cursor: String!, $columnaIds: [String!]) {
      next_items_page(cursor: $cursor, limit: 100) {
        cursor
        items {
          id name
          column_values(ids: $columnaIds) {
            id text value
            ... on BoardRelationValue { linked_item_ids }
            ... on FormulaValue { display_value }
          }
        }
      }
    }
    """
    while cursor:
        data = monday_graphql(query_siguiente, {"cursor": cursor, "columnaIds": ids_columnas})
        pagina = data["next_items_page"]
        cursor = pagina["cursor"]
        _sumar(pagina["items"])

    estados = _estados_contacto_por_cuenta()
    for cuenta in cuentas.values():
        cuenta["tiene_contacto_exitoso"] = bool(estados.get(cuenta["item_id"], set()) & ESTADOS_CONTACTO_EXITOSO)

    return cuentas


def monday_crear_cuenta(fila):
    """Crea un item nuevo en el board de Cuentas real a partir de una fila
    de df_contactos (esquema de fila_contacto en utils.py — usa las claves
    '... empresa' agregadas ahí). Se llama solo al confirmar el export de
    un pre-lead de cuenta nueva (nunca automático). Devuelve el item_id
    real creado.

    Desde el cambio de esquema del board (re-confirmado empíricamente
    2026-09-22, verificado contra la doc oficial de Monday), la mayoría de
    las columnas de MONDAY_COLUMNAS_CUENTAS son tipos reales
    (email/phone/link/status), cada una con su propio shape de JSON — ya
    no alcanza con mandar un string plano salvo en las que siguen siendo
    'text' simple (Cantidad de empleados, Descripcion, País, RFC/NIT/RUC).
    "Categoria" y "Tamaño" son columnas fórmula calculadas por Monday: NO
    se escriben más (antes se calculaba "Tamaño" a mano con TAMANOS_MONDAY
    y se escribía como texto). "Grupo Empresarial" es ahora un
    board_relation real sin automatizar (decisión explícita, no hay item
    de grupo que linkear) — solo se sigue escribiendo el flag "Pertenece a
    algun grupo empresarial" (status Sí/No)."""
    columnas = MONDAY_COLUMNAS_CUENTAS
    valores = {}
    if _valor_valido(fila.get("Sector empresa")):
        valores[columnas["Sector"]] = {"label": str(fila["Sector empresa"])}
    if _valor_valido(fila.get("Personal estimado empresa")):
        valores[columnas["Cantidad de empleados"]] = str(fila["Personal estimado empresa"])
    if _valor_valido(fila.get("Correo empresa")):
        correo_empresa = str(fila["Correo empresa"])
        valores[columnas["E-Mail"]] = {"email": correo_empresa, "text": correo_empresa}
    telefono = _telefono_mx(fila.get("Teléfono (empresa)"))
    if telefono:
        valores[columnas["Teléfono"]] = {"phone": telefono, "countryShortName": "MX"}
    if _valor_valido(fila.get("Sitio web empresa")):
        valores[columnas["Página web"]] = {"url": str(fila["Sitio web empresa"]), "text": ""}
    valores[columnas["País"]] = "México"
    valores[columnas["Fecha de inicio"]] = {"date": date.today().isoformat()}
    # Grupo empresarial (probable): "Sí — ..." o "No", calculado en la Etapa 3
    # (marcar_grupo_corporativo). Solo se escribe el flag Sí/No — "Grupo
    # Empresarial" es un board_relation real sin item que linkear, se deja
    # sin tocar (ver docstring).
    grupo = fila.get("Grupo empresarial")
    if _valor_valido(grupo):
        es_grupo = "Si" if str(grupo).strip().lower().startswith("sí") else "No"
        valores[columnas["Pertenece a algun grupo empresarial"]] = {"label": es_grupo}
    if _valor_valido(fila.get("Tipo empresa")):
        valores[columnas["Tipo"]] = {"label": str(fila["Tipo empresa"])}
    if _valor_valido(fila.get("Descripcion empresa")):
        valores[columnas["Descripcion"]] = str(fila["Descripcion empresa"])
    # RFC: se busca por enriquecimiento (Serper + Claude) sin verificación
    # oficial — se antepone un aviso para que no se use como dato certero
    # sin revisar (ver diseño acordado, RFC/NIT/RUC = confianza baja).
    if _valor_valido(fila.get("RFC empresa")):
        valores[columnas["RFC/NIT/RUC"]] = f"{fila['RFC empresa']} (no verificado, revisar antes de usar)"

    mutation = """
    mutation ($boardId: ID!, $itemName: String!, $columnValues: JSON!) {
      create_item(
        board_id: $boardId, item_name: $itemName, column_values: $columnValues,
        create_labels_if_missing: true
      ) { id }
    }
    """
    nombre_item = str(fila.get("Cuenta asociada") or "Cuenta sin nombre")
    data = monday_graphql(mutation, {
        "boardId": MONDAY_BOARD_CUENTAS,
        "itemName": nombre_item,
        "columnValues": json.dumps(valores),
    })
    return data["create_item"]["id"]
