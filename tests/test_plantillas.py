"""Tests de las plantillas de guion."""

import pytest

from vozclip import plantillas


def test_catalogo_tiene_las_tres():
    """Teatro y cine se retiraron: eran las únicas que insertaban un nombre
    de PERSONAJE en F3."""
    assert set(plantillas.CATALOGO) == {"novela", "narrativo", "escaleta"}


def test_un_ajuste_antiguo_se_corrige_solo():
    """Un config.json que dijera 'teatro' dejaba F3 metiendo PERSONAJE.
    Al retirar esas plantillas, se resuelve a novela sin tocar nada."""
    assert plantillas.obtener("teatro").clave == "novela"
    assert plantillas.obtener("cine").clave == "novela"


def test_la_novela_va_primera():
    """Es el formato propio de Julián, el que usa a diario."""
    assert plantillas.ORDEN[0] == "novela"
    assert plantillas.obtener("no_existe").clave == "novela"


def test_preparar_quita_las_marcas():
    resultado = plantillas.preparar("Hola |mundo|")
    assert resultado.texto == "Hola mundo"
    assert resultado.posiciones == [5, 10]


def test_preparar_sin_marcas():
    resultado = plantillas.preparar("Texto sin huecos")
    assert resultado.texto == "Texto sin huecos"
    assert resultado.posiciones == []


@pytest.mark.parametrize("clave", list(plantillas.CATALOGO))
def test_todas_las_plantillas_tienen_huecos(clave):
    plantilla = plantillas.obtener(clave)
    resultado = plantillas.preparar(plantilla)
    assert resultado.posiciones, f"{clave} no tiene marcas de cursor"
    assert "|" not in resultado.texto


@pytest.mark.parametrize("clave", list(plantillas.CATALOGO))
def test_las_posiciones_caen_dentro_del_texto(clave):
    resultado = plantillas.preparar(plantillas.obtener(clave))
    for p in resultado.posiciones:
        assert 0 <= p <= len(resultado.texto)


def test_ninguna_plantilla_menciona_personaje():
    """La comprobación que faltaba: que no quede ni rastro."""
    for clave in plantillas.ORDEN:
        texto = plantillas.preparar(plantillas.obtener(clave)).texto
        assert "PERSONAJE" not in texto, f"La plantilla {clave} aún lo tiene"


def test_narrativo_es_solo_sangria_y_raya():
    """La plantilla 3 de Julián: sangría de 0,63 cm (dos caracteres), la
    raya pegada, y el cursor detrás. Nada más: ni personaje, ni verbo
    dicendi, ni huecos de relleno."""
    resultado = plantillas.preparar(plantillas.NARRATIVO)
    assert resultado.texto == "  —"
    assert resultado.posiciones == [3]       # un solo hueco, tras la raya
    assert "PERSONAJE" not in resultado.texto
    assert "dijo" not in resultado.texto


def test_la_sangria_de_dialogo_es_de_dos_caracteres():
    assert plantillas.SANGRIA_DIALOGO == "  "
    assert plantillas.NARRATIVO.sangria_dialogo == "  "
    assert plantillas.NOVELA.sangria_dialogo == "  "


def test_rotacion_de_plantillas():
    assert plantillas.siguiente_clave("novela") == "narrativo"
    assert plantillas.siguiente_clave("narrativo") == "escaleta"
    assert plantillas.siguiente_clave("escaleta") == "novela"   # da la vuelta
    assert plantillas.siguiente_clave("inventada") == "novela"


def test_obtener_clave_desconocida_no_revienta():
    assert plantillas.obtener("no_existe").clave == "novela"


def test_describir_menciona_el_nombre():
    frase = plantillas.describir(plantillas.NOVELA)
    assert "novela" in frase
