"""
Catálogos públicos usados por la UI y por las llamadas a DENUE.

Estos NO son criterios de negocio (no definen qué sector/estado/tamaño es
"de interés"), son simplemente los catálogos oficiales (SCIAN, entidades
federativas del INEGI, bandas de estrato del propio DENUE) que alimentan
los dropdowns/checkboxes. El criterio de negocio (qué opciones elegir
dentro de estos catálogos) lo define el usuario desde la UI en cada corrida.
"""

# Sectores SCIAN de 2 dígitos (catálogo completo usado por INEGI/DENUE).
# Formato: {"codigo": "nombre"}
SECTORES_SCIAN = {
    "11": "Agricultura, cría y explotación de animales, aprovechamiento forestal, pesca y caza",
    "21": "Minería",
    "22": "Generación, transmisión y distribución de energía eléctrica, suministro de agua y de gas",
    "23": "Construcción",
    "31-33": "Industrias manufactureras",
    "43": "Comercio al por mayor",
    "46": "Comercio al por menor",
    "48-49": "Transportes, correos y almacenamiento",
    "51": "Información en medios masivos",
    "52": "Servicios financieros y de seguros",
    "53": "Servicios inmobiliarios y de alquiler de bienes muebles e intangibles",
    "54": "Servicios profesionales, científicos y técnicos",
    "55": "Dirección de corporativos y empresas",
    "56": "Servicios de apoyo a los negocios y manejo de residuos",
    "61": "Servicios educativos",
    "62": "Servicios de salud y de asistencia social",
    "71": "Servicios de esparcimiento culturales y deportivos",
    "72": "Servicios de alojamiento temporal y de preparación de alimentos",
    "81": "Otros servicios excepto actividades gubernamentales",
    "93": "Actividades legislativas, gubernamentales, de impartición de justicia y de organismos internacionales",
}

# Código DENUE que representa "todos los sectores" en el parámetro Sector.
SECTOR_TODOS = "0"

# Entidades federativas de México con su clave de 2 dígitos usada por DENUE.
ENTIDADES_FEDERATIVAS = {
    "01": "Aguascalientes",
    "02": "Baja California",
    "03": "Baja California Sur",
    "04": "Campeche",
    "05": "Coahuila de Zaragoza",
    "06": "Colima",
    "07": "Chiapas",
    "08": "Chihuahua",
    "09": "Ciudad de México",
    "10": "Durango",
    "11": "Guanajuato",
    "12": "Guerrero",
    "13": "Hidalgo",
    "14": "Jalisco",
    "15": "México",
    "16": "Michoacán de Ocampo",
    "17": "Morelos",
    "18": "Nayarit",
    "19": "Nuevo León",
    "20": "Oaxaca",
    "21": "Puebla",
    "22": "Querétaro",
    "23": "Quintana Roo",
    "24": "San Luis Potosí",
    "25": "Sinaloa",
    "26": "Sonora",
    "27": "Tabasco",
    "28": "Tamaulipas",
    "29": "Tlaxcala",
    "30": "Veracruz de Ignacio de la Llave",
    "31": "Yucatán",
    "32": "Zacatecas",
}

# Bandas oficiales de estrato (personal ocupado) y su código DENUE (1 dígito).
ESTRATOS = {
    "1": "0 a 5",
    "2": "6 a 10",
    "3": "11 a 30",
    "4": "31 a 50",
    "5": "51 a 100",
    "6": "101 a 250",
    "7": "251 y más",
}
