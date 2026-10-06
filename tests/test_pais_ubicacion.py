import pytest

from utils import pais_canonico, valor_ubicacion_pais


@pytest.mark.parametrize("escrito", ["México", "mexico", "MÉXICO ", "Mxico"])
def test_variantes_de_mexico_se_estandarizan(escrito):
    assert pais_canonico(escrito) == "México"
    assert valor_ubicacion_pais(escrito) == {
        "lat": "23.6345", "lng": "-102.5528", "address": "México",
        "country": "México", "countryShort": "MX",
    }


@pytest.mark.parametrize("escrito", [None, "", float("nan"), "No disponible", "NO DISPONIBLE"])
def test_pais_vacio_o_no_disponible(escrito):
    assert valor_ubicacion_pais(escrito) == {"lat": "0", "lng": "0", "address": "No disponible"}


@pytest.mark.parametrize("escrito", ["Narnia", "Latam", "Mexico y Colombia"])
def test_texto_desconocido_no_se_escribe(escrito):
    assert valor_ubicacion_pais(escrito) is None


@pytest.mark.parametrize("escrito,canonico", [
    ("Peru", "Perú"), ("Panama", "Panamá"), ("El salvador", "El Salvador"),
    ("Republica Dominicana", "República Dominicana"), ("Rep. Dominicana", "República Dominicana"),
    ("Taiwan", "Taiwán"), ("Japon", "Japón"),
])
def test_variantes_manuales_del_listado(escrito, canonico):
    assert pais_canonico(escrito) == canonico
