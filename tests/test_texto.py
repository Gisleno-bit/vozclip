"""Tests de la limpieza y el troceado de texto."""

from vozclip import texto


def test_une_lineas_partidas():
    entrada = "Esto es una frase\nque venía partida en dos."
    assert texto.limpiar(entrada) == "Esto es una frase que venía partida en dos."


def test_arregla_guion_de_corte():
    entrada = "Un documento con conti-\nnuación de palabra."
    assert "continuación" in texto.limpiar(entrada)


def test_separa_parrafos_con_pausa():
    entrada = "Primer párrafo\n\nSegundo párrafo"
    salida = texto.limpiar(entrada)
    assert "Primer párrafo." in salida
    assert "Segundo párrafo" in salida


def test_quita_vinetas():
    entrada = "• Primer punto\n• Segundo punto"
    salida = texto.limpiar(entrada)
    assert "•" not in salida


def test_colapsa_espacios():
    assert texto.limpiar("hola     mundo") == "hola mundo"


def test_texto_vacio():
    assert texto.limpiar("") == ""
    assert texto.limpiar("   \n  ") == ""
    assert texto.trocear("") == []


def test_trocear_respeta_el_maximo():
    largo = " ".join(f"Esta es la frase número {i}." for i in range(200))
    trozos = texto.trocear(largo, maximo=100)
    assert trozos
    assert all(len(t) <= 100 for t in trozos)


def test_trocear_no_pierde_palabras():
    original = "Uno dos tres. Cuatro cinco seis. Siete ocho nueve."
    trozos = texto.trocear(original, maximo=20)
    reconstruido = " ".join(trozos)
    for palabra in ["Uno", "cinco", "nueve"]:
        assert palabra in reconstruido


def test_trocear_frase_kilometrica():
    frase = "palabra " * 500
    trozos = texto.trocear(frase, maximo=50)
    assert all(len(t) <= 50 for t in trozos)
    assert len(trozos) > 1


def test_resumen_para_anuncio():
    assert texto.resumen_para_anuncio("uno dos tres", palabras=6) == "uno dos tres"
    largo = texto.resumen_para_anuncio("a b c d e f g h", palabras=3)
    assert largo == "a b c…"
    assert texto.resumen_para_anuncio("") == ""
