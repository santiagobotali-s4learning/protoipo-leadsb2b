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
    "País (Ubicación)": "location_mm7whjxm",
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
# Board "Grupo Empresarial" (id 18430361308): su columna "País (Ubicación)"
# es location_mm7wn65y — hoy el pipeline no crea items de grupo (decisión
# explícita), así que no se escribe desde acá; queda mapeada por si se
# automatiza.
MONDAY_COLUMNA_PAIS_UBICACION_GRUPO = "location_mm7wn65y"

# Valor para país vacío o 'No disponible'. Monday exige lat/lng, así que se
# usa 0,0 (verificado 2026-10-06: lo acepta y muestra el texto 'No
# disponible'); en una vista de mapa el pin cae en el océano frente a
# África, por eso conviene filtrar/agrupar por texto, no por mapa.
UBICACION_PAIS_NO_DISPONIBLE = {"lat": "0", "lng": "0", "address": "No disponible"}

# Catálogo de países para las columnas "País (Ubicación)" de Monday. Una
# columna location exige lat/lng (sin ellos la API rechaza el valor) y NO
# deriva el país por su cuenta, así que se manda un punto de referencia
# fijo por país (centroide aproximado) + el nombre canónico. Así todos los
# registros de un mismo país quedan idénticos, sin importar cómo lo
# escribió cada persona. Clave = nombre canónico en español.
# 'alias' = variantes que ya existen escritas a mano en Monday (se comparan
# sin acentos ni mayúsculas, así que 'Mexico' y 'Peru' ya matchean solos).
# Valores que no son un país único ('Latam', 'Mexico y Colombia', 'No
# disponible' vacío) no están en el catálogo: una columna location es un
# solo punto; 'No disponible' se resuelve aparte (UBICACION_PAIS_NO_DISPONIBLE).
PAISES_UBICACION = {
    "Alemania": {"iso": "DE", "lat": "51.1657", "lng": "10.4515", "alias": []},
    "Argentina": {"iso": "AR", "lat": "-38.4161", "lng": "-63.6167", "alias": []},
    "Bélgica": {"iso": "BE", "lat": "50.5039", "lng": "4.4699", "alias": []},
    "Birmania": {"iso": "MM", "lat": "21.9162", "lng": "95.9560", "alias": []},
    "Bolivia": {"iso": "BO", "lat": "-16.2902", "lng": "-63.5887", "alias": []},
    "Brasil": {"iso": "BR", "lat": "-14.2350", "lng": "-51.9253", "alias": []},
    "Canadá": {"iso": "CA", "lat": "56.1304", "lng": "-106.3468", "alias": []},
    "Chile": {"iso": "CL", "lat": "-35.6751", "lng": "-71.5430", "alias": []},
    "China": {"iso": "CN", "lat": "35.8617", "lng": "104.1954", "alias": []},
    "Colombia": {"iso": "CO", "lat": "4.5709", "lng": "-74.2973", "alias": []},
    "Ecuador": {"iso": "EC", "lat": "-1.8312", "lng": "-78.1834", "alias": []},
    "El Salvador": {"iso": "SV", "lat": "13.7942", "lng": "-88.8965", "alias": []},
    "España": {"iso": "ES", "lat": "40.4637", "lng": "-3.7492", "alias": []},
    "Estados Unidos": {"iso": "US", "lat": "37.0902", "lng": "-95.7129", "alias": []},
    "Francia": {"iso": "FR", "lat": "46.2276", "lng": "2.2137", "alias": []},
    "India": {"iso": "IN", "lat": "20.5937", "lng": "78.9629", "alias": []},
    "Irlanda": {"iso": "IE", "lat": "53.1424", "lng": "-7.6921", "alias": []},
    "Japón": {"iso": "JP", "lat": "36.2048", "lng": "138.2529", "alias": []},
    "Luxemburgo": {"iso": "LU", "lat": "49.8153", "lng": "6.1296", "alias": []},
    "México": {"iso": "MX", "lat": "23.6345", "lng": "-102.5528", "alias": ["mxico"]},
    "Nicaragua": {"iso": "NI", "lat": "12.8654", "lng": "-85.2072", "alias": []},
    "Noruega": {"iso": "NO", "lat": "60.4720", "lng": "8.4689", "alias": []},
    "Panamá": {"iso": "PA", "lat": "8.5380", "lng": "-80.7821", "alias": []},
    "Perú": {"iso": "PE", "lat": "-9.1900", "lng": "-75.0152", "alias": []},
    "Reino Unido": {"iso": "GB", "lat": "55.3781", "lng": "-3.4360", "alias": []},
    "República Dominicana": {"iso": "DO", "lat": "18.7357", "lng": "-70.1627", "alias": ["rep. dominicana"]},
    "Suecia": {"iso": "SE", "lat": "60.1282", "lng": "18.6435", "alias": []},
    "Suiza": {"iso": "CH", "lat": "46.8182", "lng": "8.2275", "alias": []},
    "Taiwán": {"iso": "TW", "lat": "23.6978", "lng": "120.9605", "alias": []},
    "Venezuela": {"iso": "VE", "lat": "6.4238", "lng": "-66.5897", "alias": []},
}

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
    "País (Ubicación)": "location_mm7wwcd6",
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
    "Personal_monday": "Estrato (Personal Ocupado)",
    "Correo_e": "Correo",
    "Telefono": "Teléfono",
    "Sitio_internet": "Sitio web",
    "Clase_actividad": "Actividad económica",
    "CLASE_ACTIVIDAD_ID": "Código SCIAN",
    "Sector_monday": "Sector (Monday)",
    "Ubicacion": "Localidad, municipio, estado",
    "Fecha_Alta": "Fecha de alta en DENUE",
    "Grupo_corporativo_probable": "Grupo corporativo probable",
}

