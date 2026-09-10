# Tablero de Cuentas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar el descarte total de empresas ya cargadas en Monday por una clasificación en 3 grupos contra el board de Cuentas real (nueva / existe-necesita-contacto / existe-gestionada), saltar el re-enriquecimiento de perfil para cuentas existentes, y exportar pre-leads de cuenta+contacto vinculados con un `board_relation` real de Monday.

**Architecture:** Se extiende el pipeline lineal de 4 pestañas ya existente (`app.py`) en vez de agregar un flujo desacoplado. Un módulo nuevo `cuentas.py` (mismo patrón que `monday.py`) aporta la clasificación y la integración con el board de Cuentas; `monday.py` y `utils.py` se extienden lo mínimo necesario para vincular cuenta↔contacto con un `board_relation` real en vez de texto libre.

**Tech Stack:** Python, Streamlit, pandas, Monday.com GraphQL API v2, pytest (nuevo — no había test runner en el proyecto).

**Spec:** `docs/superpowers/specs/2026-09-09-tablero-cuentas-design.md`

## Global Constraints

- **Prerrequisito para el Task 1:** `MONDAY_API_KEY` en `.env` debe apuntar al tablero de prueba funcional nuevo (el que tiene Cuentas + Contacto con la estructura de `structuraCuentas.md`/`structuraContacto.md`), no al board de prueba viejo ("pruebaContacto"). Sin esto, el Task 1 no se puede ejecutar y los tasks 4-8 tampoco (dependen de los IDs reales que ahí se relevan).
- **Match de existencia de cuenta:** nombre del item de Cuentas vs. Razón social del DENUE, normalizado con `.strip().lower()` — sin fuzzy matching.
- **Cuenta "gestionada" (se descarta, no se busca contacto):** tiene al menos un vínculo en la columna "Convenios", **o** tiene al menos un contacto vinculado con Estado en `{"Contactado", "Convenio firmado"}` (exactamente esos dos labels — `ESTADOS_CONTACTO_EXITOSO` en `config.py`).
- **Alta de cuenta nueva en Monday:** nunca automática — se crea recién al confirmar el export del pre-lead (mismo patrón que ya existe para contactos).
- **Empresas que ya existen en Monday y necesitan contacto:** no pasan por el enriquecimiento SerpAPI+Claude — usan el perfil ya cargado en Cuentas.
- **Nunca asumir el formato de una API externa sin verificarlo primero** (convención ya establecida en este proyecto) — el Task 1 existe exactamente para esto; si el shape real de un `column_value` difiere de lo escrito en los tasks 4/5, hay que ajustar el parsing antes de seguir, no forzar el shape supuesto.
- **Fuera de alcance:** columnas de Cuentas no relacionadas a este flujo (Eventos, Empleabilidad, Académico, Relacionamiento y ventas, Plan ESG, Documento ESG, Grupo empresarial asociado, Oportunidades), agrupar visualmente el panel final por cuenta (queda con la lista de tarjetas actual, solo cambia la lógica de export).

---

### Task 1: Verificación empírica de Monday + `config.py`

**Files:**
- Modify: `config.py`

**Interfaces:**
- Produces: `MONDAY_BOARD_CUENTAS` (str), `MONDAY_COLUMNAS_CUENTAS` (dict), `ESTADOS_CONTACTO_EXITOSO` (set), y `MONDAY_BOARD_CONTACTO`/`MONDAY_COLUMNAS_CONTACTO` actualizados con los IDs reales del tablero de prueba nuevo — todos los tasks siguientes los consumen vía `import` desde `config.py`.

Antes de arrancar, confirmar con el usuario que `MONDAY_API_KEY` en `.env` ya apunta al tablero de prueba funcional nuevo (no al viejo "pruebaContacto"). Sin esto, ningún curl de este task funciona.

- [ ] **Step 1: Listar boards y confirmar IDs de Cuentas y Contacto**

Correr (reemplazando `$MONDAY_API_KEY` por el valor real del `.env`):

```bash
curl -s -X POST https://api.monday.com/v2 \
  -H "Authorization: $MONDAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "{ boards (limit: 200) { id name } }"}'
```

Buscar en la respuesta el board cuyo nombre corresponde a "Cuentas" y el que corresponde a "Contacto" (puede no llamarse igual que el viejo "pruebaContacto"). Anotar ambos IDs.

- [ ] **Step 2: Traer columnas reales del board de Cuentas**

```bash
curl -s -X POST https://api.monday.com/v2 \
  -H "Authorization: $MONDAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "query ($boardId: ID!) { boards(ids: [$boardId]) { columns { id title type } } }", "variables": {"boardId": "<ID_CUENTAS>"}}'
```

Mapear cada `title` contra `structuraCuentas.md` y anotar el `id` real de: "Nombre de la alianza" (no se usa — se usa el nombre del item), "Convenios", "Sector", "Cantidad de empleados", "Tamaño", "País", "Página web", "E-Mail", "Teléfono", "Fecha de inicio". Confirmar que "Convenios" tiene `type` de vínculo entre boards (anotar el nombre exacto que devuelve la API — puede ser `board_relation` u otro).

- [ ] **Step 3: Traer columnas reales del board de Contacto y confirmar labels de "Estado"**

```bash
curl -s -X POST https://api.monday.com/v2 \
  -H "Authorization: $MONDAY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"query": "query ($boardId: ID!) { boards(ids: [$boardId]) { columns { id title type settings_str } } }", "variables": {"boardId": "<ID_CONTACTO>"}}'
```

Anotar el `id` real de cada columna de `MONDAY_COLUMNAS_CONTACTO` (todas — el board es nuevo, los IDs viejos no sirven). Confirmar que "Cuenta asociada" tiene el mismo `type` de vínculo anotado en el Step 2. Para "Estado", parsear `settings_str` (JSON con los labels configurados) y confirmar que están los 8 valores: Nuevo, En gestión, Contactado, No contactado, No interesado, No válido, Inactivo, Convenio firmado — si el texto exacto difiere (mayúsculas, tildes) del que se usa en `ESTADOS_CONTACTO_EXITOSO`, usar el texto exacto que devuelve la API.

- [ ] **Step 4: Confirmar el shape de un `column_value` de tipo vínculo, con datos reales**

Crear un item de prueba en Cuentas y otro en Contacto, vincularlos, y leer la respuesta:

