"""Tests del módulo de atajos.

No se levanta ningún escuchador real: se comprueba que el mapa se construye
bien y que los atajos solo ENCOLAN, que es la corrección de fondo respecto a
la versión anterior.
"""

import pytest

from vozclip import atajos


# -- Normalización de combinaciones ----------------------------------------
def test_normalizar_ya_correcto():
    assert atajos.normalizar("<ctrl>+<alt>+l") == "<ctrl>+<alt>+l"


def test_normalizar_forma_corta():
    """Si el usuario edita el config.json a mano y escribe la forma corta,
    debe seguir funcionando en vez de fallar en silencio."""
    assert atajos.normalizar("ctrl+alt+l") == "<ctrl>+<alt>+l"


def test_normalizar_sinonimos():
    assert atajos.normalizar("control+alt+g") == "<ctrl>+<alt>+g"
    assert atajos.normalizar("<ctrl>+<alt>+return") == "<ctrl>+<alt>+<enter>"


def test_normalizar_teclas_especiales():
    assert atajos.normalizar("ctrl+alt+up") == "<ctrl>+<alt>+<up>"
    assert atajos.normalizar("ctrl+alt+f5") == "<ctrl>+<alt>+<f5>"


def test_normalizar_ignora_espacios_y_mayusculas():
    assert atajos.normalizar(" CTRL + Alt + L ") == "<ctrl>+<alt>+l"


# -- Construcción del mapa --------------------------------------------------
def test_el_mapa_solo_encola():
    """Un atajo NO ejecuta la acción: mete su nombre en una cola.

    Este es el arreglo del bug original, así que merece su propio test.
    """
    recogidas = []
    mapa = atajos.construir_mapa(
        {"guardar": "<ctrl>+<alt>+d"}, recogidas.append
    )
    assert list(mapa) == ["<ctrl>+<alt>+d"]

    mapa["<ctrl>+<alt>+d"]()          # simulamos la pulsación
    assert recogidas == ["guardar"]


def test_cada_atajo_conserva_su_propia_accion():
    """Con un lambda dentro del bucle, todos apuntarían a la última acción."""
    recogidas = []
    mapa = atajos.construir_mapa(
        {
            "guardar": "<ctrl>+<alt>+d",
            "ayuda": "<ctrl>+<alt>+h",
            "salir": "<ctrl>+<alt>+q",
        },
        recogidas.append,
    )
    for disparar in mapa.values():
        disparar()
    assert sorted(recogidas) == ["ayuda", "guardar", "salir"]


def test_se_ignoran_acciones_desconocidas():
    mapa = atajos.construir_mapa(
        {"guardar": "<ctrl>+<alt>+d", "inventada": "<ctrl>+<alt>+z"},
        lambda _n: None,
        acciones_validas={"guardar"},
    )
    assert list(mapa) == ["<ctrl>+<alt>+d"]


def test_se_ignoran_combinaciones_vacias():
    mapa = atajos.construir_mapa({"guardar": ""}, lambda _n: None)
    assert mapa == {}


def test_un_fallo_al_encolar_no_propaga():
    """Si encolar explota, el hilo del teclado debe sobrevivir."""

    def explota(_nombre):
        raise RuntimeError("boom")

    mapa = atajos.construir_mapa({"guardar": "<ctrl>+<alt>+d"}, explota)
    mapa["<ctrl>+<alt>+d"]()   # no debe lanzar


def test_escuchador_falla_con_elegancia():
    """Sin entorno gráfico, arrancar() devuelve False en vez de reventar."""
    escuchador = atajos.EscuchadorAtajos({"<ctrl>+<alt>+d": lambda: None})
    resultado = escuchador.arrancar()
    assert resultado in (True, False)      # cualquiera vale, pero sin excepción
    escuchador.parar()


def test_todos_los_atajos_por_defecto_se_normalizan():
    from vozclip import config

    for nombre, combinacion in config.DEFAULTS["atajos"].items():
        normalizada = atajos.normalizar(combinacion)
        assert normalizada, f"El atajo '{nombre}' se normaliza a nada"