# Columna de personal a nivel empresa en las tablas de la Etapa 2 (misma
# etiqueta que en datos limpios; es el valor que se carga a Monday).
COLUMNA_ESTRATO_EMPRESA = {
    "Personal_monday": st.column_config.NumberColumn("Estrato (Personal Ocupado)", format="%d"),
}

# Sector SCIAN de 2 dígitos -> label de la columna 'Sector' del board de
# Cuentas (25 labels, lista final en 'Listas B2B.xlsx'; "Sector" es una
# columna status real y sus labels van SIN acentos: deben matchear exacto o
# Monday crea un label duplicado).
# Reglas por sector, según la tabla de equivalencias Sector SCIAN -> Salida
# Utel: (label por defecto, [(prefijos del código de clase SCIAN, label), ...]).
# La primera regla cuyo prefijo matchee el CLASE_ACTIVIDAD_ID gana. Cada sector
# solo puede dar las salidas que su fila permite (ej. 43/46 nunca dan
# 'Alimentario'). Label vacío "" = sin equivalencia automática: la columna
# Sector queda vacía en Monday y el registro se ve sin sector en la app.
SECTOR_MONDAY_REGLAS = {
    "11": ("Agricultura", [(("1125", "1141"), "Pesca"), (("113", "1153"), "Silvicultura")]),
    "21": ("Mineria", []),
    "22": ("", []),
    "23": ("Construccion", []),
    "31": ("Manufactura/ Transformacion de productos",
           [(("311", "3121"), "Alimentario"), (("3361", "3362", "3363"), "Automotriz"), (("3254",), "Laboratorios")]),
    "43": ("Comercio", [(("436",), "Automotriz")]),
    "46": ("Comercio", [(("4681", "4682", "4683"), "Automotriz")]),
    "48": ("Transporte", []),
    "49": ("Transporte", [(("491", "492"), "Correos / Telecomunicaciones")]),
    "51": ("", [(("517",), "Correos / Telecomunicaciones"), (("5132", "518"), "Tecnologia"),
                (("512", "516"), "Entretenimiento"), (("511", "513", "5192"), "Cultural")]),
    "52": ("Financiero", []),
    "53": ("Inmobiliaria", []),
    "54": ("Profesional", [(("5415",), "Tecnologia"), (("541380",), "Laboratorios")]),
    "55": ("", []),
    "56": ("", []),
    "61": ("Educativo", []),
    "62": ("Salud", [(("6215",), "Laboratorios")]),
    "71": ("Entretenimiento", [(("7111", "7115", "7121"), "Cultural")]),
    "72": ("", [(("721",), "Turismo"), (("722",), "Alimentario")]),
    "81": ("", [(("8111",), "Automotriz")]),
    "93": ("Gobierno", []),
}
# 32 y 33 comparten las reglas de 31 (Manufacturas).
SECTOR_MONDAY_REGLAS["32"] = SECTOR_MONDAY_REGLAS["33"] = SECTOR_MONDAY_REGLAS["31"]

# Respaldo por texto de Clase_actividad (minúsculas) para sectores donde la
# clase SCIAN sola no alcanza. Solo corre si ninguna regla de prefijo matcheó.
# {prefijo de sector: [(palabras clave, label), ...]}
SECTOR_MONDAY_PALABRAS_CLAVE = {
    "54": [(("incubadora", "aceleradora"), "Emprendimiento")],
    "81": [(("fundación", "fundacion", "asociación civil", "asociacion civil"), "Fundacion")],
}

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
# Monday, sin acentos (lista final en 'Listas B2B.xlsx'). El 4to label tenía
# una comilla suelta pegada al final (typo antiguo de Monday); la lista final
# ya no la tiene, así que acá tampoco.
NIVELES_CARGO = [
    ("CEO, Presidente y/o similares",
     ["ceo", "cfo", "coo", "cto", "chief", "president", "presidente", "fundador", "founder", "dueño", "dueno"]),
    ("Director, Gerente, Jefe, Lider y/o similares",
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
    "Personal estimado empresa", "Sitio web empresa", "Correo empresa",
    "Grupo empresarial", "Tipo empresa", "Descripcion empresa", "RFC empresa",
]
# Marcado manual en el panel de gestión — no se envía a Monday tal cual, pilotea
# si/cómo se exporta cada fila.
COLUMNAS_CONTACTO_GESTION = ["Contactado", "No existe / desvinculado", "Exportado a Monday"]