```bash
# Crear item de prueba en Cuentas
curl -s -X POST https://api.monday.com/v2 \
  -H "Authorization: $MONDAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"query": "mutation ($boardId: ID!) { create_item(board_id: $boardId, item_name: \"ZZZ TEST BORRAR\") { id } }", "variables": {"boardId": "<ID_CUENTAS>"}}'

# Crear item de prueba en Contacto y vincularlo a la cuenta de prueba (ITEM_ID_CUENTA_TEST del paso anterior)
curl -s -X POST https://api.monday.com/v2 \
  -H "Authorization: $MONDAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"query": "mutation ($boardId: ID!, $col: JSON!) { create_item(board_id: $boardId, item_name: \"ZZZ TEST BORRAR\", column_values: $col) { id } }", "variables": {"boardId": "<ID_CONTACTO>", "col": "{\"<COLUMN_ID_CUENTA_ASOCIADA>\": {\"item_ids\": [<ITEM_ID_CUENTA_TEST>]}}"}}'

# Leer el column_value del item de Contacto recién creado
curl -s -X POST https://api.monday.com/v2 \
  -H "Authorization: $MONDAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"query": "query ($itemId: ID!, $colId: [String!]) { items(ids: [$itemId]) { column_values(ids: $colId) { id text value } } }", "variables": {"itemId": "<ITEM_ID_CONTACTO_TEST>", "colId": ["<COLUMN_ID_CUENTA_ASOCIADA>"]}}'
```

Anotar el JSON exacto del campo `value` en la respuesta del último curl (debería traer algo con los IDs vinculados — el nombre de la clave interna, ej. `linkedPulseIds`, es lo que hace falta confirmar). Los tasks 4 y 5 de este plan asumen `{"linkedPulseIds": [{"linkedPulseId": <id>}]}` para lectura y `{"item_ids": [<id>]}` para escritura — si la respuesta real difiere, ajustar el parsing en esos tasks antes de darlos por buenos.

- [ ] **Step 5: Borrar los items de prueba**

```bash
curl -s -X POST https://api.monday.com/v2 \
  -H "Authorization: $MONDAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"query": "mutation ($id: ID!) { delete_item(item_id: $id) { id } }", "variables": {"id": "<ITEM_ID_CUENTA_TEST>"}}'
curl -s -X POST https://api.monday.com/v2 \
  -H "Authorization: $MONDAY_API_KEY" -H "Content-Type: application/json" \
  -d '{"query": "mutation ($id: ID!) { delete_item(item_id: $id) { id } }", "variables": {"id": "<ITEM_ID_CONTACTO_TEST>"}}'
```

- [ ] **Step 6: Actualizar `config.py` con los valores reales**

Editar `config.py`: reemplazar `MONDAY_BOARD_CONTACTO` y todos los valores de `MONDAY_COLUMNAS_CONTACTO` por los IDs reales del Step 3, y agregar:

```python
# Board "Cuentas" (tablero real de prueba) — IDs de columna confirmados
# empíricamente contra la API (ver Task 1 del plan de tablero de cuentas).
MONDAY_BOARD_CUENTAS = "<ID_CUENTAS del Step 1>"
MONDAY_COLUMNAS_CUENTAS = {
    "Convenios": "<id del Step 2>",
    "Sector": "<id del Step 2>",
    "Cantidad de empleados": "<id del Step 2>",
    "Tamaño": "<id del Step 2>",
    "País": "<id del Step 2>",
    "Página web": "<id del Step 2>",
    "E-Mail": "<id del Step 2>",
    "Teléfono": "<id del Step 2>",
    "Fecha de inicio": "<id del Step 2>",
}
# Estados de MONDAY_COLUMNAS_CONTACTO["Estado"] que cuentan como gestión
# avanzada/exitosa — una cuenta con al menos un contacto en uno de estos
# estados no necesita más contactos nuevos (ver spec, sección 6).
ESTADOS_CONTACTO_EXITOSO = {"Contactado", "Convenio firmado"}
```

- [ ] **Step 7: Commit**

```bash
git add config.py
git commit -m "config: IDs reales de Monday para el tablero de Cuentas"
```

---

### Task 2: `cuentas.py` — clasificación pura de empresas (TDD)

**Files:**
- Create: `cuentas.py`
- Create: `tests/test_cuentas.py`
- Modify: `requirements.txt`

**Interfaces:**
- Consumes: nada de otros tasks (función pura, sin I/O).
- Produces: `clasificar_cuentas(df_empresas, cuentas_reales) -> (df_nueva, df_existe_necesita_contacto, df_existe_gestionada)`, usada por el Task 6 (`app.py`). `cuentas_reales` es un `dict {nombre_normalizado: {"item_id": str, "tiene_convenio": bool, "tiene_contacto_exitoso": bool, ...}}` — el shape completo (con más claves) lo define el Task 4, pero este task solo necesita esas 3 claves.

- [ ] **Step 1: Agregar pytest a las dependencias**

Editar `requirements.txt`, agregar una línea:

```
pytest
```

Correr: `pip install pytest`

- [ ] **Step 2: Escribir el test que falla**

Crear `tests/test_cuentas.py`:

```python
import pandas as pd

from cuentas import clasificar_cuentas


def _df_empresas(nombres):
    return pd.DataFrame({"Razon_social": nombres, "Personal_min": [100] * len(nombres)})


def test_empresa_sin_match_es_nueva():
    df_nueva, df_necesita, df_gestionada = clasificar_cuentas(_df_empresas(["Empresa Nueva SA"]), {})
    assert list(df_nueva["Razon_social"]) == ["Empresa Nueva SA"]
    assert df_necesita.empty
    assert df_gestionada.empty
    assert df_nueva.iloc[0]["Cuenta_item_id"] is None


def test_empresa_existente_sin_convenio_ni_contacto_exitoso_necesita_contacto():
    cuentas_reales = {
        "empresa existente sa": {"item_id": "111", "tiene_convenio": False, "tiene_contacto_exitoso": False}
    }
    df_nueva, df_necesita, df_gestionada = clasificar_cuentas(
        _df_empresas(["Empresa Existente SA"]), cuentas_reales
    )
    assert df_nueva.empty
    assert df_gestionada.empty
    assert list(df_necesita["Razon_social"]) == ["Empresa Existente SA"]
    assert df_necesita.iloc[0]["Cuenta_item_id"] == "111"


def test_empresa_con_convenio_esta_gestionada():
    cuentas_reales = {
        "empresa con convenio sa": {"item_id": "222", "tiene_convenio": True, "tiene_contacto_exitoso": False}
    }
    df_nueva, df_necesita, df_gestionada = clasificar_cuentas(
        _df_empresas(["Empresa Con Convenio SA"]), cuentas_reales
    )
    assert df_nueva.empty
    assert df_necesita.empty
    assert list(df_gestionada["Razon_social"]) == ["Empresa Con Convenio SA"]


def test_empresa_con_contacto_exitoso_esta_gestionada():
    cuentas_reales = {
        "empresa contactada sa": {"item_id": "333", "tiene_convenio": False, "tiene_contacto_exitoso": True}
    }
    df_nueva, df_necesita, df_gestionada = clasificar_cuentas(
        _df_empresas(["Empresa Contactada SA"]), cuentas_reales
    )
    assert df_nueva.empty
    assert df_necesita.empty
    assert list(df_gestionada["Razon_social"]) == ["Empresa Contactada SA"]


def test_match_normaliza_espacios_y_mayusculas():
    cuentas_reales = {"empresa mayus sa": {"item_id": "444", "tiene_convenio": True, "tiene_contacto_exitoso": False}}
    df_nueva, df_necesita, df_gestionada = clasificar_cuentas(
        _df_empresas(["  EMPRESA MAYUS SA  "]), cuentas_reales
    )
    assert len(df_gestionada) == 1
```

