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
    "Fuente", "Fuentes del correo",
]
# Marcado manual en el panel de gestión — no se envía a Monday tal cual, pilotea
# si/cómo se exporta cada fila.
COLUMNAS_CONTACTO_GESTION = ["Contactado", "No existe / desvinculado", "Exportado a Monday"]
