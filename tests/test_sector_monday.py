import openpyxl
import pytest

from config import SECTOR_MONDAY_PALABRAS_CLAVE, SECTOR_MONDAY_REGLAS
from denue import sector_monday


@pytest.mark.parametrize("clase_id, clase, esperado", [
    ("112519", "Otra acuicultura", "Pesca"),
    ("115310", "Servicios relacionados con el aprovechamiento forestal", "Silvicultura"),
    ("111110", "Cultivo", "Agricultura"),
    ("312112", "Purificación y embotellado de agua", "Alimentario"),
    ("336110", "Fabricación de automóviles", "Automotriz"),
    ("325411", "Fabricación de productos farmacéuticos", "Laboratorios"),
    ("313210", "Telas", "Manufactura/ Transformacion de productos"),
    ("461110", "Abarrotes", "Comercio"),            # nunca Alimentario
    ("431110", "Mayoreo de abarrotes", "Comercio"),
    ("468111", "Venta de automóviles", "Automotriz"),
    ("436111", "Mayoreo de camiones", "Automotriz"),
    ("492110", "Servicios de mensajería", "Correos / Telecomunicaciones"),
    ("484111", "Autotransporte", "Transporte"),
    ("517311", "Telecomunicaciones", "Correos / Telecomunicaciones"),
    ("518210", "Procesamiento electrónico de información", "Tecnologia"),
    ("513111", "Edición de periódicos", "Cultural"),
    ("512111", "Producción de películas", "Entretenimiento"),
    ("519190", "Otros servicios de información", ""),   # 51 sin clase conocida: vacío
    ("541510", "Diseño de sistemas de cómputo", "Tecnologia"),
    ("541380", "Laboratorios de pruebas", "Laboratorios"),
    ("541110", "Bufetes jurídicos", "Profesional"),      # nunca Servicios
    ("621511", "Laboratorios médicos", "Laboratorios"),
    ("621111", "Consultorios", "Salud"),
    ("712111", "Museos", "Cultural"),
    ("713111", "Parques de diversiones", "Entretenimiento"),
    ("721111", "Hoteles", "Turismo"),
    ("722513", "Restaurantes", "Alimentario"),
    ("811111", "Reparación mecánica de automóviles", "Automotriz"),
    ("812110", "Salones de belleza", ""),
    ("221111", "Generación de electricidad", ""),
    ("551112", "Tenedoras de acciones", ""),
    ("561110", "Administración de negocios", ""),
    ("931110", "Administración pública", "Gobierno"),
    ("", "", ""),
])
def test_sector_monday_segun_tabla_de_equivalencias(clase_id, clase, esperado):
    assert sector_monday(clase, clase_id) == esperado


def test_palabras_clave_de_respaldo():
    assert sector_monday("Fundación sin fines de lucro", "813999") == "Fundacion"
    assert sector_monday("Incubadora de empresas", "541990") == "Emprendimiento"


def test_todas_las_salidas_existen_en_la_lista_de_monday():
    ws = openpyxl.load_workbook("Listas B2B.xlsx", data_only=True)["Listas"]
    labels = {v for c in ws.iter_cols(values_only=True) if c[1] == "Sector" for v in c[2:] if v}
    salidas = {d for d, _ in SECTOR_MONDAY_REGLAS.values()} | {
        e for _, reglas in SECTOR_MONDAY_REGLAS.values() for _, e in reglas
    } | {e for lst in SECTOR_MONDAY_PALABRAS_CLAVE.values() for _, e in lst}
    assert salidas - {""} <= labels
