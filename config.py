"""
Configuración central: variables de entorno, claves de API, URLs y
constantes de negocio compartidas entre los módulos de integración y la UI.

Los módulos de integración (denue.py, enrichment.py, hunter.py, monday.py)
no leen variables de entorno directamente — las claves viven acá para que
quede claro, en un solo lugar, qué necesita cada servicio externo.
"""
import os

import streamlit as st
from dotenv import load_dotenv

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
# Board "Contactos" (workspace "Pruebas IA", id 17441169) — IDs de columna
# reales confirmados empíricamente contra la API (ver Task 1 del plan de
# tablero de cuentas). OJO: en este board TODAS las columnas de texto
# originales (incluida "Estado") son de type "text" simple, sin labels
# configurados del lado de Monday — ver la nota al inicio de
# structuraContacto.md.
# "Cuenta asociada" apunta a la columna "Cuenta vinculada", creada después
# de Task 1 como board_relation real (Contactos -> Cuentas) porque el board
# de prueba no traía ninguna columna de vínculo nativo — la columna de texto
# original "Cuenta asociada" (text_mm71b8fe) queda sin usar por este código
# (ver también la nota al inicio de structuraContacto.md).
MONDAY_BOARD_CONTACTO = "18430360621"
MONDAY_COLUMNAS_CONTACTO = {
    "Cuenta asociada": "board_relation_mm725nna",
    "Correo": "text_mm717z2r",
    "Teléfono (empresa)": "text_mm714vte",
    "Extensión": "text_mm71vz61",
    "País": "text_mm7173en",
    "Nivel de cargo": "text_mm71gzey",
    "Nombre de cargo": "text_mm715hwe",
    "Link de LinkedIn": "text_mm71cj9k",
    "Rol en la decisión": "text_mm718qtq",
    "Estado": "text_mm719jdf",
    "Fecha de inicio": "text_mm71n8qa",
    "Responsable": "text_mm71erf3",
}
# Board "Cuentas" (tablero real de prueba, workspace "Pruebas IA", id
# 17441169) — IDs de columna confirmados empíricamente contra la API (ver
# Task 1 del plan de tablero de cuentas). "Convenios" apunta a la columna
# "Convenio vinculado", creada después de Task 1 como board_relation real
# (Cuentas -> board "Convenios", id 18430363328, también dentro de Pruebas
# IA) — la columna de texto original "Convenio asociado" (text_mm71gsya)
# queda sin usar por este código. Ver la nota al inicio de
# structuraCuentas.md para el detalle del board original 100% de texto.
MONDAY_BOARD_CUENTAS = "18430360623"
MONDAY_COLUMNAS_CUENTAS = {
    "Convenios": "board_relation_mm72x2xb",
    "Sector": "text_mm71vga2",
    "Cantidad de empleados": "text_mm714996",
    "Tamaño": "text_mm71ce60",
    "País": "text_mm71fen5",
    "Página web": "text_mm71tbvy",
    "E-Mail": "text_mm71ksmd",
    "Teléfono": "text_mm718nrr",
    "Fecha de inicio": "text_mm718xd5",
}
# Estados de MONDAY_COLUMNAS_CONTACTO["Estado"] que cuentan como gestión
# avanzada/exitosa — una cuenta con al menos un contacto en uno de estos
# estados no necesita más contactos nuevos (ver spec, sección 6).
# OJO: "Estado" es una columna type "text" simple, sin labels configurados
# del lado de Monday (settings_str vacío) — no hay validación de que el
# valor escrito coincida con uno de estos 8 estados, queda a cargo del
# código que escribe/lee esta columna (ver la nota al inicio de
# structuraContacto.md).
ESTADOS_CONTACTO_EXITOSO = {"Contactado", "Convenio firmado"}
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

BANDAS_TOTALES = [
    (1000, "1000 y más"),
    (250, "250 a 999"),
    (50, "50 a 249"),
    (0, "Hasta 49"),
]

# Local-parts típicos de un buzón institucional/funcional (no una persona) —
# buscar un contacto por rol para uno de estos correos vuelve vacío siempre,
# porque no hay una persona detrás, sino un área (ej. archivogeneral@dgsg.unam.mx).
LOCAL_PARTS_CORREO_GENERAL = {
    "info", "contacto", "ventas", "atencion", "atencionaclientes", "general",
    "archivo", "archivogeneral", "admin", "administracion", "recepcion",
    "soporte", "ayuda", "servicios", "tramites", "notificaciones",
    "correspondencia", "buzon", "informacion", "rrhh", "recursoshumanos",
}

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
    "Fuente", "Fuentes del correo", "Cuenta item id", "Sector empresa",
    "Personal estimado empresa", "Tamaño empresa", "Sitio web empresa", "Correo empresa",
]
# Marcado manual en el panel de gestión — no se envía a Monday tal cual, pilotea
# si/cómo se exporta cada fila.
COLUMNAS_CONTACTO_GESTION = ["Contactado", "No existe / desvinculado", "Exportado a Monday"]
