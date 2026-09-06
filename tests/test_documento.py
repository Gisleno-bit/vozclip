"""Tests de las operaciones de edición.

Todo son funciones puras, así que no hace falta abrir ninguna ventana.
"""

from vozclip import documento


# -- Localizar la línea actual ---------------------------------------------
def test_linea_actual_en_medio():
    texto = "primera\nsegunda\ntercera"
    assert documento.linea_actual(texto, 10) == "segunda"


def test_linea_actual_al_principio():
    assert documento.linea_actual("hola\nadios", 0) == "hola"


def test_linea_actual_ultima_sin_salto_final():
    texto = "una\ndos"
    assert documento.linea_actual(texto, 7) == "dos"


def test_cursor_fuera_de_rango_no_revienta():
    assert documento.linea_actual("corto", 9999) == "corto"
    assert documento.linea_actual("corto", -5) == "corto"


def test_numero_de_linea():
    texto = "a\nb\nc"
    assert documento.numero_linea(texto, 0) == 1
    assert documento.numero_linea(texto, 2) == 2
    assert documento.numero_linea(texto, 4) == 3


# -- Sangrías ---------------------------------------------------------------
def test_sangria_se_pone_al_principio_de_la_linea():
    """El cursor está a mitad de la palabra, pero la sangría va al margen."""
    texto = "PERSONAJE\nhola que tal"
    cursor = 14  # dentro de "hola que tal"
    nuevo, ncursor = documento.aplicar_sangria(texto, cursor, "    ")
    assert nuevo == "PERSONAJE\n    hola que tal"
    assert ncursor == 18   # el cursor se ha desplazado con el texto


def test_sangria_en_documento_vacio():
    nuevo, cursor = documento.aplicar_sangria("", 0, "  ")
    assert nuevo == "  "
    assert cursor == 2


def test_quitar_sangria():
    texto = "        diálogo"
    nuevo, _ = documento.quitar_sangria(texto, 10, "        ")
    assert nuevo == "diálogo"


def test_quitar_sangria_parcial():
    """Si hay menos espacios que la sangría completa, quita los que haya."""
    texto = "  diálogo"
    nuevo, _ = documento.quitar_sangria(texto, 5, "        ")
    assert nuevo == "diálogo"


def test_quitar_sangria_sin_sangria_no_cambia_nada():
    texto = "diálogo"
    nuevo, cursor = documento.quitar_sangria(texto, 3, "    ")
    assert nuevo == texto
    assert cursor == 3


def test_sangria_ida_y_vuelta():
    original = "una línea"
    con, cursor = documento.aplicar_sangria(original, 4, "    ")
    sin, _ = documento.quitar_sangria(con, cursor, "    ")
    assert sin == original


# -- Salto de línea ---------------------------------------------------------
def test_siguiente_linea_hereda_la_sangria():
    texto = "        primera réplica"
    nuevo, cursor = documento.siguiente_linea(texto, 12)
    assert nuevo == "        primera réplica\n        "
    assert cursor == len(nuevo)


def test_siguiente_linea_con_sangria_explicita():
    nuevo, _ = documento.siguiente_linea("hola", 2, sangria="  ")
    assert nuevo == "hola\n  "


def test_siguiente_linea_en_medio_del_documento():
    """El salto va al FINAL de la línea, no donde esté el cursor."""
    texto = "primera\nsegunda"
    nuevo, _ = documento.siguiente_linea(texto, 3)
    assert nuevo == "primera\n\nsegunda"


def test_sangria_de_linea():
    assert documento.sangria_de_linea("    hola") == "    "
    assert documento.sangria_de_linea("\t\thola") == "\t\t"
    assert documento.sangria_de_linea("hola") == ""


# -- Insertar ---------------------------------------------------------------
def test_insertar_en_medio():
    nuevo, cursor = documento.insertar("holamundo", 4, " ")
    assert nuevo == "hola mundo"
    assert cursor == 5


# -- Marcas de plantilla ----------------------------------------------------
def test_siguiente_marca():
    assert documento.siguiente_marca([5, 20, 40], 10) == 20


def test_siguiente_marca_da_la_vuelta():
    assert documento.siguiente_marca([5, 20, 40], 100) == 5


def test_siguiente_marca_sin_marcas():
    assert documento.siguiente_marca([], 0) is None


# -- Anuncios de voz --------------------------------------------------------
def test_resumen_documento():
    assert documento.resumen_documento("") == "Documento vacío."
    assert "1 palabra en 1 línea." == documento.resumen_documento("hola")
    assert "palabras" in documento.resumen_documento("hola que tal")


def test_contexto_para_voz():
    texto = "primera\nsegunda"
    assert documento.contexto_para_voz(texto, 10) == "Línea 2. segunda"


def test_contexto_linea_vacia():
    assert "vacía" in documento.contexto_para_voz("hola\n\nadios", 5)