- [ ] **Step 3: Correr los tests y verificar que fallan**

Run: `pytest tests/test_cuentas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'cuentas'`

- [ ] **Step 4: Implementar `clasificar_cuentas`**

Crear `cuentas.py`:

```python
"""
Integración con el board de Cuentas en Monday.com: clasificación de
empresas contra las cuentas ya cargadas, armado de perfil desde una cuenta
existente, y creación de cuentas nuevas. Ver structuraCuentas.md para el
esquema del board y docs/superpowers/specs/2026-09-09-tablero-cuentas-design.md
para las reglas de negocio.
"""


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
    df["_gestionada"] = gestionadas

    df_nueva = df[df["Cuenta_item_id"].isna()].drop(columns="_gestionada")
    df_existe = df[df["Cuenta_item_id"].notna()]
    df_existe_necesita_contacto = df_existe[~df_existe["_gestionada"]].drop(columns="_gestionada")
    df_existe_gestionada = df_existe[df_existe["_gestionada"]].drop(columns="_gestionada")
    return df_nueva, df_existe_necesita_contacto, df_existe_gestionada
```

- [ ] **Step 5: Correr los tests y verificar que pasan**

Run: `pytest tests/test_cuentas.py -v`
Expected: PASS (5 tests)

- [ ] **Step 6: Commit**

```bash
git add requirements.txt cuentas.py tests/test_cuentas.py
git commit -m "feat: clasificación de empresas contra el board de Cuentas de Monday"
```

---

### Task 3: `utils.py` — extender `fila_contacto()` con datos de cuenta/empresa

**Files:**
- Modify: `utils.py:82-108` (función `fila_contacto`)
- Modify: `config.py` (`COLUMNAS_CONTACTO_INTERNAS`)

**Interfaces:**
- Consumes: nada nuevo.
- Produces: `fila_contacto(..., cuenta_item_id=None, sector_empresa=None, personal_estimado_empresa=None, tamano_empresa=None, sitio_web_empresa=None, correo_empresa=None)` — agrega las claves `"Cuenta item id"`, `"Sector empresa"`, `"Personal estimado empresa"`, `"Tamaño empresa"`, `"Sitio web empresa"`, `"Correo empresa"` al dict devuelto. El Task 4 (`monday_crear_cuenta`) y el Task 8 (`dialog_exportar_monday`) leen esas claves.

No hace falta TDD acá — es una extensión de firma de una función ya usada en producción, sin lógica nueva que valga la pena testear por separado (los valores se pasan tal cual, sin transformación). Se verifica junto con el resto del pipeline en el Task 7.

- [ ] **Step 1: Extender `fila_contacto` en `utils.py`**

Reemplazar la función completa (líneas 82-108):

```python
def fila_contacto(
    razon_social, nombre, correo, telefono_empresa, cargo, linkedin, es_principal,
    estado_correo=None, score_correo=None, confianza_correo=None, fuente=None, sources=None,
    cuenta_item_id=None, sector_empresa=None, personal_estimado_empresa=None,
    tamano_empresa=None, sitio_web_empresa=None, correo_empresa=None,
):
    """Arma una fila de contacto con el esquema del board de Monday (ver
    contacto.md) + columnas propias de diagnóstico al final. Las columnas
    'Cuenta item id'/'... empresa' no se mandan al board de Contacto —
    viajan para poder crear la cuenta en Monday (monday_crear_cuenta) si
    hace falta al momento de exportar (ver cuentas.py)."""
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
        "Cuenta item id": cuenta_item_id,
        "Sector empresa": sector_empresa,
        "Personal estimado empresa": personal_estimado_empresa,
        "Tamaño empresa": tamano_empresa,
        "Sitio web empresa": sitio_web_empresa,
        "Correo empresa": correo_empresa,
    }
```

- [ ] **Step 2: Agregar las columnas nuevas a `COLUMNAS_CONTACTO_INTERNAS` en `config.py`**

```python
COLUMNAS_CONTACTO_INTERNAS = [
    "Es principal", "Estado del correo", "Score del correo", "Confianza del correo",
    "Fuente", "Fuentes del correo", "Cuenta item id", "Sector empresa",
    "Personal estimado empresa", "Tamaño empresa", "Sitio web empresa", "Correo empresa",
]
```

- [ ] **Step 3: Verificar que la app sigue arrancando**

Run: `streamlit run app.py --server.headless true &` y luego `curl -s -o /dev/null -w "%{http_code}" http://localhost:8501` (o simplemente abrir la app y confirmar que no tira `TypeError` al cargar — todos los `fila_contacto(...)` existentes siguen siendo válidos porque los parámetros nuevos tienen default `None`).
Expected: la pestaña "Búsqueda"/"Datos limpios" carga sin error (las pestañas de Enriquecimiento/Monday recién se tocan en los tasks 6-8).

- [ ] **Step 4: Commit**

```bash
git add utils.py config.py
git commit -m "feat: fila_contacto lleva datos de cuenta/empresa para crear la cuenta en Monday al exportar"
```

---

### Task 4: `cuentas.py` — perfil desde Monday + integración con la API real

**Files:**
- Modify: `cuentas.py`
- Modify: `tests/test_cuentas.py`

**Interfaces:**
- Consumes: `monday_graphql` de `monday.py` (`monday_graphql(query, variables=None) -> dict`, ya existente); `MONDAY_BOARD_CUENTAS`, `MONDAY_COLUMNAS_CUENTAS`, `MONDAY_BOARD_CONTACTO`, `MONDAY_COLUMNAS_CONTACTO`, `ESTADOS_CONTACTO_EXITOSO` de `config.py` (Task 1); `_telefono_mx`, `_valor_valido` de `utils.py`.
- Produces: `perfil_desde_cuenta(cuenta_monday) -> dict` (mismo esquema que `EnriquecimientoEmpresa.model_dump()` de `enrichment.py` — usada por el Task 7); `monday_listar_cuentas_reales() -> dict` (usada por los Tasks 6 y 7); `monday_crear_cuenta(fila) -> str` (item_id nuevo, usada por el Task 8). `fila` es una fila de `df_contactos` con las claves que agregó el Task 3.

