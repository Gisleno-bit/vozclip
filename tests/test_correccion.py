"""Tests de la corrección por voz: palabras, números, órdenes y sustitución.

Todo funciones puras: sin ventana, sin micrófono.
"""

from __future__ import annotations

import pytest

from vozclip import correccion as c

PARRAFO = "     Aquella noche no dormí. El taller olía a papel viejo, y la casa estaba en silencio."
AMBITO = (0, len(PARRAFO))


def _aplicar(dicho, texto=PARRAFO, eleccion=None):
    return c.aplicar(texto, c.interpretar_orden(dicho), (0, len(texto)), eleccion)


# ===========================================================================
# Palabras
# ===========================================================================
def test_tokenizar_numera_desde_uno():
    palabras = c.tokenizar("Hola, mundo cruel.")
    assert [p.indice for p in palabras] == [1, 2, 3]
    assert [p.texto for p in palabras] == ["Hola", "mundo", "cruel"]


def test_la_puntuacion_no_forma_parte_de_la_palabra():
    """Así, al cambiar 'casa' en 'casa,' se conserva la coma."""
    [p] = c.tokenizar("casa,")
    assert p.texto == "casa"
    assert (p.inicio, p.fin) == (0, 4)


def test_los_acentos_y_la_ene_son_letras():
    assert [p.texto for p in c.tokenizar("dormí año")] == ["dormí", "año"]


def test_enumerar_dice_numero_y_palabra():
    assert c.enumerar("casa azul") == "1, casa. 2, azul."


def test_enumerar_un_texto_vacio():
    assert c.enumerar("") == "No hay palabras."


def test_enumerar_tiene_tope():
    largo = " ".join(f"p{i}" for i in range(100))
    frase = c.enumerar(largo, maximo=10)
    assert "10, p9." in frase
    assert "90 más" in frase


# ===========================================================================
# Números en castellano
# ===========================================================================
@pytest.mark.parametrize("palabras, esperado", [
    (["tres"], 3), (["3"], 3), (["doce"], 12), (["veintitrés"], 23),
    (["treinta", "y", "dos"], 32), (["cuarenta"], 40), (["una"], 1),
    (["casa"], None), ([], None),
])
def test_numero(palabras, esperado):
    assert c.numero(palabras) == esperado


def test_numeros_en_una_frase():
    assert c._numeros_en("la dos y la cuatro") == [2, 4]
    assert c._numeros_en("de la treinta y dos a la treinta y cinco") == [32, 35]
    assert c._numeros_en("cambia casa por cosa") == []


# ===========================================================================
# Órdenes
# ===========================================================================
@pytest.mark.parametrize("dicho", [
    "cambia casa por cosa", "cambiar casa por cosa", "sustituye casa por cosa",
    "reemplaza casa por cosa", "corrige casa por cosa", "casa por cosa",
    "Cambia casa por cosa.",
])
def test_cambiar_una_palabra(dicho):
    o = c.interpretar_orden(dicho)
    assert (o.tipo, o.buscar, o.poner) == ("cambiar", "casa", "cosa")


def test_cambiar_una_frase_entera():
    o = c.interpretar_orden("cambia no me lo creo por no lo creo")
    assert o.buscar == "no me lo creo"
    assert o.poner == "no lo creo"


def test_el_ultimo_por_es_el_separador():
    """'cambia por favor por por fin': lo de después del último 'por' es lo
    nuevo."""
    o = c.interpretar_orden("cambia por favor por por fin")
    assert o.buscar == "por favor"
    assert o.poner == "por fin"


@pytest.mark.parametrize("dicho, indices", [
    ("cambia la tres por cosa", [3]),
    ("la tres por cosa", [3]),
    ("cambia la palabra tres por cosa", [3]),
    ("cambia la uno y la tres por cosa", [1, 3]),
    ("cambia de la dos a la cuatro por cosa", [2, 3, 4]),
    ("cambia de la treinta y dos a la treinta y cuatro por cosa", [32, 33, 34]),
])
def test_cambiar_por_numero(dicho, indices):
    o = c.interpretar_orden(dicho)
    assert o.tipo == "cambiar"
    assert o.indices == indices
    assert o.poner == "cosa"


@pytest.mark.parametrize("dicho", ["borra viejo", "quita viejo", "elimina la tres"])
def test_borrar(dicho):
    assert c.interpretar_orden(dicho).tipo == "borrar"


@pytest.mark.parametrize("dicho", ["léelo", "leelo", "numera", "enumera", "repítelo"])
def test_numerar(dicho):
    assert c.interpretar_orden(dicho).tipo == "numerar"


@pytest.mark.parametrize("dicho", ["cancela", "cancelar", "nada", "déjalo", "no"])
def test_cancelar(dicho):
    assert c.interpretar_orden(dicho).tipo == "cancelar"


def test_deshacer():
    assert c.interpretar_orden("deshacer").tipo == "deshacer"


def test_no_a_secas_cancela_pero_no_se_no():
    """'no sé' o 'no dormí' no son una cancelación."""
    assert c.interpretar_orden("no").tipo == "cancelar"
    assert c.interpretar_orden("no sé").tipo != "cancelar"
    assert c.interpretar_orden("no dormí por no me dormí").tipo == "cambiar"


def test_borrar_a_secas_es_una_orden():
    """En el flujo guiado, tras elegir la palabra, 'borrar' la quita."""
    assert c.interpretar_orden("borrar").tipo == "borrar"



