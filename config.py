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
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
HUNTER_API_KEY = os.getenv("HUNTER_API_KEY")
MONDAY_API_KEY = os.getenv("MONDAY_API_KEY")

BASE_URL = "https://www.inegi.org.mx/app/api/denue/v1/consulta/BuscarAreaActEstr"
SERPER_URL = "https://google.serper.dev/search"
HUNTER_URL = "https://api.hunter.io/v2"
MONDAY_URL = "https://api.monday.com/v2"
# Board "Contactos" (workspace "Pruebas IA", id 17441169) — IDs de columna
# re-confirmados empíricamente contra la API el 2026-09-22, tras un cambio
# de esquema en Monday: el board dejó de tener columnas "text" simples y
# pasó a tipos reales (email/phone/link/date/status/people/board_relation).
# Cada tipo requiere un shape de JSON distinto en column_values (verificado
# contra la doc oficial de Monday y con un create_item + lectura real de
# prueba, borrado después) — ver monday_crear_contacto() en monday.py.
# "Cuenta asociada" sigue siendo la misma columna board_relation real
# (Contactos -> Cuentas), sin cambios.
MONDAY_BOARD_CONTACTO = "18430360621"
MONDAY_COLUMNAS_CONTACTO = {
    "Cuenta asociada": "board_relation_mm725nna",
    "Correo": "email_mm7d3zqa",
    "Teléfono (empresa)": "phone_mm7d71wd",
    "Extensión": "text_mm71vz61",
    "País": "text_mm7173en",
    "Nivel de cargo": "color_mm7dp4ay",
    "Nombre de cargo": "text_mm715hwe",
    "Link de LinkedIn": "link_mm7dw301",
    "Rol en la decisión": "color_mm7dcr52",
    "Estado": "color_mm7dg76t",
    "Fecha de inicio": "date_mm7dcry0",
    "Responsable": "multiple_person_mm7datgq",
}
# Board "Cuentas" (tablero real de prueba, workspace "Pruebas IA", id
# 17441169) — IDs de columna re-confirmados empíricamente contra la API el
# 2026-09-22, mismo cambio de esquema que el board de Contacto: columnas de
# texto simple pasaron a tipos reales. "Categoria" y "Tamaño" ahora son
# columnas fórmula, calculadas por Monday (a partir de los 4 checkboxes y
# de "Cantidad de empleados" respectivamente) — el código NUNCA debe
# escribirlas, solo puede leerlas. "Convenio asociado" es ahora la columna
# board_relation real hacia el board "Convenios" (18430363328) — antes
# vivía bajo la clave "Convenios"; se renombró para que coincida con el
# título real en Monday. "Grupo Empresarial", "Contacto asociado",
# "Oportunidad asociada", "Responsable", "Plan ESG", "Documento ESG" y
# "Co-abridor" son ahora columnas tipadas reales (board_relation/people/
# status/file/dropdown) pero siguen sin automatizarse — decisión explícita
# de no automatizar (ver proyecto_schema_cuentas_29_campos en memoria);
# quedan mapeadas por si hace falta leerlas, pero monday_crear_cuenta() no
# les escribe nada.
MONDAY_BOARD_CUENTAS = "18430360623"
MONDAY_COLUMNAS_CUENTAS = {
    "Convenio asociado": "board_relation_mm7dxbap",
    "RFC/NIT/RUC": "text_mm71st8a",
    "Pertenece a algun grupo empresarial": "color_mm7dx7dg",
    "Grupo Empresarial": "board_relation_mm7ds0ae",
    "Contacto asociado": "board_relation_mm7dk68c",
    "Tipo": "color_mm7dzm8c",
    "Eventos": "boolean_mm7da3yj",
    "Empleabilidad": "boolean_mm7dsvgz",
    "Academico": "boolean_mm7dvs2d",
    "Relacionamiento y ventas": "boolean_mm7dhjs6",
    "Categoria": "formula_mm7dxzva",
    "Sector": "color_mm7dqw42",
    "Cantidad de empleados": "text_mm714996",
    "Tamaño": "formula_mm7dj04x",
    "Descripcion": "text_mm71thgp",
    "E-Mail": "email_mm7daqpm",
    "Teléfono": "phone_mm7dr75t",
    "Página web": "link_mm7d75bp",
    "País": "text_mm71fen5",
    "Responsable": "multiple_person_mm7d5v02",
    "Fecha de inicio": "date_mm7dbcyt",
    "Oportunidad asociada": "board_relation_mm7d2h1c",
    "Plan ESG": "color_mm7dynp6",
    "Documento ESG": "file_mm7dyde7",
    "Co-abridor": "dropdown_mm7d5758",
}
# Estados de MONDAY_COLUMNAS_CONTACTO["Estado"] que cuentan como gestión
# avanzada/exitosa — una cuenta con al menos un contacto en uno de estos
# estados no necesita más contactos nuevos (ver spec, sección 6). "Estado"
# es ahora una columna status real con labels fijos (Contactado, Nuevo, En
# gestion, No contactado, No interesado, No valido, Inactivo) — el label
# "Convenio firmado" que usaba esta constante antes ya no existe en el
# board real; decisión explícita del usuario (2026-09-22): solo
# "Contactado" cuenta como gestión exitosa por ahora.
ESTADOS_CONTACTO_EXITOSO = {"Contactado"}
MODELO_ENRIQUECIMIENTO = "claude-haiku-4-5"
ENTIDAD_TODOS = "00"
ESTRATO_TODOS = "0"
TAMANO_PAGINA = 5000
# Prototipo: solo se enriquece(n) la(s) N empresa(s) de mayor personal estimado,
# para no consumir de más las búsquedas de Serper/Anthropic — bajado a 1 para
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
    "sitio_web": "Sitio web (Serper)",
    "empleados_linkedin": "Empleados (LinkedIn/web)",
    "actividad_reciente": "Actividad reciente",
    "resumen_actividad": "Resumen actividad",
    "senales_riesgo": "Señal de riesgo",
    "resumen_riesgo": "Resumen riesgo",
    "confianza_coincidencia": "Confianza (coincide con la empresa)",
    "evidencia": "Evidencia",
    "tipo_empresa": "Tipo",
    "rfc": "RFC/NIT/RUC",
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
    "Sector_monday": "Sector (Monday)",
    "Tamano_monday": "Tamaño (Monday)",
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