- [ ] **Step 1: Escribir el test de `perfil_desde_cuenta` que falla**

Agregar a `tests/test_cuentas.py`:

```python
from cuentas import perfil_desde_cuenta


def test_perfil_desde_cuenta_usa_pagina_web_y_tamano():
    cuenta_monday = {
        "item_id": "111", "pagina_web": "https://empresa.com",
        "cantidad_empleados": "300", "tamano": "Grande",
    }
    perfil = perfil_desde_cuenta(cuenta_monday)
    assert perfil["sitio_web"] == "https://empresa.com"
    assert "300" in perfil["empleados_linkedin"]
    assert "Grande" in perfil["empleados_linkedin"]
    assert perfil["linkedin_url"] is None
    assert perfil["actividad_reciente"] is False
    assert perfil["senales_riesgo"] is False
    assert perfil["confianza_coincidencia"] == "alta"
    assert "Monday" in perfil["evidencia"]


def test_perfil_desde_cuenta_sin_datos_no_rompe():
    perfil = perfil_desde_cuenta({"item_id": "222"})
    assert perfil["sitio_web"] is None
    assert perfil["empleados_linkedin"] is None
```

Run: `pytest tests/test_cuentas.py -v`
Expected: FAIL — `ImportError: cannot import name 'perfil_desde_cuenta'`

- [ ] **Step 2: Implementar `perfil_desde_cuenta`**

Agregar a `cuentas.py`:

```python
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
        "contacto_rrhh": None,
        "contacto_rrhh_url": None,
        "confianza_coincidencia": "alta",
        "evidencia": (
            "Perfil tomado del board de Cuentas en Monday (cuenta ya existente) "
            "— no se re-enriqueció con búsqueda web."
        ),
    }
```

- [ ] **Step 3: Correr los tests y verificar que pasan**

Run: `pytest tests/test_cuentas.py -v`
Expected: PASS (7 tests)

- [ ] **Step 4: Implementar la integración con Monday (I/O, sin test automatizado)**

Sin tests automatizados para estas — mismo criterio que `monday.py` hoy (ninguna de sus funciones de I/O tiene test), se verifican a mano en el Step 5. Agregar a `cuentas.py`:

```python
import json
from datetime import date

from config import (
    ESTADOS_CONTACTO_EXITOSO,
    MONDAY_BOARD_CONTACTO,
    MONDAY_BOARD_CUENTAS,
    MONDAY_COLUMNAS_CONTACTO,
    MONDAY_COLUMNAS_CUENTAS,
)
from monday import monday_graphql
from utils import _telefono_mx, _valor_valido

import streamlit as st


def _linked_item_ids(column_value_json):
    """Parsea el 'value' crudo de una columna de vínculo entre boards
    (board_relation) — devuelve una lista de item_ids como str, [] si no
    hay vínculos. Shape confirmado empíricamente en el Task 1: si Monday
    devuelve otra clave que no sea 'linkedPulseIds', ajustar acá."""
    if not column_value_json:
        return []
    datos = json.loads(column_value_json)
    return [str(v["linkedPulseId"]) for v in (datos.get("linkedPulseIds") or [])]


def _estados_contacto_por_cuenta():
    """{cuenta_item_id (str): set(labels de 'Estado')} de todos los
    contactos del board de Contacto que ya tienen una cuenta vinculada —
    bulk, mismo patrón de paginación que monday_listar_cuentas() en
    monday.py."""
    columna_cuenta = MONDAY_COLUMNAS_CONTACTO["Cuenta asociada"]
    columna_estado = MONDAY_COLUMNAS_CONTACTO["Estado"]
    estados_por_cuenta = {}

    def _sumar(items):
        for item in items:
            valores = {cv["id"]: cv for cv in item["column_values"]}
            for cuenta_id in _linked_item_ids(valores[columna_cuenta]["value"]):
                estados_por_cuenta.setdefault(cuenta_id, set())
                etiqueta = valores[columna_estado]["text"]
                if etiqueta:
                    estados_por_cuenta[cuenta_id].add(etiqueta)

    query_inicial = """
    query ($boardId: ID!, $columnaIds: [String!]) {
      boards(ids: [$boardId]) {
        items_page(limit: 100) {
          cursor
          items { column_values(ids: $columnaIds) { id text value } }
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
        items { column_values(ids: $columnaIds) { id text value } }
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
    Cuentas real. Cacheada sin TTL, refresco manual (mismo patrón que
    monday_listar_cuentas() en monday.py)."""
    columnas_a_leer = ["Convenios", "Página web", "Cantidad de empleados", "Tamaño"]
    ids_columnas = [MONDAY_COLUMNAS_CUENTAS[c] for c in columnas_a_leer]
    cuentas = {}

    def _sumar(items):
        for item in items:
            valores = {cv["id"]: cv for cv in item["column_values"]}
            nombre_normalizado = item["name"].strip().lower()
            cuentas[nombre_normalizado] = {
                "item_id": item["id"],
                "tiene_convenio": len(_linked_item_ids(valores[MONDAY_COLUMNAS_CUENTAS["Convenios"]]["value"])) > 0,
                "pagina_web": valores[MONDAY_COLUMNAS_CUENTAS["Página web"]]["text"] or None,
                "cantidad_empleados": valores[MONDAY_COLUMNAS_CUENTAS["Cantidad de empleados"]]["text"] or None,
                "tamano": valores[MONDAY_COLUMNAS_CUENTAS["Tamaño"]]["text"] or None,
            }

    query_inicial = """
    query ($boardId: ID!, $columnaIds: [String!]) {
      boards(ids: [$boardId]) {
        items_page(limit: 100) {
          cursor
          items { id name column_values(ids: $columnaIds) { id text value } }
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
        items { id name column_values(ids: $columnaIds) { id text value } }
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
    real creado."""
    columnas = MONDAY_COLUMNAS_CUENTAS
    valores = {}
    if _valor_valido(fila.get("Sector empresa")):
        valores[columnas["Sector"]] = {"label": fila["Sector empresa"]}
    if _valor_valido(fila.get("Personal estimado empresa")):
        valores[columnas["Cantidad de empleados"]] = str(fila["Personal estimado empresa"])
    if _valor_valido(fila.get("Tamaño empresa")):
        valores[columnas["Tamaño"]] = {"label": fila["Tamaño empresa"]}
    if _valor_valido(fila.get("Correo empresa")):
        correo = fila["Correo empresa"]
        valores[columnas["E-Mail"]] = {"email": correo, "text": correo}
    telefono = _telefono_mx(fila.get("Teléfono (empresa)"))
    if telefono:
        valores[columnas["Teléfono"]] = {"phone": telefono, "countryShortName": "MX"}
    if _valor_valido(fila.get("Sitio web empresa")):
        sitio = fila["Sitio web empresa"]
        valores[columnas["Página web"]] = {"url": sitio, "text": sitio}
    valores[columnas["País"]] = "México"
    valores[columnas["Fecha de inicio"]] = {"date": date.today().isoformat()}

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
```

