"""Tests del puente con aplicaciones externas.

No se puede abrir Word en un contenedor, así que se prueban las piezas que
sí se pueden probar y que son donde estaban los fallos reales: la espera
adaptativa, la restauración del portapapeles y la elección del método de
inserción.
"""

from __future__ import annotations

import pytest

from vozclip import puente
from vozclip.fuentes import ErrorFuente


@pytest.fixture(autouse=True)
def adaptador_limpio():
    """Cada test empieza con el adaptador sin aprender nada."""
    puente.ADAPTADOR.reiniciar()
    yield
    puente.ADAPTADOR.reiniciar()


# ===========================================================================
# Espera adaptativa
# ===========================================================================
def test_cada_aplicacion_tiene_su_espera():
    """El Bloc de notas pega al instante; Word tarda tres veces más."""
    assert puente.ADAPTADOR.espera("notepad") < puente.ADAPTADOR.espera("winword")
    assert puente.ADAPTADOR.espera("winword") < puente.ADAPTADOR.espera("chrome")


def test_una_app_desconocida_usa_la_espera_por_defecto():
    assert puente.ADAPTADOR.espera("programa_raro") == puente.ESPERA_POR_DEFECTO


def test_un_fallo_sube_la_espera_deprisa():
    """Cuando algo falla hay que dar margen ya, no poco a poco."""
    inicial = puente.ADAPTADOR.espera("winword")
    puente.ADAPTADOR.registrar_fallo("winword")
    assert puente.ADAPTADOR.espera("winword") > inicial * 1.5


def test_un_exito_a_la_primera_baja_la_espera_despacio():
    """Bajar despacio evita volver a quedarse corto al primer tropiezo."""
    inicial = puente.ADAPTADOR.espera("notepad")
    puente.ADAPTADOR.registrar_exito("notepad", intentos=1)
    nueva = puente.ADAPTADOR.espera("notepad")
    assert nueva < inicial
    assert nueva > inicial * 0.8


def test_un_exito_tras_reintentos_no_baja_la_espera():
    puente.ADAPTADOR.registrar_fallo("chrome")
    tras_fallo = puente.ADAPTADOR.espera("chrome")
    puente.ADAPTADOR.registrar_exito("chrome", intentos=2)
    assert puente.ADAPTADOR.espera("chrome") == tras_fallo


def test_la_espera_tiene_topes():
    for _ in range(30):
        puente.ADAPTADOR.registrar_fallo("winword")
    assert puente.ADAPTADOR.espera("winword") <= puente.ESPERA_MAXIMA

    puente.ADAPTADOR.reiniciar()
    for _ in range(200):
        puente.ADAPTADOR.registrar_exito("notepad", intentos=1)
    assert puente.ADAPTADOR.espera("notepad") >= puente.ESPERA_MINIMA


def test_reiniciar_olvida_lo_aprendido():
    puente.ADAPTADOR.registrar_fallo("notepad")
    puente.ADAPTADOR.reiniciar()
    assert puente.ADAPTADOR.espera("notepad") == puente.ESPERAS_POR_APP["notepad"]


# ===========================================================================
# Portapapeles prestado
# ===========================================================================
def test_el_portapapeles_se_restaura(monkeypatch):
    almacen = {"valor": "lo que el usuario tenía copiado"}
    monkeypatch.setattr(puente, "leer_portapapeles", lambda: almacen["valor"])
    monkeypatch.setattr(
        puente, "escribir_portapapeles", lambda t: almacen.__setitem__("valor", t)
    )

    with puente.portapapeles_prestado():
        puente.escribir_portapapeles("texto temporal de VozClip")
        assert almacen["valor"] == "texto temporal de VozClip"

    assert almacen["valor"] == "lo que el usuario tenía copiado"


def test_el_portapapeles_se_restaura_aunque_falle(monkeypatch):
    """Lo que el usuario tenía copiado no se pierde ni con una excepción."""
    almacen = {"valor": "importante"}
    monkeypatch.setattr(puente, "leer_portapapeles", lambda: almacen["valor"])
    monkeypatch.setattr(
        puente, "escribir_portapapeles", lambda t: almacen.__setitem__("valor", t)
    )

    with pytest.raises(RuntimeError):
        with puente.portapapeles_prestado():
            puente.escribir_portapapeles("basura")
            raise RuntimeError("algo se rompió")

    assert almacen["valor"] == "importante"


def test_si_no_se_puede_leer_el_portapapeles_no_revienta(monkeypatch):
    def falla():
        raise ErrorFuente("sin portapapeles")

    monkeypatch.setattr(puente, "leer_portapapeles", falla)
    monkeypatch.setattr(puente, "escribir_portapapeles", lambda _t: None)

    with puente.portapapeles_prestado() as anterior:
        assert anterior == ""


# ===========================================================================
# Elección del método de inserción
# ===========================================================================
def test_texto_vacio_no_hace_nada():
    assert puente.insertar_texto("") == "nada"