@pytest.mark.parametrize("dicho", ["", "hola", "cambia casa", "por cosa", "la tres"])
def test_lo_que_no_es_una_orden(dicho):
    assert c.interpretar_orden(dicho).tipo == "desconocida"


# ===========================================================================
# Localizar
# ===========================================================================
def test_localizar_sin_mayusculas_ni_acentos():
    """El reconocedor no siempre los pone, y Julián no los va a dictar."""
    [m] = c.localizar(PARRAFO, "dormi")
    assert m.texto == "dormí"
    [m] = c.localizar(PARRAFO, "aquella")
    assert m.texto == "Aquella"


def test_localizar_una_frase():
    [m] = c.localizar(PARRAFO, "el taller olia")
    assert m.texto == "El taller olía"


def test_localizar_respeta_el_ambito():
    texto = "casa aquí.\n\ncasa allí."
    assert len(c.localizar(texto, "casa")) == 2
    assert len(c.localizar(texto, "casa", (12, len(texto)))) == 1


def test_localizar_no_encuentra():
    assert c.localizar(PARRAFO, "bicicleta") == []


def test_localizar_no_confunde_partes_de_palabra():
    assert c.localizar("Casablanca es blanca", "casa") == []


# ===========================================================================
# Sustituir: lo esencial
# ===========================================================================
def test_cambia_solo_esa_palabra():
    r = _aplicar("cambia casa por cosa")
    assert r.aplicado
    assert r.texto == PARRAFO.replace("casa", "cosa")
    assert r.mensaje == "He cambiado casa por cosa."


def test_conserva_la_sangria_y_la_puntuacion():
    r = _aplicar("cambia viejo por nuevo")
    assert r.texto.startswith("     Aquella")          # sangría intacta
    assert "papel nuevo, y" in r.texto                  # la coma sigue pegada


def test_conserva_la_mayuscula_inicial():
    r = _aplicar("cambia aquella por esa")
    assert r.texto.startswith("     Esa noche")


def test_cambia_una_frase():
    r = _aplicar("cambia el taller olía por el taller huele")
    assert "El taller huele a papel" in r.texto


def test_cambia_por_numero():
    r = _aplicar("cambia la dos por tarde")
    assert "Aquella tarde no dormí" in r.texto
    assert r.mensaje == "He cambiado noche por tarde."


def test_un_rango_es_un_solo_tramo():
    """'de la tres a la cuatro por me desvelé' sustituye 'no dormí' entero,
    no cada palabra por separado."""
    r = _aplicar("cambia de la tres a la cuatro por me desvelé")
    assert "Aquella noche me desvelé." in r.texto
    assert r.texto.count("me desvelé") == 1


def test_numeros_salteados_son_tramos_independientes():
    r = _aplicar("cambia la dos y la seis por X")
    assert "Aquella X no dormí. El X olía" in r.texto


def test_borrar_cierra_el_hueco():
    r = _aplicar("borra viejo")
    assert "a papel, y la casa" in r.texto          # ni doble espacio ni espacio antes de la coma
    assert r.mensaje == "He borrado viejo."


def test_borrar_al_final():
    r = _aplicar("borra silencio", "la casa estaba en silencio")
    assert r.texto == "la casa estaba en"


def test_no_encontrada():
    r = _aplicar("cambia bicicleta por moto")
    assert not r.aplicado
    assert r.texto == PARRAFO
    assert "No encuentro bicicleta" in r.mensaje
    assert "léelo" in r.mensaje


def test_numero_fuera_de_rango():
    r = _aplicar("cambia la cincuenta por x")
    assert not r.aplicado
    assert "solo hay" in r.mensaje


def test_varias_apariciones_preguntan():
    texto = "la casa grande y la casa pequeña"
    r = _aplicar("cambia casa por cosa", texto)
    assert not r.aplicado
    assert len(r.opciones) == 2
    assert "aparece 2 veces" in r.mensaje
    assert "¿Cuál?" in r.mensaje


def test_varias_apariciones_se_resuelven_con_el_numero():
    texto = "la casa grande y la casa pequeña"
    r = _aplicar("cambia casa por cosa", texto, eleccion=2)
    assert r.aplicado
    assert r.texto == "la casa grande y la cosa pequeña"


def test_eleccion_fuera_de_rango():
    texto = "la casa grande y la casa pequeña"
    r = _aplicar("cambia casa por cosa", texto, eleccion=5)
    assert not r.aplicado
    assert "Solo hay 2" in r.mensaje


def test_leelo_enumera_el_ambito():
    r = _aplicar("léelo", "uno dos tres")
    assert r.mensaje == "1, uno. 2, dos. 3, tres."
    assert not r.aplicado


def test_orden_desconocida_explica_como_hacerlo():
    r = _aplicar("hola qué tal")
    assert "cambia casa por cosa" in r.mensaje


def test_el_cursor_queda_tras_lo_nuevo():
    r = _aplicar("cambia casa por cosa")
    assert r.texto[r.cursor - 4:r.cursor] == "cosa"


# ===========================================================================
# Ámbito
# ===========================================================================
def test_ambito_es_el_parrafo_del_cursor():
    texto = "primero.\n\nsegundo párrafo aquí.\n\ntercero."
    ini, fin = c.ambito_parrafo(texto, texto.index("segundo") + 3)
    assert texto[ini:fin] == "segundo párrafo aquí."


def test_ambito_en_blanco_es_el_ultimo_parrafo():
    texto = "primero.\n\nsegundo.\n\n"
    ini, fin = c.ambito_parrafo(texto, len(texto))
    assert texto[ini:fin] == "segundo."