- [ ] **Step 5: Verificación manual contra el board de prueba real**

Con `MONDAY_API_KEY` ya apuntando al tablero de prueba nuevo, correr en una consola de Python (`python -i`, o un script descartable):

```python
from cuentas import monday_listar_cuentas_reales
cuentas = monday_listar_cuentas_reales()
print(len(cuentas), list(cuentas.items())[:2])
```

Confirmar que devuelve un dict no vacío (si el board de prueba ya tiene al menos una cuenta cargada) y que `tiene_convenio`/`tiene_contacto_exitoso` reflejan lo que hay realmente cargado en Monday para esa cuenta. Si el board de prueba está vacío, crear una cuenta de prueba a mano en Monday primero. Si algo no coincide con lo esperado, revisar el shape confirmado en el Task 1, Step 4, antes de seguir.

- [ ] **Step 6: Commit**

```bash
git add cuentas.py tests/test_cuentas.py
git commit -m "feat: integración con el board de Cuentas real de Monday (listar, perfil, crear)"
```

---

### Task 5: `monday.py` — vincular contacto↔cuenta con `board_relation` real

**Files:**
- Modify: `monday.py`

**Interfaces:**
- Consumes: `MONDAY_COLUMNAS_CUENTAS`... no — este task no necesita Cuentas, solo escribe en Contacto. Consume `MONDAY_COLUMNAS_CONTACTO["Cuenta asociada"]` (ya existente, ahora apuntando al column_id real de tipo vínculo, del Task 1).
- Produces: `monday_crear_contacto(fila, cuenta_item_id, responsable_id=None)` — firma cambiada (nuevo parámetro posicional `cuenta_item_id`, obligatorio). Usada por el Task 8 (`dialog_exportar_monday`).

- [ ] **Step 1: Cambiar `monday_crear_contacto` para escribir un vínculo real**

En `monday.py`, reemplazar las líneas 111-118 (inicio de la función, hasta el armado de `valores`):

```python
def monday_crear_contacto(fila, cuenta_item_id, responsable_id=None):
    """Crea un item en el board de Contacto a partir de una fila con el
    esquema de COLUMNAS_CONTACTO_MONDAY. 'cuenta_item_id' es el item_id
    real de la cuenta en el board de Cuentas (ver cuentas.py) — se linkea
    con un board_relation real, no con texto. 'Estado' queda en
    'Contactado' — se llama a esta función solo al exportar un contacto ya
    contactado. 'responsable_id' es el ID real de un usuario de Monday (ver
    monday_listar_usuarios), no un nombre — se omite si no se pasa."""
    columnas = dict(MONDAY_COLUMNAS_CONTACTO)
    valores = {columnas["Cuenta asociada"]: {"item_ids": [int(cuenta_item_id)]}}
```

El resto de la función (líneas 120-176 del archivo original) queda igual — solo cambió cómo se arma el valor de "Cuenta asociada".

- [ ] **Step 2: Eliminar `monday_listar_cuentas()`, ya sin uso**

Esta función quedó reemplazada por `monday_listar_cuentas_reales()` de `cuentas.py` (Task 4) — el Task 6 deja de llamarla. Borrar de `monday.py` la función completa `monday_listar_cuentas()` (el bloque decorado con `@st.cache_data(show_spinner="Consultando empresas ya cargadas en Monday...")`, desde su docstring hasta el `return cuentas` final).

- [ ] **Step 3: Verificación manual**

No se puede probar `monday_crear_contacto` de punta a punta sin datos personales reales (correo real) — según la práctica ya usada en este proyecto para este caso: reemplazar temporalmente el cuerpo de `monday_crear_contacto` por una versión que solo arma y devuelve `valores` (sin llamar a `monday_graphql`), correr:

```python
from monday import monday_crear_contacto
fila_prueba = {"Cuenta asociada": "Empresa Test", "Correo": None, "Nombre": "Test", "Teléfono (empresa)": None, "País": "México", "Nombre de cargo": None, "Fuente": None, "Nivel de cargo": None, "Link de LinkedIn": None, "Fecha de inicio": "2026-09-09"}
print(monday_crear_contacto(fila_prueba, cuenta_item_id="123456"))
```

Confirmar que el dict de `valores` arma `{"<column_id de Cuenta asociada>": {"item_ids": [123456]}}` correctamente, después restaurar el cuerpo real de la función (con una copia de respaldo hecha antes de este paso).

- [ ] **Step 4: Commit**

```bash
git add monday.py
git commit -m "feat: monday_crear_contacto vincula la cuenta real (board_relation) en vez de texto"
```

---

### Task 6: `app.py` — Etapa 3: clasificación en 3 grupos contra Cuentas

**Files:**
- Modify: `app.py:12-40` (imports)
- Modify: `app.py:343-367` (bloque "Etapa 3 — Descarte de duplicados contra Monday")

**Interfaces:**
- Consumes: `clasificar_cuentas`, `monday_listar_cuentas_reales` de `cuentas.py` (Tasks 2 y 4); `MONDAY_BOARD_CUENTAS` de `config.py` (Task 1).
- Produces: variables locales `cuentas_reales` (dict), `df_etapa4` (con columna `Cuenta_item_id`, `NaN`/valor real) — consumidas por el Task 7.

- [ ] **Step 1: Actualizar imports en `app.py`**

Reemplazar la línea `from monday import monday_correo_existe, monday_crear_contacto, monday_listar_cuentas, monday_listar_usuarios` por:

```python
from cuentas import clasificar_cuentas, monday_crear_cuenta, monday_listar_cuentas_reales
from monday import monday_correo_existe, monday_crear_contacto, monday_listar_usuarios
```

Y agregar `MONDAY_BOARD_CUENTAS` al import existente de `config` (junto a `MONDAY_API_KEY`).

- [ ] **Step 2: Reemplazar el bloque de la Etapa 3**

Reemplazar las líneas 343-367 (todo el `with st.container(border=True):` de "Etapa 3 — Descarte de duplicados contra Monday") por:

```python
    cuentas_reales = {}
    with st.container(border=True):
        st.markdown("**Etapa 3 — Clasificación contra el board de Cuentas**")
        if not MONDAY_API_KEY or not MONDAY_BOARD_CUENTAS:
            st.warning("Falta MONDAY_API_KEY y/o MONDAY_BOARD_CUENTAS en el .env para comparar contra Monday.")
            df_etapa4 = df_etapa3.copy()
            df_etapa4["Cuenta_item_id"] = None
        else:
            if st.button("Actualizar cuentas de Monday", icon=":material/refresh:"):
                monday_listar_cuentas_reales.clear()
            try:
                cuentas_reales = monday_listar_cuentas_reales()
                st.caption(f"{len(cuentas_reales)} cuenta(s) ya cargadas en Monday (board de Cuentas).")
                df_nueva, df_existe_necesita_contacto, df_existe_gestionada = clasificar_cuentas(
                    df_etapa3, cuentas_reales
                )
                df_etapa4 = pd.concat([df_nueva, df_existe_necesita_contacto])
                if not df_existe_gestionada.empty:
                    with st.expander(
                        f"Ver {len(df_existe_gestionada)} empresa(s) descartadas — ya tienen convenio o "
                        "contacto exitoso en Monday"
                    ):
                        st.dataframe(
                            df_existe_gestionada[["Razon_social", "Sucursales", "Personal_estimado", "Banda_total"]],
                            hide_index=True,
                        )
                if not df_existe_necesita_contacto.empty:
                    st.caption(
                        f"{len(df_existe_necesita_contacto)} empresa(s) ya existen en Monday pero sin "
                        "convenio ni contacto exitoso — se les busca contacto sin re-enriquecer perfil."
                    )
            except Exception as exc:
                st.error(f"No se pudo consultar Monday: {exc}")
                df_etapa4 = df_etapa3.copy()
                df_etapa4["Cuenta_item_id"] = None
```

El resto de `tab_limpios` (métricas, `df_final`, descarga CSV) sigue exactamente igual — sigue leyendo `df_etapa4` como antes, ahora con la columna extra `Cuenta_item_id` (que `COLUMNAS_LIMPIAS` no incluye, así que no aparece en `df_final`, sin cambios ahí).

- [ ] **Step 3: Verificación manual**

Correr `streamlit run app.py`, hacer una búsqueda chica (un sector/estado con pocos resultados), y en la pestaña "Datos limpios" confirmar: (a) si `MONDAY_BOARD_CUENTAS` está seteado, aparece "Etapa 3 — Clasificación contra el board de Cuentas" con el conteo de cuentas de Monday; (b) el expander de descartadas solo lista empresas con convenio o contacto exitoso reales (verificar contra lo que hay cargado en el board de prueba); (c) sin quebrar si `MONDAY_BOARD_CUENTAS` está vacío en `.env` (fallback a warning, `df_etapa4 = df_etapa3` con `Cuenta_item_id` en `None`).

- [ ] **Step 4: Commit**

```bash
git add app.py
git commit -m "feat: Etapa 3 clasifica contra el board de Cuentas en vez de descartar por texto"
```

---

### Task 7: `app.py` — Enriquecimiento: bypass para cuentas existentes + threading de `Cuenta_item_id`

**Files:**
- Modify: `app.py:12-40` (imports)
- Modify: `app.py:405-495` (bloque de enriquecimiento, dentro de `tab_enriquecimiento`)
- Modify: `app.py:602-625` (llamadas a `fila_contacto` en Grupo A)
- Modify: `app.py:684-702` (llamadas a `fila_contacto` en Grupo B)

**Interfaces:**
- Consumes: `perfil_desde_cuenta` de `cuentas.py` (Task 4); `cuentas_reales`, `df_etapa4` (con `Cuenta_item_id`) del Task 6.
- Produces: `st.session_state["df_enriquecido"]` con columna `Cuenta_item_id`; `st.session_state["df_contactos"]` con las columnas nuevas de `fila_contacto` (Task 3) pobladas — consumido por el Task 8.

- [ ] **Step 1: Importar `perfil_desde_cuenta`**

Agregar `perfil_desde_cuenta` al import ya existente de `cuentas` en `app.py` (junto a `clasificar_cuentas`, `monday_crear_cuenta`, `monday_listar_cuentas_reales`).

- [ ] **Step 2: Reemplazar el armado de `candidatas` y el bloque de enriquecimiento**

Reemplazar desde `_texto_cantidad = (` (línea 406) hasta el cierre del bloque `if st.button("Enriquecer estas empresas"...)` que arma `df_combinado` y lo guarda en `st.session_state["df_enriquecido"]` (hasta antes de `if "df_enriquecido" in st.session_state:`, línea 487) por:

