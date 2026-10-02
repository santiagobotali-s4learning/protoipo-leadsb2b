import pandas as pd

from denue import agrupar_por_empresa


def _sucursales(estratos, razon="Empresa SA"):
    n = len(estratos)
    return pd.DataFrame({
        "Id": list(range(n)), "Razon_social": [razon] * n, "Nombre": ["X"] * n,
        "Estrato": estratos, "Clase_actividad": ["Comercio"] * n,
        "CLASE_ACTIVIDAD_ID": ["461110"] * n, "Correo_e": [""] * n, "Telefono": [""] * n,
        "Sitio_internet": [""] * n, "Ubicacion": [""] * n, "Fecha_Alta": [""] * n,
    })


def test_personal_monday_usa_el_maximo_del_rango():
    fila = agrupar_por_empresa(_sucursales(["31 a 50 personas"])).iloc[0]
    assert fila["Personal_monday"] == 50
    assert fila["Personal_estimado"] == "31–50"  # la vista conserva el rango


def test_personal_monday_suma_maximos_de_sucursales():
    fila = agrupar_por_empresa(_sucursales(["6 a 10 personas", "11 a 30 personas"])).iloc[0]
    assert fila["Personal_monday"] == 40


def test_personal_monday_banda_abierta_usa_251():
    fila = agrupar_por_empresa(_sucursales(["251 y más personas"])).iloc[0]
    assert fila["Personal_monday"] == 251
    assert fila["Personal_estimado"] == "251+"


def test_personal_monday_banda_abierta_mas_otras_sucursales():
    fila = agrupar_por_empresa(_sucursales(["251 y más personas", "11 a 30 personas"])).iloc[0]
    assert fila["Personal_monday"] == 281