def test_se_pega_por_defecto(monkeypatch):
    monkeypatch.setattr(puente, "app_activa", lambda: "winword")
    monkeypatch.setattr(puente, "_pegar", lambda t, a: None)
    assert puente.insertar_texto("hola") == "pegar"


def test_en_la_terminal_se_teclea(monkeypatch):
    """Ctrl+V no pega en muchas consolas: hay que teclear."""
    monkeypatch.setattr(puente, "app_activa", lambda: "powershell")
    monkeypatch.setattr(puente, "_teclear", lambda t: None)
    assert puente.insertar_texto("dir") == "teclear"


def test_un_texto_largo_se_pega_aunque_sea_terminal(monkeypatch):
    """Teclear 2000 caracteres tardaría más de un minuto."""
    monkeypatch.setattr(puente, "app_activa", lambda: "powershell")
    monkeypatch.setattr(puente, "_pegar", lambda t, a: None)
    largo = "x" * (puente.LIMITE_TECLEADO + 1)
    assert puente.insertar_texto(largo) == "pegar"


def test_se_puede_forzar_el_metodo(monkeypatch):
    monkeypatch.setattr(puente, "_teclear", lambda t: None)
    assert puente.insertar_texto("hola", metodo="teclear") == "teclear"


# ===========================================================================
# Detección de la aplicación activa
# ===========================================================================
def test_fuera_de_windows_no_se_detecta_app():
    """En Linux devuelve cadena vacía en vez de lanzar una excepción: no
    saber la aplicación degrada la precisión, no la función."""
    import platform

    if platform.system() != "Windows":
        assert puente.app_activa() == ""
        assert puente.titulo_ventana_activa() == ""


def test_describir_destino_siempre_dice_algo():
    """Se usa para anunciar en voz alta dónde se va a escribir."""
    descripcion = puente.describir_destino()
    assert descripcion
    assert isinstance(descripcion, str)


# ===========================================================================
# Captura con marca
# ===========================================================================
def test_la_captura_detecta_que_no_se_copio_nada(monkeypatch):
    """Si tras el Ctrl+C sigue estando la marca, la app no copió."""
    monkeypatch.setattr(puente, "app_activa", lambda: "notepad")
    monkeypatch.setattr(puente, "leer_portapapeles", lambda: puente.MARCA)
    monkeypatch.setattr(puente, "escribir_portapapeles", lambda _t: None)
    monkeypatch.setattr(puente.time, "sleep", lambda _s: None)

    with pytest.raises(ErrorFuente, match="no permite copiar"):
        puente._capturar(lambda: None, "La aplicación no permite copiar.")


def test_la_captura_reintenta_antes_de_rendirse(monkeypatch):
    """Puede que la aplicación solo vaya lenta la primera vez."""
    intentos = {"n": 0}

    def leer():
        intentos["n"] += 1
        return "por fin el texto" if intentos["n"] >= 2 else puente.MARCA

    monkeypatch.setattr(puente, "app_activa", lambda: "winword")
    monkeypatch.setattr(puente, "leer_portapapeles", leer)
    monkeypatch.setattr(puente, "escribir_portapapeles", lambda _t: None)
    monkeypatch.setattr(puente.time, "sleep", lambda _s: None)

    assert puente._capturar(lambda: None, "error") == "por fin el texto"
    assert intentos["n"] >= 2


def test_un_fallo_al_capturar_sube_la_espera(monkeypatch):
    monkeypatch.setattr(puente, "app_activa", lambda: "chrome")
    monkeypatch.setattr(puente, "leer_portapapeles", lambda: puente.MARCA)
    monkeypatch.setattr(puente, "escribir_portapapeles", lambda _t: None)
    monkeypatch.setattr(puente.time, "sleep", lambda _s: None)

    inicial = puente.ADAPTADOR.espera("chrome")
    with pytest.raises(ErrorFuente):
        puente._capturar(lambda: None, "error")
    assert puente.ADAPTADOR.espera("chrome") > inicial


# ===========================================================================
# Tabla de compatibilidad documentada
# ===========================================================================
def test_la_tabla_cubre_los_programas_habituales():
    esperados = [
        "Bloc de notas", "Microsoft Word", "LibreOffice Writer",
        "Google Docs (navegador)", "Notepad++", "Visual Studio Code",
    ]
    for programa in esperados:
        assert programa in puente.COMPATIBILIDAD


def test_cada_entrada_de_la_tabla_esta_completa():
    for programa, datos in puente.COMPATIBILIDAD.items():
        assert "insertar" in datos, programa
        assert "capturar" in datos, programa
        assert "notas" in datos, programa


def test_los_casos_problematicos_estan_documentados():
    """Un 'no funciona' documentado vale más que una sorpresa."""
    assert puente.COMPATIBILIDAD["PDF protegidos"]["insertar"] == "no"
    assert "tecleando" in puente.COMPATIBILIDAD["Terminal / PowerShell"]["insertar"]