```python
    df_nueva_etapa4 = df_etapa4[df_etapa4["Cuenta_item_id"].isna()]
    df_existe_etapa4 = df_etapa4[df_etapa4["Cuenta_item_id"].notna()]
    candidatas_nuevas = df_nueva_etapa4.head(N_EMPRESAS_ENRIQUECER)

    _texto_cantidad = (
        "solo la empresa nueva con más personal estimado"
        if N_EMPRESAS_ENRIQUECER == 1
        else f"solo las primeras {N_EMPRESAS_ENRIQUECER} empresas nuevas de más personal estimado"
    )
    st.caption(
        f"Prototipo: busca y analiza {_texto_cantidad} de \"Datos limpios\", para no "
        "consumir de más las búsquedas de SerpAPI/Anthropic. Las empresas que ya existen "
        "en Monday (sin convenio ni contacto exitoso) no se re-enriquecen — usan el perfil "
        "que ya está cargado en el board de Cuentas."
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
        st.caption(
            "Campos que se van a completar con la búsqueda (empresas nuevas): "
            + ", ".join(COLUMNAS_ENRIQUECIMIENTO.values()) + "."
        )
        st.markdown("**Datos actuales antes de enriquecer**")
        st.dataframe(df_final.head(N_EMPRESAS_ENRIQUECER), hide_index=True)
        if not df_existe_etapa4.empty:
            st.caption(
                f"{len(df_existe_etapa4)} empresa(s) ya existen en Monday — se procesan igual, "
                "sin re-enriquecer perfil."
            )

        if st.button("Enriquecer estas empresas", icon=":material/travel_explore:"):
            resultados_nuevas = []
            with st.status("Enriqueciendo empresas...", expanded=True) as status:
                for i, fila in enumerate(candidatas_nuevas.itertuples(), start=1):
                    status.update(label=f"Empresa {i} de {len(candidatas_nuevas)} — {fila.Razon_social}...")
                    try:
                        resultado = enriquecer_empresa(
                            fila.Razon_social,
                            fila.Clase_actividad,
                            fila.Ubicacion,
                            SERPAPI_KEY,
                            ANTHROPIC_API_KEY,
                        )
                        resultados_nuevas.append(resultado.model_dump())
                        st.write(f"✓ {fila.Razon_social} — coincidencia {resultado.confianza_coincidencia}")
                    except Exception as exc:
                        resultados_nuevas.append(None)
                        st.write(f"✗ {fila.Razon_social} — error: {exc}")

                resultados_existe = []
                for fila in df_existe_etapa4.itertuples():
                    cuenta_monday = cuentas_reales.get(str(fila.Razon_social).strip().lower())
                    if cuenta_monday:
                        resultados_existe.append(perfil_desde_cuenta(cuenta_monday))
                        st.write(f"✓ {fila.Razon_social} — perfil tomado de Monday (cuenta existente)")
                    else:
                        resultados_existe.append(None)
                        st.write(f"✗ {fila.Razon_social} — no se encontró el registro de Monday (inesperado)")
                status.update(label="Enriquecimiento completo", state="complete")

            bloques = []
            for indice_grupo, resultados in (
                (candidatas_nuevas.index, resultados_nuevas),
                (df_existe_etapa4.index, resultados_existe),
            ):
                validas = [(idx, r) for idx, r in zip(indice_grupo, resultados) if r is not None]
                if not validas:
                    continue
                indices_validos, datos = zip(*validas)
                base = df_final.loc[list(indices_validos)].reset_index(drop=True)
                base["Cuenta_item_id"] = df_etapa4.loc[list(indices_validos), "Cuenta_item_id"].values
                enriquecido = pd.DataFrame(list(datos)).rename(columns=COLUMNAS_ENRIQUECIMIENTO)
                bloques.append(pd.concat([base, enriquecido], axis=1))

            if bloques:
                df_combinado = pd.concat(bloques, ignore_index=True)

                # El sitio del DENUE puede estar vacío o desactualizado (dominio que ya
                # no responde). Si no pasa el chequeo directo, se trata como si no
                # existiera y se completa con el que encontró la búsqueda de SerpAPI
                # (o el de Monday, para cuentas existentes — viaja en la misma columna).
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
                            "SerpAPI/Monday (DENUE vacío)" if not sitio_denue else "SerpAPI/Monday (el del DENUE no responde)"
                        )
                    else:
                        sitios_finales.append("")
                        fuentes_sitio.append("Sin sitio verificado")
                df_combinado["Sitio web"] = sitios_finales
                df_combinado["Fuente sitio web"] = fuentes_sitio

                st.session_state["df_enriquecido"] = df_combinado
```

- [ ] **Step 3: Threading de `Cuenta_item_id` y datos de empresa en Grupo A**

En el loop de Grupo A (dentro de `if verificar:`), agregar los kwargs nuevos a los 3 llamados a `fila_contacto(...)`:

Llamado del contacto principal (línea ~602):

```python
                                filas_contactos.append(fila_contacto(
                                    fila["Razón social"], nombre_contacto, correo, fila["Teléfono"],
                                    cargo_contacto, linkedin_contacto, es_principal=True,
                                    estado_correo=verificacion["estado"], score_correo=score_final,
                                    confianza_correo=confianza_final, fuente=fuente_contacto,
                                    cuenta_item_id=fila["Cuenta_item_id"],
                                    sector_empresa=fila["Actividad económica"],
                                    personal_estimado_empresa=fila["Personal estimado"],
                                    tamano_empresa=fila["Banda de tamaño"],
                                    sitio_web_empresa=fila["Sitio web"],
                                    correo_empresa=fila["Correo"],
                                ))
```

Llamado de contacto alternativo (línea ~612):

```python
                                for contacto_alt in contactos_fallback:
                                    hallazgo_alt = hunter_buscar_email(dominio, contacto_alt.nombre, HUNTER_API_KEY)
                                    if hallazgo_alt and hallazgo_alt["email"] != correo:
                                        filas_contactos.append(fila_contacto(
                                            fila["Razón social"], contacto_alt.nombre, hallazgo_alt["email"],
                                            fila["Teléfono"], contacto_alt.cargo, contacto_alt.linkedin_url,
                                            es_principal=False, score_correo=hallazgo_alt["score"],
                                            fuente="Búsqueda por rol",
                                            sources="; ".join(hallazgo_alt["sources"]) if hallazgo_alt["sources"] else None,
                                            cuenta_item_id=fila["Cuenta_item_id"],
                                            sector_empresa=fila["Actividad económica"],
                                            personal_estimado_empresa=fila["Personal estimado"],
                                            tamano_empresa=fila["Banda de tamaño"],
                                            sitio_web_empresa=fila["Sitio web"],
                                            correo_empresa=fila["Correo"],
                                        ))
```

Llamado de Hunter domain search (línea ~620):

```python
                                for otro in hunter_correos_del_dominio(dominio, HUNTER_API_KEY):
                                    filas_contactos.append(fila_contacto(
                                        fila["Razón social"], otro["nombre"], otro["correo"], fila["Teléfono"],
                                        otro["cargo"], otro["linkedin"], es_principal=False,
                                        score_correo=otro["confianza"], fuente="Hunter domain search",
                                        cuenta_item_id=fila["Cuenta_item_id"],
                                        sector_empresa=fila["Actividad económica"],
                                        personal_estimado_empresa=fila["Personal estimado"],
                                        tamano_empresa=fila["Banda de tamaño"],
                                        sitio_web_empresa=fila["Sitio web"],
                                        correo_empresa=fila["Correo"],
                                    ))
```

- [ ] **Step 4: Threading de `Cuenta_item_id` y datos de empresa en Grupo B**

Llamado de candidatos (línea ~684):

```python
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
                                            cuenta_item_id=fila["Cuenta_item_id"],
                                            sector_empresa=fila["Actividad económica"],
                                            personal_estimado_empresa=fila["Personal estimado"],
                                            tamano_empresa=fila["Banda de tamaño"],
                                            sitio_web_empresa=fila["Sitio web"],
                                            correo_empresa=fila["Correo"],
                                        ))
```

Llamado de Hunter domain search (línea ~697):

```python
                                if dominio:
                                    for otro in hunter_correos_del_dominio(dominio, HUNTER_API_KEY):
                                        filas_contactos.append(fila_contacto(
                                            razon, otro["nombre"], otro["correo"], fila["Teléfono"],
                                            otro["cargo"], otro["linkedin"], es_principal=False,
                                            score_correo=otro["confianza"], fuente="Hunter domain search",
                                            cuenta_item_id=fila["Cuenta_item_id"],
                                            sector_empresa=fila["Actividad económica"],
                                            personal_estimado_empresa=fila["Personal estimado"],
                                            tamano_empresa=fila["Banda de tamaño"],
                                            sitio_web_empresa=fila["Sitio web"],
                                            correo_empresa=fila["Correo"],
                                        ))
```