def test_los_cinco_comandos_diarios_van_sin_modificadores():
    """F1 a F5 van sueltas a propósito.

    Son los cinco comandos que Julián usa a todas horas: grabar, nuevo
    párrafo, nuevo diálogo, leer el último párrafo y leer todo. Tienen que
    poder pulsarse sin pensar y con una sola mano. Todo lo demás lleva
    Ctrl+Alt para no pisar los atajos de Word, del navegador ni de NVDA.
    """
    from vozclip import config

    sueltos = {
        nombre
        for nombre, combinacion in config.DEFAULTS["atajos"].items()
        if "<ctrl>" not in atajos.normalizar(combinacion)
        and "<alt>" not in atajos.normalizar(combinacion)
    }
    assert sueltos == {
        "dictar", "nuevo_parrafo", "nuevo_dialogo",
        "leer_ultimo_parrafo", "leer_texto_entero",
        "corregir", "cancelar_correccion",       # F9 y Escape
    }


def test_f1_se_normaliza_bien():
    assert atajos.normalizar("<f1>") == "<f1>"
    assert atajos.normalizar("f1") == "<f1>"
    assert atajos.normalizar("ctrl+alt+f1") == "<ctrl>+<alt>+<f1>"


def test_no_hay_atajos_duplicados_por_defecto():
    """Dos acciones con el mismo atajo harían que una fuese inalcanzable."""
    from vozclip import config

    combinaciones = list(config.DEFAULTS["atajos"].values())
    assert len(combinaciones) == len(set(combinaciones))


# -- Que pynput acepte de verdad cada atajo ---------------------------------
def test_pynput_acepta_todos_los_atajos_por_defecto():
    """La comprobación que faltaba.

    Antes solo se verificaba que la normalización produjera ALGO. Pero un
    atajo mal escrito no falla al normalizar: falla al registrarlo, y como
    el registro se hace dentro de un try, el atajo simplemente no existiría
    y nadie se enteraría. Aquí se le pide a pynput que lo interprete.
    """
    # `pytest.importorskip` no vale aquí: desde pytest 8 solo salta ante un
    # ModuleNotFoundError, y pynput lanza un ImportError genérico cuando no
    # encuentra servidor X. Hay que capturarlo a mano.
    try:
        from pynput import keyboard
    except ImportError as e:
        pytest.skip(f"pynput no se puede importar en este entorno: {e}")

    from vozclip import config

    for nombre, combinacion in config.DEFAULTS["atajos"].items():
        normalizada = atajos.normalizar(combinacion)
        try:
            keyboard.HotKey.parse(normalizada)
        except ValueError as e:
            pytest.fail(f"pynput rechaza el atajo '{nombre}' ({normalizada}): {e}")


def test_el_mas_y_el_menos_se_traducen_al_caracter():
    """pynput no tiene nombre para estas teclas: quiere el carácter."""
    assert atajos.normalizar("<ctrl>+<alt>+<plus>") == "<ctrl>+<alt>++"
    assert atajos.normalizar("<ctrl>+<alt>+<minus>") == "<ctrl>+<alt>+-"
    assert atajos.normalizar("ctrl+alt+mas") == "<ctrl>+<alt>++"
    assert atajos.normalizar("ctrl+alt+menos") == "<ctrl>+<alt>+-"


def test_hay_atajo_para_cada_grupo_de_funciones():
    """Un repaso de que no se ha quedado nada sin atajo."""
    from vozclip import config

    esperados = {
        # Los cinco de todos los días
        "dictar", "nuevo_parrafo", "nuevo_dialogo",
        "leer_ultimo_parrafo", "leer_texto_entero",
        "corregir", "cancelar_correccion",
        # Escritura
        "insertar_plantilla", "cambiar_plantilla", "aplicar_sangria",
        "quitar_sangria", "siguiente_linea", "siguiente_marca",
        # Archivos
        "importar", "exportar", "guardar", "guardar_como", "exportar_word",
        "exportar_libreoffice",
        # Configuración
        "importar_config", "exportar_config", "perfil_julian",
        # Lectura
        "leer_linea", "leer_seleccion", "leer_portapapeles", "leer_todo",
        "pausar_reanudar", "parar",
        # Vista
        "alto_contraste", "letra_mas_grande", "letra_mas_pequena", "modo_solo_voz",
        # Voz y navegación
        "mas_rapido", "mas_lento", "siguiente_voz", "cambiar_modo",
        "donde_estoy", "ayuda", "salir",
    }
    assert esperados == set(config.DEFAULTS["atajos"])