# Tamaño para la columna 'Tamano' del board de Cuentas (Micro/Pequeña/
# Mediana/Grande) — cortes fijos (no por sector, a diferencia de los
# oficiales SE/INEGI) definidos por el usuario. (umbral, etiqueta): personal
# <= umbral cae en esa etiqueta; por encima del último, "Grande".
TAMANOS_MONDAY = [
    (10, "Micro"),
    (50, "Pequeña"),
    (250, "Mediana"),
]

# Sector SCIAN de 2 dígitos (ver catalogos.SECTORES_SCIAN) -> uno de los 25
# sectores del dropdown 'Sector' del board de Cuentas. Mapeo aproximado —
# varios sectores SCIAN combinan actividades que el dropdown separa (ver
# SECTOR_MONDAY_PALABRAS_CLAVE para los casos que sí se distinguen).
# "Servicios" es el catch-all para sectores SCIAN sin una categoría más
# específica en el dropdown (electricidad/agua/gas, corporativos, apoyo a
# negocios, otros servicios). "Sector" es una columna status real en
# Monday, y sus labels reales vienen SIN acentos (confirmado empíricamente
# 2026-09-22) — estos valores deben matchear exacto o Monday crea un label
# nuevo duplicado en vez de usar el existente.
SECTOR_MONDAY_POR_SCIAN = {
    "11": "Agricultura",
    "21": "Mineria",
    "22": "Servicios",
    "23": "Construccion",
    "31": "Manufactura/ Transformacion de productos",
    "32": "Manufactura/ Transformacion de productos",
    "33": "Manufactura/ Transformacion de productos",
    "43": "Comercio",
    "46": "Comercio",
    "48": "Transporte",
    "49": "Transporte",
    "51": "Tecnologia",
    "52": "Financiero",
    "53": "Inmobiliaria",
    "54": "Profesional",
    "55": "Servicios",
    "56": "Servicios",
    "61": "Educativo",
    "62": "Salud",
    "71": "Entretenimiento",
    "72": "Turismo",
    "81": "Servicios",
    "93": "Gobierno",
}

# Se prueban ANTES del mapeo por SCIAN, sobre el texto de Clase_actividad en
# minúsculas — capturan sub-sectores que el dropdown de Monday separa pero
# el SCIAN de 2 dígitos no distingue (ej. "Automotriz" es una porción de
# "31-33 Industrias manufactureras"). La primera clave que matchea gana.
SECTOR_MONDAY_PALABRAS_CLAVE = [
    (("automotriz", "automotor", "autopartes", "automóvil", "automovil", "vehículos automotores", "vehiculos automotores"), "Automotriz"),
    (("aliment", "bebida", "lácte", "lacte", "cárnic", "carnic", "panificación", "panificacion"), "Alimentario"),
    (("telecomunicaciones", "telefonía", "telefonia", "acceso a internet", "mensajería", "mensajeria"), "Correos / Telecomunicaciones"),
    (("software", "informática", "informatica", "procesamiento electrónico de información", "procesamiento electronico de informacion"), "Tecnologia"),
    (("laboratorio", "farmacéutic", "farmaceutic"), "Laboratorios"),
    (("pesca", "acuicultura", "acuícola", "acuicola"), "Pesca"),
    (("silvicultura", "forestal"), "Silvicultura"),
    (("fundación", "fundacion", "asociación civil", "asociacion civil"), "Fundacion"),
    (("museo", "teatro", "biblioteca"), "Cultural"),
    (("incubadora", "aceleradora"), "Emprendimiento"),
    (("hotel", "agencia de viajes", "turístic", "turistic"), "Turismo"),
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
# "Nivel de cargo" es una columna status real (re-confirmado 2026-09-22) —
# estos textos deben matchear EXACTO los labels que están hoy cargados en
# Monday, sin acentos. El 4to label tiene una comilla suelta pegada al
# final (typo de carga de datos del lado de Monday, confirmado empíricamente
# contra la API) — se deja así a pedido explícito del usuario, en vez de
# corregir el label en Monday.
NIVELES_CARGO = [
    ("CEO, Presidente y/o similares",
     ["ceo", "cfo", "coo", "cto", "chief", "president", "presidente", "fundador", "founder", "dueño", "dueno"]),
    ("Director, Gerente, Jefe, Lider y/o similares",
     ["director", "gerente", "jefe", "lider", "líder", "manager", "head of"]),
    ("Coordinador y/o supervisor",
     ["coordinador", "supervisor", "coordinator"]),
    ('Auxiliar, Asistente, Operador ejecutivo Jr. y/o similares"',
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
    "Grupo empresarial", "Tipo empresa", "Descripcion empresa", "RFC empresa",
]
# Marcado manual en el panel de gestión — no se envía a Monday tal cual, pilotea
# si/cómo se exporta cada fila.
COLUMNAS_CONTACTO_GESTION = ["Contactado", "No existe / desvinculado", "Exportado a Monday"]
