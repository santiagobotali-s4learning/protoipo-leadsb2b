import pandas as pd

from cuentas import clasificar_cuentas, perfil_desde_cuenta


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