- [ ] **Step 5: Verificación manual**

Correr `streamlit run app.py`, en "Datos limpios" dejar pasar al menos una empresa nueva y (si el board de prueba ya tiene alguna cuenta sin convenio/contacto exitoso cargada con el mismo nombre que algo del DENUE) una empresa existente. En "Enriquecimiento": confirmar que la empresa nueva pasa por SerpAPI+Claude como antes (ver el log `✓ ... — coincidencia ...`) y la existente aparece con `✓ ... — perfil tomado de Monday`, sin llamar a SerpAPI para esa fila. Confirmar que `st.session_state["df_enriquecido"]` (visible en el `st.dataframe` de la pestaña) tiene datos razonables para ambas. Correr "Verificar y buscar contactos" y confirmar en el CSV descargado que las columnas `Cuenta item id`, `Sector empresa`, etc. tienen valores (no todas vacías).

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: enriquecimiento salta re-enriquecer cuentas existentes y propaga Cuenta_item_id"
```

---

### Task 8: `app.py` — export de 2 pasos (crear cuenta si falta + contacto vinculado)

**Files:**
- Modify: `app.py:59-80` (`dialog_exportar_monday`)

**Interfaces:**
- Consumes: `monday_crear_cuenta` de `cuentas.py` (Task 4); `monday_crear_contacto(fila, cuenta_item_id, responsable_id=None)` de `monday.py` (Task 5); columna `"Cuenta item id"` de `df_contactos` (Task 3/7).
- Produces: comportamiento final visible al usuario — export con confirmación crea la cuenta en Monday si hace falta, antes del contacto.

- [ ] **Step 1: Reemplazar `dialog_exportar_monday`**

Reemplazar la función completa (líneas 59-80):

```python
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
                    cuenta_item_id = fila["Cuenta item id"]
                    if not _valor_valido(cuenta_item_id):
                        cuenta_item_id = monday_crear_cuenta(fila)
                        st.session_state["df_contactos"].loc[idx, "Cuenta item id"] = cuenta_item_id
                    monday_crear_contacto(fila, cuenta_item_id, responsable_id=responsable_id)
                    st.session_state["_monday_aviso"] = ("success", f"{etiqueta} exportado correctamente.")
                st.session_state["df_contactos"].loc[idx, "Exportado a Monday"] = True
            except Exception as exc:
                st.session_state["_monday_aviso"] = ("error", f"{etiqueta} — error al exportar: {exc}")
            st.rerun()
    with col_no:
        if st.button("Cancelar", key=f"dialog_no_{idx}"):
            st.rerun()
```

Único cambio real: si `fila["Cuenta item id"]` está vacío, se crea la cuenta primero (`monday_crear_cuenta`) y se guarda el `item_id` devuelto en `df_contactos` antes de crear el contacto — así si el mismo `st.rerun()` vuelve a pasar por acá (no debería, pero por las dudas) no se duplica la cuenta.

- [ ] **Step 2: Verificación manual (con datos ficticios, no reales)**

Según la práctica ya usada en este proyecto para pruebas que tocan datos personales/de negocio reales: hacer una copia de respaldo de `app.py`, reemplazar temporalmente `monday_crear_cuenta` y `monday_crear_contacto` (en el import o con un monkeypatch al principio del script) por versiones que solo imprimen sus argumentos y devuelven un id ficticio, correr la app, generar un contacto de una empresa nueva (sin `Cuenta item id`), exportarlo, y confirmar en la consola que:
1. Se llama primero a la versión falsa de `monday_crear_cuenta` con los datos de la fila.
2. Se llama después a la versión falsa de `monday_crear_contacto` con el `cuenta_item_id` devuelto por el paso anterior.
3. `df_contactos` queda con `Exportado a Monday = True` y `Cuenta item id` poblado.

Restaurar `app.py` desde la copia de respaldo al terminar. Después, con el board de prueba nuevo y datos ficticios propios (no de una persona/empresa real), probar el flujo de punta a punta una vez contra Monday de verdad y confirmar en la UI de Monday que la cuenta y el contacto quedaron creados y vinculados (columna "Cuenta asociada" del contacto muestra la cuenta real, no texto suelto).

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: exportar un pre-lead crea la cuenta en Monday si hace falta, antes del contacto"
```

---

## Self-Review

**Spec coverage:**
- Clasificación en 3 grupos (nueva/existe-necesita-contacto/existe-gestionada) → Tasks 2 y 6.
- Bypass de enriquecimiento para cuentas existentes → Task 7.
- Pre-leads de cuenta + contacto vinculados con `board_relation` real, export manual con confirmación → Tasks 3, 4, 5, 8.
- Verificación empírica antes de codear (Monday) → Task 1, y notas de "ajustar si difiere" en los Tasks 4 y 5.
- Config nueva (`MONDAY_BOARD_CUENTAS`, `MONDAY_COLUMNAS_CUENTAS`, `ESTADOS_CONTACTO_EXITOSO`) → Task 1.
- Manejo de errores fail-per-item / no crear contacto sin cuenta → Task 8 (la excepción de `monday_crear_cuenta` corta el `try` antes de llegar a `monday_crear_contacto`, y queda registrada como error de esa fila puntual, sin cortar el resto del panel).

**Placeholder scan:** sin `TBD`/`TODO` en ningún step; el único dato no fijado de antemano son los IDs reales de Monday, resueltos por el propio Task 1 (acción con pasos concretos, no un placeholder oculto) y consumidos como constantes reales desde el Task 4 en adelante.

**Type consistency:** `clasificar_cuentas` (Task 2) y `monday_listar_cuentas_reales` (Task 4) coinciden en el shape del dict `cuentas_reales` (`item_id`, `tiene_convenio`, `tiene_contacto_exitoso` — Task 4 agrega además `pagina_web`/`cantidad_empleados`/`tamano`, que Task 2 no necesita pero tampoco rompe). `fila_contacto` (Task 3) y `monday_crear_cuenta`/`dialog_exportar_monday` (Tasks 4 y 8) coinciden en las claves `"Cuenta item id"`, `"Sector empresa"`, `"Personal estimado empresa"`, `"Tamaño empresa"`, `"Sitio web empresa"`, `"Correo empresa"`. `monday_crear_contacto(fila, cuenta_item_id, responsable_id=None)` tiene la misma firma en el Task 5 (definición) y el Task 8 (uso).

**Scope check:** un solo subsistema (clasificación + creación de cuentas vinculadas), plan ejecutable de punta a punta sin depender de otro plan aparte.
