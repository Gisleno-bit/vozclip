"""Tests del HUD.

Estos tests levantan una ventana de tkinter DE VERDAD. En un servidor hace
falta un display virtual (Xvfb); si no lo hay, se saltan solos:

    xvfb-run -a pytest tests/test_hud.py

Se comprueba que la ventana se construye, que los widgets existen, y que
cada acción hace lo que dice y lo anuncia por voz.
"""

from __future__ import annotations

import copy
import gc
import os

import pytest

tk = pytest.importorskip("tkinter", reason="tkinter no está instalado")

from vozclip import config, plantillas  # noqa: E402
from vozclip.voz import ServicioVoz  # noqa: E402


def _hay_pantalla() -> bool:
    """¿Se puede abrir una ventana de tkinter aquí y ahora?

    OJO: no basta con mirar el sistema operativo. En los runners de Windows
    de GitHub Actions, tkinter está instalado pero la instalación de Tcl/Tk
    del tool cache viene a veces incompleta, y `tk.Tk()` falla con
    "Can't find a usable init.tcl". Por eso la única comprobación fiable es
    intentar crear una ventana de verdad y ver qué pasa.
    """
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        return False
    try:
        raiz = tk.Tk()
        raiz.destroy()
        return True
    except Exception:
        # tk.TclError en un Tcl roto, pero también puede salir otra cosa
        return False


pytestmark = pytest.mark.skipif(
    not _hay_pantalla(),
    reason="Tkinter no puede abrir ventana aquí (falta display o Tcl/Tk roto)",
)


def crear_tk_o_saltar():
    """Crea una ventana, o salta el test si Tcl/Tk falla EN ESTE MOMENTO.

    El guardián de arriba se evalúa una sola vez, al importar el módulo. En
    los runners de Windows eso no basta: la instalación de Tcl/Tk del tool
    cache falla de forma INTERMITENTE (un `tk.Tk()` funciona y el siguiente
    se queja de que no encuentra ttk/notebook.tcl). Es un problema del
    entorno, no del proyecto, así que se salta el test en vez de teñir la
    CI de rojo.
    """
    try:
        return tk.Tk()
    except tk.TclError as e:
        pytest.skip(f"Tcl/Tk ha fallado al crear la ventana: {e}")


def _recoger_basura_tk() -> None:
    """Recoge los restos de la ventana AQUÍ, en el hilo principal.

    Si no se hace, los objetos de tkinter de las ventanas ya destruidas se
    quedan esperando a que alguien recoja la basura. Y en esta batería hay
    hilos de voz corriendo todo el rato: tarde o temprano el ciclo de
    recolección se dispara DENTRO de uno de esos hilos, que finaliza
    objetos Tk desde fuera del hilo principal. Tcl no lo tolera: llama a
    abort() y se lleva por delante el proceso entero, con un
    "Fatal Python error: Aborted" que no señala a ningún test concreto.

    Recogerla aquí, con el hilo principal y sin ventanas vivas, lo evita.
    """
    gc.collect()


@pytest.fixture
def hud():
    from vozclip.hud import HUD

    # Se comprueba Tcl/Tk ANTES de arrancar la voz: así, si hay que saltar,
    # no queda un hilo de voz suelto.
    crear_tk_o_saltar().destroy()

    voz = ServicioVoz(motor_forzado="falso")
    voz.arrancar()
    try:
        ajustes = copy.deepcopy(config.DEFAULTS)
        ventana = HUD(voz, ajustes)
        ventana.raiz.update()      # fuerza el dibujado real
        yield ventana
        try:
            # `detener_bucle` corta el bucle de `after` y vacía la cola de
            # eventos de Tcl. Sin eso, un callback pendiente se ejecuta
            # sobre un intérprete ya destruido y Tcl llama a abort().
            ventana.detener_bucle()
            ventana.raiz.destroy()
        except tk.TclError:
            pass
    finally:
        # Pase lo que pase, el hilo de voz se cierra. Dejarlos vivos hace
        # que se acumulen decenas de hilos durante la batería.
        voz.cerrar()
        _recoger_basura_tk()


def _dicho(hud) -> str:
    """Todo lo que se ha dicho hasta ahora, junto."""
    hud.voz.esperar_silencio(limite=3)
    return " ".join(hud.voz._motor.dicho)


# -- La ventana existe de verdad -------------------------------------------
def test_la_ventana_se_construye(hud):
    assert hud.raiz.winfo_exists()
    assert "VozClip Escritor" in hud.raiz.title()


def test_el_titulo_refleja_el_estado(hud):
    """El título es lo único que un lector de pantalla externo lee bien de
    una ventana de tkinter, así que lleva el archivo y el modo."""
    hud.modificado = True
    hud._refrescar_estado()
    titulo = hud.raiz.title()
    assert titulo.startswith("*")          # hay cambios sin guardar
    assert "editor" in titulo


def test_hay_once_botones_grandes(hud):
    assert len(hud.botones) == 11


def test_los_botones_van_agrupados_por_color(hud):
    """Cinco comandos en azul, guardar en verde, tres de archivo en naranja.
    Con baja visión, localizar un bloque de color cuesta mucho menos que
    leer nueve rótulos iguales."""
    assert hud.grupos_boton[:5] == ["comando"] * 5
    assert hud.grupos_boton[5] == "corregir"       # F9, color propio
    assert hud.grupos_boton[6] == "guardar"
    assert hud.grupos_boton[7:10] == ["archivo"] * 3
    assert hud.grupos_boton[10] == "libre"         # LibreOffice, color propio

    t = hud.tema
    assert hud.botones[0].cget("bg") == t["destacado"]
    assert hud.botones[5].cget("bg") == t["corregir"]
    assert hud.botones[6].cget("bg") == t["guardar"]
    assert hud.botones[7].cget("bg") == t["archivo"]
    assert hud.botones[10].cget("bg") == t["libre"]
    assert len({t["destacado"], t["corregir"], t["guardar"], t["archivo"], t["libre"]}) == 5
    for boton in hud.botones:
        assert boton.winfo_exists()
        assert boton.cget("takefocus")      # navegables con Tab


def test_el_editor_tiene_el_foco_al_abrir(hud):
    assert hud.editor.winfo_exists()
    assert hud.editor.cget("undo") in (1, True, "1")


def test_la_franja_de_estado_muestra_modo_y_plantilla(hud):
    estado = hud.etiqueta_estado.cget("text")
    assert "Modo" in estado
    assert "Plantilla" in estado
    assert "Velocidad" in estado


def test_el_saludo_suena(hud):
    hud.saludar()
    assert "VozClip Escritor" in _dicho(hud) and "en marcha" in _dicho(hud)


# -- Escritura --------------------------------------------------------------
def test_insertar_plantilla_mete_texto_y_coloca_el_cursor(hud):
    hud.accion_insertar_plantilla()
    contenido = hud._texto()
    assert contenido.strip()                     # plantilla de novela
    assert "|" not in contenido                  # las marcas desaparecen
    assert hud.marcas                            # pero quedan registradas
    assert hud._cursor() == hud.marcas[0]        # cursor en el primer hueco
    assert "insertada" in _dicho(hud)


def test_cambiar_plantilla_rota_y_lo_dice(hud):
    assert hud.plantilla.clave == "novela"
    hud.accion_cambiar_plantilla()
    assert hud.plantilla.clave == "narrativo"
    assert "diálogo narrativo" in _dicho(hud)
    assert "narrativo" in hud.etiqueta_estado.cget("text")


def test_insertar_plantilla_conserva_las_sangrias(hud):
    """La de novela abre con la sangría de narrador de 1,25 cm."""
    hud.accion_insertar_plantilla()
    assert hud._texto().startswith(plantillas.SANGRIA_NARRADOR)


def test_siguiente_marca_salta_al_hueco_siguiente(hud):
    hud.accion_insertar_plantilla()
    primero = hud._cursor()
    hud.accion_siguiente_marca()
    assert hud._cursor() > primero
    assert hud._cursor() in hud.marcas


def test_aplicar_sangria(hud):
    hud.editor.insert("1.0", "diálogo del personaje")
    hud.editor.mark_set("insert", "1.0 + 5 chars")
    hud.accion_aplicar_sangria()
    assert hud._texto().startswith(hud.plantilla.sangria_parrafo)
    assert "Sangría" in _dicho(hud)


def test_quitar_sangria(hud):
    sangria = hud.plantilla.sangria_parrafo
    hud.editor.insert("1.0", sangria + "diálogo")
    hud.editor.mark_set("insert", f"1.0 + {len(sangria) + 2} chars")
    hud.accion_quitar_sangria()
    assert hud._texto() == "diálogo"


def test_quitar_sangria_sin_sangria_avisa(hud):
    hud.editor.insert("1.0", "diálogo")
    hud.accion_quitar_sangria()
    assert "no tiene sangría" in _dicho(hud)


def test_siguiente_linea_anade_salto_y_lo_anuncia(hud):
    hud.editor.insert("1.0", "        primera réplica")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_siguiente_linea()
    assert hud._texto().count("\n") == 1
    assert "Línea 2" in _dicho(hud)


# -- Lectura ----------------------------------------------------------------
def test_leer_linea_dice_numero_y_contenido(hud):
    hud.editor.insert("1.0", "primera\nsegunda réplica")
    hud.editor.mark_set("insert", "2.3")
    hud.accion_leer_linea()
    dicho = _dicho(hud)
    assert "Línea 2" in dicho
    assert "segunda réplica" in dicho


def test_leer_todo_documento_vacio_avisa(hud):
    hud.accion_leer_todo()
    assert "vacío" in _dicho(hud)


def test_leer_todo_lee_el_contenido(hud):
    hud.editor.insert("1.0", "Contenido del guion completo.")
    hud.accion_leer_todo()
    assert "Contenido del guion" in _dicho(hud)


def test_leer_seleccion_sin_seleccion_avisa(hud):
    hud.editor.insert("1.0", "texto")
    hud.accion_leer_seleccion()
    assert "nada seleccionado" in _dicho(hud)


def test_leer_seleccion_con_seleccion(hud):
    hud.editor.insert("1.0", "primera parte y segunda parte")
    hud.editor.tag_add("sel", "1.0", "1.13")
    hud.accion_leer_seleccion()
    assert "primera parte" in _dicho(hud)


def test_donde_estoy_resume_el_contexto(hud):
    hud.editor.insert("1.0", "una réplica cualquiera")
    hud.accion_donde_estoy()
    dicho = _dicho(hud)
    assert "Modo editor propio" in dicho
    assert "palabras" in dicho


def test_ayuda_enumera_los_atajos(hud):
    hud.accion_ayuda()
    dicho = _dicho(hud)
    assert "plantilla" in dicho.lower()
    assert "guardar" in dicho.lower()


# -- Ajustes ----------------------------------------------------------------
def test_velocidad_sube_y_se_refleja_en_la_franja(hud):
    hud.accion_mas_rapido()
    assert hud.ajustes["velocidad"] == 1
    assert "Velocidad: 1" in hud.etiqueta_estado.cget("text")
    assert "Velocidad 1" in _dicho(hud)


def test_velocidad_tiene_topes(hud):
    for _ in range(20):
        hud.accion_mas_rapido()
    assert hud.ajustes["velocidad"] == 10


def test_cambiar_modo_ida_y_vuelta(hud):
    assert hud.modo == "editor"
    hud.accion_cambiar_modo()
    assert hud.modo == "externo"
    assert "Aplicación externa" in hud.etiqueta_estado.cget("text")
    hud.accion_cambiar_modo()
    assert hud.modo == "editor"


def test_siguiente_voz_rota(hud):
    hud.accion_siguiente_voz()
    primera = hud.ajustes["voz"]
    hud.accion_siguiente_voz()
    assert hud.ajustes["voz"] != primera


# -- Archivos ---------------------------------------------------------------
def test_guardar_crea_el_archivo_y_dice_el_nombre(hud, tmp_path):
    hud.ajustes["carpeta_guiones"] = str(tmp_path)
    hud.editor.insert("1.0", "INT. CASA - DÍA\n\nAlguien entra.")
    hud.accion_guardar()

    assert hud.ruta_actual is not None
    assert hud.ruta_actual.exists()
    assert "INT. CASA" in hud.ruta_actual.read_text(encoding="utf-8")
    assert "Guardado como" in _dicho(hud)


def test_abrir_carga_el_archivo(hud, tmp_path):
    origen = tmp_path / "guion.txt"
    origen.write_text("ESCENA PRIMERA\nEntra el personaje.", encoding="utf-8")

    hud.abrir(origen)
    assert "ESCENA PRIMERA" in hud._texto()
    assert hud.ruta_actual == origen
    assert "Abierto guion.txt" in _dicho(hud)


def test_abrir_archivo_inexistente_avisa(hud, tmp_path):
    hud.abrir(tmp_path / "no_existe.txt")
    assert "No encuentro el archivo" in _dicho(hud)


# -- La cola de órdenes (integración teclado -> ventana) --------------------
def test_una_orden_encolada_se_ejecuta_en_el_hilo_principal(hud):
    """Esto es lo que hace un atajo global: encolar. Aquí lo simulamos."""
    hud.encolar_orden("cambiar_plantilla")
    hud._atender_cola()              # lo que hace el bucle cada 50 ms
    assert hud.plantilla.clave == "narrativo"


def test_orden_desconocida_no_rompe_el_bucle(hud):
    hud.encolar_orden("accion_que_no_existe")
    hud._atender_cola()              # no debe lanzar
    hud.encolar_orden("cambiar_plantilla")
    hud._atender_cola()
    assert hud.plantilla.clave == "narrativo"


def test_todos_los_atajos_por_defecto_apuntan_a_acciones_reales(hud):
    """Un atajo configurado sin acción detrás sería un botón muerto."""
    disponibles = set(hud.acciones())
    for nombre in config.DEFAULTS["atajos"]:
        assert nombre in disponibles, f"El atajo '{nombre}' no tiene acción"


def test_el_primer_boton_es_el_de_dictar(hud):
    """Va el primero porque es la acción principal para quien no teclea."""
    assert "Grabar" in hud.botones[0].cget("text")
    assert "F1" in hud.botones[0].cget("text")
    assert hud.botones[0].cget("text").startswith("1.")   # también Alt+1


def test_todas_las_plantillas_se_pueden_insertar(hud):
    for clave in plantillas.ORDEN:
        hud.plantilla = plantillas.obtener(clave)
        hud.editor.delete("1.0", "end")
        hud.accion_insertar_plantilla()
        assert hud._texto().strip(), f"La plantilla {clave} insertó texto vacío"
        assert "|" not in hud._texto()


# ===========================================================================
# Dictado por voz
# ===========================================================================
@pytest.fixture
def hud_con_dictado():
    """HUD con un servicio de dictado falso, controlable desde el test."""
    from vozclip import dictado as moddictado
    from vozclip.hud import HUD
    from vozclip.voz import ServicioVoz

    crear_tk_o_saltar().destroy()

    voz = ServicioVoz(motor_forzado="falso")
    voz.arrancar()
    ajustes = copy.deepcopy(config.DEFAULTS)

    def fabrica(notificar):
        return moddictado.ServicioDictado(
            notificar=notificar,
            ajustes={"activado": True, "modelo": "fingido"},
            fabrica_motor=lambda: moddictado.MotorDictadoFalso(
                ["hola coma qué tal punto"]
            ),
            fabrica_captura=lambda: moddictado.CapturaFalsa(),
            voz=voz,
        )

    try:
        ventana = HUD(voz, ajustes, fabrica_dictado=fabrica)
        ventana.raiz.update()
        yield ventana
        try:
            ventana.detener_bucle()
            ventana.servicio_dictado.cerrar()
            ventana.raiz.destroy()
        except Exception:
            pass
    finally:
        voz.cerrar()
        _recoger_basura_tk()


def _completar_dictado(hud, limite=5.0):
    """Espera a que el hilo de dictado acabe y procesa su cola."""
    import time as _t

    plazo = _t.monotonic() + limite
    while hud.servicio_dictado.activo and _t.monotonic() < plazo:
        hud._atender_dictado()
        hud.raiz.update()
        _t.sleep(0.02)
    _t.sleep(0.1)
    hud._atender_dictado()
    hud.raiz.update()


def test_el_servicio_de_dictado_se_crea(hud_con_dictado):
    assert hud_con_dictado.servicio_dictado is not None
    assert hud_con_dictado.dictando is False


def test_f1_inserta_el_texto_dictado(hud_con_dictado):
    hud = hud_con_dictado
    hud.accion_dictar()
    _completar_dictado(hud)
    # El dictado dijo "hola coma qué tal punto"
    assert "Hola, qué tal." in hud._texto()


def test_el_indicador_se_enciende_al_empezar(hud_con_dictado):
    hud = hud_con_dictado
    hud._procesar_evento_dictado("inicio", None)
    assert "ESCUCHANDO" in hud.etiqueta_dictado.cget("text")
    assert hud.dictando is True


def test_el_indicador_se_apaga_al_terminar(hud_con_dictado):
    hud = hud_con_dictado
    hud._procesar_evento_dictado("inicio", None)
    hud._procesar_evento_dictado("fin", None)
    assert hud.dictando is False
    assert "ESCUCHANDO" not in hud.etiqueta_dictado.cget("text")


def test_el_parcial_se_ve_pero_no_se_habla(hud_con_dictado):
    """Hablar los parciales interrumpiría al usuario justo mientras dicta."""
    hud = hud_con_dictado
    hud.voz._motor.dicho.clear()
    hud._procesar_evento_dictado("parcial", "media frase")
    hud.voz.esperar_silencio(limite=2)
    assert "media frase" in hud.etiqueta_dictado.cget("text")
    assert hud.voz._motor.dicho == []


def test_un_error_de_dictado_se_dice_en_voz_alta(hud_con_dictado):
    hud = hud_con_dictado
    hud.voz._motor.dicho.clear()
    hud._procesar_evento_dictado("error", "No hay ningún micrófono conectado.")
    hud.voz.esperar_silencio(limite=3)
    assert any("micrófono" in t for t in hud.voz._motor.dicho)
    assert "micrófono" in hud.etiqueta_dictado.cget("text")


def test_el_dictado_respeta_la_sangria_de_la_plantilla(hud_con_dictado):
    """Lo esencial: si dictas dentro de un diálogo de cine, la línea nueva
    sale alineada con las demás."""
    hud = hud_con_dictado
    hud.plantilla = plantillas.obtener("cine")
    hud.editor.delete("1.0", "end")
    hud.editor.insert("1.0", "                    ELENA\n          ")
    hud.editor.mark_set("insert", "end-1c")

    hud._procesar_evento_dictado("texto", "no me lo creo punto y aparte y me voy")

    lineas = hud._texto().split("\n")
    assert lineas[-1].startswith("          "), "La línea nueva perdió la sangría"
    assert "Y me voy" in lineas[-1]


def test_el_dictado_continua_una_frase_empezada(hud_con_dictado):
    hud = hud_con_dictado
    hud.editor.delete("1.0", "end")
    hud.editor.insert("1.0", "El personaje dice")
    hud.editor.mark_set("insert", "end-1c")

    hud._procesar_evento_dictado("texto", "que no piensa volver")
    assert hud._texto() == "El personaje dice que no piensa volver"


def test_el_dictado_marca_el_documento_como_modificado(hud_con_dictado):
    hud = hud_con_dictado
    hud.modificado = False
    hud._procesar_evento_dictado("texto", "algo dictado")
    assert hud.modificado is True


def test_el_texto_insertado_se_confirma_en_voz(hud_con_dictado):
    hud = hud_con_dictado
    hud.voz._motor.dicho.clear()
    hud._procesar_evento_dictado("texto", "prueba de confirmación")
    hud.voz.esperar_silencio(limite=3)
    assert any("Escrito" in t for t in hud.voz._motor.dicho)


def test_dictar_sin_servicio_avisa_y_no_rompe(hud):
    """Sin librería, sin modelo o sin micrófono, el resto sigue igual."""
    hud.servicio_dictado = None
    hud.accion_dictar()
    assert "no está disponible" in _dicho(hud)
    # Y el editor sigue funcionando
    hud.accion_insertar_plantilla()
    assert hud._texto().strip()


def test_dictar_esta_entre_las_acciones(hud):
    assert "dictar" in hud.acciones()


def test_la_ayuda_menciona_el_dictado(hud):
    hud.accion_ayuda()
    assert "efe uno" in _dicho(hud).lower()


# ===========================================================================
# Accesibilidad: temas, tamaño de letra y modo solo voz
# ===========================================================================
def test_arranca_en_tema_oscuro(hud):
    from vozclip.hud import TEMAS

    assert hud.tema is TEMAS["oscuro"]


def test_el_contraste_rota_entre_los_tres_temas(hud):
    from vozclip.hud import ORDEN_TEMAS

    vistos = []
    for _ in range(len(ORDEN_TEMAS)):
        hud.accion_alto_contraste()
        vistos.append(hud.ajustes["tema"])
    assert sorted(vistos) == sorted(ORDEN_TEMAS)


def test_el_tema_de_alto_contraste_es_negro_y_amarillo(hud):
    """Negro puro con amarillo puro da la relación de contraste máxima."""
    from vozclip.hud import TEMAS

    t = TEMAS["alto_contraste"]
    assert t["fondo"] == "#000000"
    assert t["acento"] == "#ffff00"
    assert t["texto"] == "#ffffff"


def test_cambiar_de_tema_repinta_el_editor(hud):
    hud.ajustes["tema"] = "alto_contraste"
    hud._aplicar_tema()
    assert hud.editor.cget("bg") == "#000000"
    assert hud.editor.cget("fg") == "#ffffff"


def test_el_cambio_de_tema_se_anuncia(hud):
    hud.accion_alto_contraste()
    assert "Tema" in _dicho(hud)


def test_la_letra_crece_y_mengua(hud):
    inicial = hud.tamano
    hud.accion_letra_mas_grande()
    assert hud.tamano > inicial
    hud.accion_letra_mas_pequena()
    assert hud.tamano == inicial


def test_la_letra_tiene_topes(hud):
    from vozclip.hud import TAMANO_MAXIMO, TAMANO_MINIMO

    for _ in range(40):
        hud.accion_letra_mas_grande()
    assert hud.tamano == TAMANO_MAXIMO
    for _ in range(60):
        hud.accion_letra_mas_pequena()
    assert hud.tamano == TAMANO_MINIMO


def test_al_subir_la_letra_crecen_tambien_los_botones(hud):
    """Si alguien sube la letra porque no ve, no tiene sentido que los
    botones se queden pequeños."""
    antes = hud.botones[0].cget("font")
    hud.accion_letra_mas_grande()
    hud.accion_letra_mas_grande()
    assert hud.botones[0].cget("font") != antes


def test_el_tamano_se_ve_en_la_franja_de_estado(hud):
    hud.accion_letra_mas_grande()
    assert f"Letra: {hud.tamano}" in hud.etiqueta_estado.cget("text")


def test_el_cursor_no_parpadea_por_defecto(hud):
    """Un cursor parpadeando es un elemento en movimiento permanente:
    cansa a quien tiene fatiga visual."""
    assert int(hud.editor.cget("insertofftime")) == 0


def test_modo_solo_voz_esconde_la_interfaz(hud):
    hud.accion_modo_solo_voz()
    hud.raiz.update()
    assert hud.ajustes["solo_voz"] is True
    assert not hud.editor.winfo_ismapped()
    assert not hud.botones[0].winfo_ismapped()


def test_modo_solo_voz_se_puede_deshacer(hud):
    hud.accion_modo_solo_voz()
    hud.raiz.update()
    hud.accion_modo_solo_voz()
    hud.raiz.update()
    assert hud.ajustes["solo_voz"] is False
    assert hud.editor.winfo_ismapped()
    assert hud.botones[0].winfo_ismapped()


def test_en_modo_solo_voz_los_atajos_siguen_funcionando(hud):
    """La ventana se esconde, pero el programa entero sigue igual."""
    hud.accion_modo_solo_voz()
    hud.raiz.update()
    hud.encolar_orden("cambiar_plantilla")
    hud._atender_cola()
    assert hud.plantilla.clave == "narrativo"


def test_los_botones_son_navegables_con_tabulador(hud):
    for boton in hud.botones:
        assert boton.cget("takefocus")
        assert int(boton.cget("highlightthickness")) >= 2   # el foco se ve


def test_cada_boton_lleva_su_numero_para_alt(hud):
    for i, boton in enumerate(hud.botones, start=1):
        assert boton.cget("text").startswith(f"{i}.")


def test_f6_salta_entre_editor_y_botones(hud):
    hud.editor.focus_set()
    hud.raiz.update()
    hud.accion_siguiente_foco()
    hud.raiz.update()
    assert hud.raiz.focus_get() is not hud.editor


# ===========================================================================
# Importar y exportar
# ===========================================================================
def test_exportar_copia_al_portapapeles(hud, monkeypatch):
    copiado = {}
    monkeypatch.setattr(
        "vozclip.hud.escribir_portapapeles", lambda t: copiado.setdefault("texto", t)
    )
    hud.editor.insert("1.0", "INT. CASA - DÍA\n\nEntra Elena.")
    hud.accion_exportar()
    assert "INT. CASA" in copiado["texto"]
    assert "portapapeles" in _dicho(hud)


def test_exportar_un_documento_vacio_avisa(hud):
    hud.accion_exportar()
    assert "vacío" in _dicho(hud)


def test_exportar_en_modo_externo_escribe_en_la_app(hud, monkeypatch):
    escrito = {}

    def falso_insertar(texto, metodo="auto"):
        escrito["texto"] = texto
        return "pegar"

    monkeypatch.setattr("vozclip.puente.insertar_texto", falso_insertar)
    monkeypatch.setattr("vozclip.puente.describir_destino", lambda: "Documento1 - Word")

    hud.modo = "externo"
    hud.editor.insert("1.0", "Contenido del guion")
    hud.accion_exportar()

    assert escrito["texto"] == "Contenido del guion"
    assert "Word" in _dicho(hud)


def test_importar_conserva_las_sangrias_en_el_editor(hud, tmp_path):
    """La prueba de fuego: un guion de cine importado mantiene sus márgenes."""
    ruta = tmp_path / "guion.txt"
    ruta.write_text(
        "INT. CASA - DÍA\n\n                    ELENA\n          No me lo creo.\n",
        encoding="utf-8",
    )
    hud.abrir(ruta)
    lineas = hud._texto().split("\n")
    assert lineas[2].startswith(" " * 20)
    assert lineas[3].startswith(" " * 10)


def test_importar_un_rtf(hud, tmp_path):
    ruta = tmp_path / "guion.rtf"
    ruta.write_text(
        r"{\rtf1\ansi\deff0 \pard Texto en erre te efe\par}", encoding="latin-1"
    )
    hud.abrir(ruta)
    assert "Texto en erre te efe" in hud._texto()


def test_importar_algo_ilegible_avisa_sin_romper(hud, tmp_path):
    ruta = tmp_path / "documento.pdf"
    ruta.write_bytes(b"%PDF falso")
    hud.abrir(ruta)
    assert "no se pueden editar" in _dicho(hud)
    hud.accion_insertar_plantilla()          # el editor sigue vivo
    assert hud._texto().strip()


def test_importar_de_la_app_externa(hud, monkeypatch):
    monkeypatch.setattr(
        "vozclip.puente.capturar_todo", lambda: "Texto traído desde Word"
    )
    hud.accion_importar_de_app_externa()
    assert "Texto traído desde Word" in hud._texto()


def test_guardado_atomico_no_deja_temporales(hud, tmp_path):
    hud.ajustes["carpeta_guiones"] = str(tmp_path)
    hud.editor.insert("1.0", "contenido")
    hud.accion_guardar()
    assert list(tmp_path.glob("*.tmp")) == []


def test_las_acciones_nuevas_estan_registradas(hud):
    for nombre in (
        "importar", "exportar", "guardar_como", "alto_contraste",
        "letra_mas_grande", "letra_mas_pequena", "modo_solo_voz",
    ):
        assert nombre in hud.acciones(), f"Falta la acción '{nombre}'"


def test_la_ayuda_cubre_las_funciones_nuevas(hud):
    hud.accion_ayuda()
    dicho = _dicho(hud).lower()
    for concepto in ("importar", "exportar", "contraste", "solo voz", "efe seis"):
        assert concepto in dicho, f"La ayuda no menciona '{concepto}'"


def test_la_botonera_se_reparte_en_filas_con_letra_grande(hud):
    """Regresión de un fallo que se vio en la captura: con letra de 24
    puntos, ocho botones en una fila dejaban rótulos como '6. Importa'.
    Justo el caso de quien ha subido la letra porque no ve bien."""
    assert hud.columnas_botonera() == 6       # dos filas de seis
    hud.ajustes["tamano_fuente"] = 22
    assert hud.columnas_botonera() == 6       # siguen siendo dos filas


def test_la_botonera_siempre_son_dos_filas_de_seis(hud):
    """El texto del guion llega a 42 puntos, pero los rótulos se topan en
    22. Si los botones creciesen sin límite, acabarían ocupando la ventana
    entera y empujando al editor fuera: lo contrario de lo que busca quien
    ha subido la letra."""
    from vozclip.hud import TAMANO_MAXIMO

    hud.ajustes["tamano_fuente"] = TAMANO_MAXIMO
    assert hud.columnas_botonera() == 6


def test_los_rotulos_de_la_interfaz_tienen_tope(hud):
    from vozclip.hud import TAMANO_UI_MAXIMO

    hud.ajustes["tamano_fuente"] = 42
    _familia, puntos, *_ = hud._fuente_ui(1.0)
    assert puntos <= TAMANO_UI_MAXIMO

    # El editor, en cambio, sí crece hasta el máximo
    assert hud._fuente_editor()[1] == 42


def test_los_botones_se_recolocan_al_crecer_la_letra(hud):
    for _ in range(6):
        hud.accion_letra_mas_grande()
    hud.raiz.update()
    filas = {b.grid_info()["row"] for b in hud.botones}
    assert len(filas) > 1, "Los botones siguen en una sola fila"


def test_el_editor_sigue_visible_con_letra_grande(hud):
    """La botonera no debe crecer hasta empujar el editor fuera."""
    for _ in range(8):
        hud.accion_letra_mas_grande()
    hud.raiz.update()
    assert hud.editor.winfo_ismapped()


def test_los_rotulos_no_se_recortan(hud):
    """`wraplength` en 0 o demasiado bajo recorta el texto del botón."""
    hud.raiz.update()
    for boton in hud.botones:
        assert int(boton.cget("wraplength")) >= 150


def test_detener_bucle_deja_la_ventana_lista_para_destruir(hud):
    """Regresión del `Fatal Python error: Aborted`.

    Cancelar el `after` no basta: si el temporizador ya saltó, su callback
    está esperando turno en la cola de eventos de Tcl y se ejecutará
    igualmente sobre un intérprete destruido. `detener_bucle` pone la
    bandera, cancela y vacía la cola.
    """
    assert hud._tarea_cola is not None, "El bucle de eventos no está programado"
    hud.detener_bucle()
    assert hud._cerrando is True
    assert hud._tarea_cola is None


def test_el_bucle_no_toca_una_ventana_cerrada(hud):
    """Aunque el callback llegue a ejecutarse, tiene que salir sin hacer
    nada en vez de tocar widgets que ya no existen."""
    hud.detener_bucle()
    hud.encolar_orden("cambiar_plantilla")
    hud._atender_cola()                       # no debe lanzar
    assert hud.plantilla.clave == "novela"    # ni ejecutar la orden


def test_detener_bucle_se_puede_llamar_dos_veces(hud):
    hud.detener_bucle()
    hud.detener_bucle()      # idempotente: no debe lanzar


def test_el_bucle_procesa_las_ordenes_por_su_cuenta(hud):
    """Que el bucle esté PROGRAMADO, no solo que funcione al llamarlo.

    Los demás tests invocan `_atender_cola()` a mano, así que no verían
    que el `after` inicial hubiera desaparecido. En la aplicación real eso
    dejaría los atajos globales y el dictado sin procesar nunca.
    """
    import time as _t

    hud.encolar_orden("cambiar_plantilla")
    plazo = _t.monotonic() + 3
    while hud.plantilla.clave == "novela" and _t.monotonic() < plazo:
        hud.raiz.update()
        _t.sleep(0.02)

    assert hud.plantilla.clave == "narrativo", "El bucle de eventos no está programado"


# ===========================================================================
# Los cinco comandos de todos los días
# ===========================================================================
def test_nuevo_parrafo_abre_con_sangria(hud):
    hud.editor.insert("1.0", "     Aquella noche no dormí.")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_nuevo_parrafo()

    lineas = hud._texto().split("\n")
    assert lineas[1] == ""                                   # línea de separación
    assert lineas[2] == hud.plantilla.sangria_parrafo        # sangría de párrafo
    assert "Nuevo párrafo" in _dicho(hud)


def test_nuevo_parrafo_deja_el_cursor_listo(hud):
    hud.editor.insert("1.0", "     Texto.")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_nuevo_parrafo()
    assert hud._cursor() == len(hud._texto())


def test_nuevo_parrafo_no_encadena_lineas_vacias(hud):
    """Si ya estás en una línea vacía, se aprovecha en vez de abrir otra."""
    hud.editor.insert("1.0", "     Texto.\n\n")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_nuevo_parrafo()
    assert hud._texto().count("\n\n\n") == 0


def test_nuevo_dialogo_en_novela_pone_sangria_y_raya_pegada(hud):
    """El formato de Julián: dos espacios (0,63 cm), la raya PEGADA a ellos,
    y el cursor justo detrás. Sin espacio después de la raya, sin nombre de
    personaje, sin nada más."""
    hud.editor.insert("1.0", "     Aquella noche no dormí.")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_nuevo_dialogo()

    lineas = hud._texto().split("\n")
    assert lineas[-1] == "  \u2014"              # sangría + raya, nada más
    assert hud._cursor() == len(hud._texto())    # cursor detrás de la raya
    assert "Nuevo diálogo" in _dicho(hud)


def test_f3_no_anade_espacio_tras_la_raya(hud):
    """En castellano la raya de diálogo va pegada a la primera palabra."""
    hud.plantilla = plantillas.obtener("narrativo")
    hud.editor.insert("1.0", "Texto previo.")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_nuevo_dialogo()
    assert not hud._texto().endswith(" ")
    assert hud._texto().endswith("—")


def test_nuevo_parrafo_no_interfiere_con_el_dialogo(hud):
    """F2 tras F3: el párrafo nuevo lleva su propia sangría de narrador,
    no arrastra la raya ni la sangría de diálogo."""
    hud.editor.insert("1.0", "     Narrador.")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_nuevo_dialogo()
    hud.editor.insert("insert", "No me lo creo.")
    hud.accion_nuevo_parrafo()

    lineas = hud._texto().split("\n")
    assert lineas[-1] == hud.plantilla.sangria_parrafo
    assert "—" not in lineas[-1]


def test_f3_nunca_pone_un_nombre_de_personaje(hud):
    """En NINGUNA plantilla. Era lo que se colaba con un config antiguo."""
    for clave in plantillas.ORDEN:
        hud.plantilla = plantillas.obtener(clave)
        hud.editor.delete("1.0", "end")
        hud.editor.insert("1.0", "Texto previo.")
        hud.editor.mark_set("insert", "end-1c")
        hud.accion_nuevo_dialogo()

        ultima = hud._texto().split("\n")[-1]
        assert ultima == "  \u2014", f"{clave} produjo {ultima!r}"
        assert "PERSONAJE" not in hud._texto()


def test_leer_ultimo_parrafo(hud):
    hud.editor.insert(
        "1.0",
        "     Primer párrafo del capítulo.\n\n     Segundo párrafo, el bueno.",
    )
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_leer_ultimo_parrafo()

    dicho = _dicho(hud)
    assert "Segundo párrafo, el bueno." in dicho
    assert "Primer párrafo" not in dicho          # solo el párrafo, no todo


def test_leer_ultimo_parrafo_con_documento_vacio(hud):
    hud.accion_leer_ultimo_parrafo()
    assert "vacío" in _dicho(hud)


def test_leer_ultimo_parrafo_desde_una_linea_en_blanco(hud):
    """Si el cursor está en el hueco entre párrafos, se lee el último."""
    hud.editor.insert("1.0", "     Un párrafo escrito.\n\n")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_leer_ultimo_parrafo()
    assert "Un párrafo escrito." in _dicho(hud)


def test_los_comandos_estan_registrados(hud):
    for nombre in ("nuevo_parrafo", "nuevo_dialogo", "leer_ultimo_parrafo",
                   "leer_texto_entero", "exportar_word",
                   "importar_config", "exportar_config", "perfil_julian"):
        assert nombre in hud.acciones(), f"Falta la acción '{nombre}'"


# ===========================================================================
# Exportar a Word desde el HUD
# ===========================================================================
def test_exportar_a_word_crea_el_archivo(hud, tmp_path):
    pytest.importorskip("docx")
    hud.ajustes["carpeta_guiones"] = str(tmp_path)
    hud.editor.insert("1.0", "     Un párrafo.\n\n— Y un diálogo.")
    hud.accion_exportar_word()

    archivos = list(tmp_path.glob("*.docx"))
    assert archivos, "No se creó ningún .docx"
    assert "Word" in _dicho(hud)


def test_exportar_a_word_usa_el_nombre_del_guion(hud, tmp_path):
    pytest.importorskip("docx")
    hud.ajustes["carpeta_guiones"] = str(tmp_path)
    hud.editor.insert("1.0", "     Texto.")
    hud.accion_guardar()
    hud.accion_exportar_word()

    esperado = hud.ruta_actual.with_suffix(".docx")
    assert esperado.exists()


def test_exportar_a_word_con_documento_vacio(hud):
    hud.accion_exportar_word()
    assert "vacío" in _dicho(hud)


# ===========================================================================
# Perfiles desde el HUD
# ===========================================================================
def test_cargar_un_perfil_lo_aplica_todo(hud, tmp_path):
    from vozclip import perfiles

    ruta = perfiles.exportar(
        {"tema": "claro", "tamano_fuente": 30, "velocidad": -3,
         "plantilla": "narrativo"},
        tmp_path / "otro.json",
        nombre="Prueba",
    )
    assert hud.cargar_perfil(ruta) is True

    assert hud.ajustes["tema"] == "claro"
    assert hud.tamano == 30
    assert hud.plantilla.clave == "narrativo"
    assert hud.editor.cget("bg") == hud.tema["editor"]
    assert "Prueba" in _dicho(hud)


def test_un_perfil_invalido_no_descoloca_nada(hud, tmp_path):
    import json

    ruta = tmp_path / "malo.json"
    ruta.write_text(json.dumps({"tema": "arcoiris"}), encoding="utf-8")

    tema_antes = hud.ajustes["tema"]
    assert hud.cargar_perfil(ruta) is False
    assert hud.ajustes["tema"] == tema_antes
    assert "no existe" in _dicho(hud)


def test_exportar_la_configuracion(hud, tmp_path, monkeypatch):
    from vozclip import perfiles

    monkeypatch.setattr(perfiles, "carpeta_perfiles", lambda: tmp_path)
    hud.accion_exportar_config()

    assert list(tmp_path.glob("*.json"))
    assert "guardada" in _dicho(hud)


def test_volver_al_perfil_de_julian(hud):
    """La salida de emergencia: si algo se descoloca y no puedes ver la
    pantalla, esto devuelve el programa a un estado conocido."""
    hud.ajustes["tema"] = "claro"
    hud.ajustes["tamano_fuente"] = 40
    hud.plantilla = plantillas.obtener("escaleta")

    hud.accion_perfil_julian()

    assert hud.ajustes["tema"] == "alto_contraste"
    assert hud.tamano == 20
    assert hud.plantilla.clave == "novela"
    assert "Julián" in _dicho(hud)



# ===========================================================================
# Exportar a LibreOffice desde el HUD
# ===========================================================================
def test_exportar_a_libreoffice_crea_el_odt(hud, tmp_path):
    from vozclip import exportar_odt

    hud.ajustes["carpeta_guiones"] = str(tmp_path)
    hud.editor.insert("1.0", "     Un párrafo.\n\n  —Y un diálogo.")
    hud.accion_exportar_libreoffice()

    archivos = list(tmp_path.glob("*.odt"))
    assert archivos, "No se creó ningún .odt"
    d = exportar_odt.leer(archivos[0])
    assert [p["estilo"] for p in d["parrafos"]] == ["Narrador", "Dialogo"]
    assert "LibreOffice" in _dicho(hud)


def test_exportar_a_libreoffice_usa_el_nombre_del_guion(hud, tmp_path):
    hud.ajustes["carpeta_guiones"] = str(tmp_path)
    hud.editor.insert("1.0", "     Texto.")
    hud.accion_guardar()
    hud.accion_exportar_libreoffice()
    assert hud.ruta_actual.with_suffix(".odt").exists()


def test_exportar_a_libreoffice_con_documento_vacio(hud):
    hud.accion_exportar_libreoffice()
    assert "vacío" in _dicho(hud)


def test_el_ultimo_boton_es_libreoffice(hud):
    assert "LibreOffice" in hud.botones[10].cget("text")
    assert hud.botones[10].cget("text").startswith("11.")


def test_txt_docx_y_odt_conviven(hud, tmp_path):
    """Las tres salidas existen a la vez: guardar sigue dejando el .txt."""
    pytest.importorskip("docx")
    hud.ajustes["carpeta_guiones"] = str(tmp_path)
    hud.editor.insert("1.0", "     Texto.\n\n  —Diálogo.")
    hud.accion_guardar()
    hud.accion_exportar_word()
    hud.accion_exportar_libreoffice()

    base = hud.ruta_actual
    assert base.with_suffix(".txt").exists()
    assert base.with_suffix(".docx").exists()
    assert base.with_suffix(".odt").exists()


# ===========================================================================
# Regresión: la raya salía doble al pulsar F3
# ===========================================================================
def _procesar_cola(hud, segundos=0.4):
    import time as _t

    fin = _t.monotonic() + segundos
    while _t.monotonic() < fin:
        hud.raiz.update()
        _t.sleep(0.02)


def test_f3_con_la_ventana_enfocada_inserta_una_sola_raya(hud):
    """Cada tecla tiene dos rutas: el bind_all de tkinter y el atajo global
    de pynput. Con la ventana enfocada, una pulsación llegaba por las dos y
    la raya salía doble. La global debe ceder cuando hay foco."""
    from vozclip.atajos import construir_mapa

    hud.raiz.focus_force()
    hud.raiz.update()
    if not hud._ventana_tiene_foco():
        pytest.skip("El servidor gráfico no da el foco a la ventana")

    mapa = construir_mapa(config.DEFAULTS["atajos"], hud.encolar_orden_global,
                          set(hud.acciones()))
    hud.editor.insert("1.0", "Texto previo.")
    hud.editor.mark_set("insert", "end-1c")

    hud.raiz.event_generate("<F3>")       # ruta local
    mapa["<f3>"]()                        # ruta global, en la misma pulsación
    _procesar_cola(hud)

    assert hud._texto().count("\u2014") == 1
    assert hud._texto().split("\n")[-1] == "  \u2014"


def test_f3_dos_veces_da_dos_rayas_en_dos_lineas(hud):
    """Que no se dedupliquen pulsaciones LEGÍTIMAS: dos F3 seguidas son dos
    diálogos."""
    hud.editor.insert("1.0", "Texto.")
    hud.editor.mark_set("insert", "end-1c")
    hud.accion_nuevo_dialogo()
    hud.editor.insert("insert", "Primero.")
    hud.accion_nuevo_dialogo()
    assert hud._texto().count("\u2014") == 2


def test_la_orden_global_se_ejecuta_si_la_ventana_no_tiene_foco(hud):
    """Sin foco, el bind_all no dispara: la global es la única ruta y tiene
    que funcionar."""
    hud.raiz.withdraw()                   # ventana oculta = sin foco
    hud.raiz.update()
    assert not hud._ventana_tiene_foco()

    hud.encolar_orden_global("cambiar_plantilla")
    hud._atender_cola()
    assert hud.plantilla.clave == "narrativo"
    hud.raiz.deiconify()


def test_la_orden_global_se_descarta_si_la_ventana_tiene_foco(hud):
    hud.raiz.focus_force()
    hud.raiz.update()
    if not hud._ventana_tiene_foco():
        pytest.skip("El servidor gráfico no da el foco a la ventana")

    hud.encolar_orden_global("cambiar_plantilla")
    hud._atender_cola()
    assert hud.plantilla.clave == "novela"      # no se ha ejecutado


def test_la_orden_directa_se_ejecuta_siempre(hud):
    """Las órdenes directas (tests, prueba de humo) no se filtran."""
    hud.raiz.focus_force()
    hud.raiz.update()
    hud.encolar_orden("cambiar_plantilla")
    hud._atender_cola()
    assert hud.plantilla.clave == "narrativo"


def test_f1_con_foco_no_arranca_y_para_el_dictado(hud_con_dictado):
    """El mismo doble disparo hacía que F1 arrancara el dictado y lo parase
    50 ms después. Con el arreglo, una pulsación es un solo alternar."""
    from vozclip.atajos import construir_mapa

    hud = hud_con_dictado
    hud.raiz.focus_force()
    hud.raiz.update()
    if not hud._ventana_tiene_foco():
        pytest.skip("El servidor gráfico no da el foco a la ventana")

    llamadas = []
    original = hud.accion_dictar
    hud.accion_dictar = lambda: llamadas.append(1) or original()
    mapa = construir_mapa(config.DEFAULTS["atajos"], hud.encolar_orden_global,
                          set(hud.acciones()))

    # El bind_all captura el método en construcción; llamamos igual que él
    hud.acciones()["dictar"]()            # ruta local
    mapa["<f1>"]()                        # ruta global
    _procesar_cola(hud)

    assert len(llamadas) == 1


def test_teclado_y_raton_insertan_lo_mismo_una_vez(hud):
    """El detalle que confirmó el diagnóstico: con el ratón nunca salía
    doble, porque el botón solo tiene una ruta (el `command` de tkinter).
    La tecla tenía dos. Ahora las dos vías insertan exactamente una raya."""
    from vozclip.atajos import construir_mapa

    hud.raiz.focus_force()
    hud.raiz.update()
    if not hud._ventana_tiene_foco():
        pytest.skip("El servidor gráfico no da el foco a la ventana")

    mapa = construir_mapa(config.DEFAULTS["atajos"], hud.encolar_orden_global,
                          set(hud.acciones()))
    hud.editor.insert("1.0", "Texto.")
    hud.editor.mark_set("insert", "end-1c")

    hud.raiz.event_generate("<F3>")       # tecla: ruta local...
    mapa["<f3>"]()                        # ...y ruta global, misma pulsación
    _procesar_cola(hud)
    assert hud._texto().count("\u2014") == 1

    hud.editor.insert("insert", "Hola.")
    hud.botones[2].invoke()               # ratón: el botón "3. Nuevo diálogo"
    assert hud._texto().count("\u2014") == 2

    # Y ninguna de las dos deja restos: cada raya en su línea, con sangría
    lineas = [ln for ln in hud._texto().split("\n") if "\u2014" in ln]
    assert all(ln.startswith("  \u2014") for ln in lineas)


# ===========================================================================
# Corrección por voz (F9)
# ===========================================================================
@pytest.fixture
def hud_corrector():
    """HUD con dictado falso que 'dice' lo que se le ponga en `respuestas`."""
    from vozclip import dictado as moddictado
    from vozclip.hud import HUD
    from vozclip.voz import ServicioVoz

    crear_tk_o_saltar().destroy()
    voz = ServicioVoz(motor_forzado="falso")
    voz.arrancar()
    respuestas: list[str] = []

    def fabrica(notificar):
        return moddictado.ServicioDictado(
            notificar=notificar,
            ajustes={"activado": True, "modelo": "fingido"},
            fabrica_motor=lambda: moddictado.MotorDictadoFalso([respuestas.pop(0)]),
            fabrica_captura=lambda: moddictado.CapturaFalsa(),
            voz=voz,
        )

    try:
        ventana = HUD(voz, copy.deepcopy(config.DEFAULTS), fabrica_dictado=fabrica)
        ventana.raiz.update()
        ventana.respuestas = respuestas
        yield ventana
        try:
            ventana.detener_bucle()
            ventana.servicio_dictado.cerrar()
            ventana.raiz.destroy()
        except Exception:
            pass
    finally:
        voz.cerrar()
        _recoger_basura_tk()


def _escuchar(hud, limite=4.0):
    """Deja que el dictado falso hable y que el HUD lo procese."""
    import time as _t

    plazo = _t.monotonic() + limite
    while _t.monotonic() < plazo:
        hud._atender_dictado()
        hud.raiz.update()
        _t.sleep(0.02)
        if not hud.servicio_dictado.activo and hud.cola_dictado.empty():
            break
    hud.voz.esperar_silencio(limite=2)


def _dictar(hud, texto):
    hud.respuestas.append(texto)
    hud.accion_dictar()
    _escuchar(hud)


def _corregir(hud, dicho):
    hud.respuestas.append(dicho)
    hud.accion_corregir()
    _escuchar(hud)


def test_el_boton_de_corregir_existe_con_su_color(hud):
    assert len(hud.botones) == 11
    assert "Corregir" in hud.botones[5].cget("text")
    assert "F9" in hud.botones[5].cget("text")
    assert hud.botones[5].cget("bg") == hud.tema["corregir"]
    assert hud.tema["corregir"] not in (hud.tema["destacado"], hud.tema["archivo"])


def test_flujo_completo_dictar_y_corregir(hud_corrector):
    """El caso de todos los días: dicta, una palabra sale mal, la cambia."""
    hud = hud_corrector
    _dictar(hud, "aquella noche no dormí coma la casa estaba en silencio punto")
    assert "la casa estaba" in hud._texto()

    hud.voz._motor.dicho.clear()
    _corregir(hud, "cambia casa por cosa")

    assert "la cosa estaba en silencio." in hud._texto()
    assert "la casa" not in hud._texto()
    assert any("He cambiado casa por cosa" in t for t in hud.voz._motor.dicho)
    assert hud.correccion is None                    # modo cerrado


def test_f9_explica_que_decir(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "Texto escrito.")
    hud.voz._motor.dicho.clear()
    hud.respuestas.append("cancela")
    hud.accion_corregir()
    hud.voz.esperar_silencio(limite=2)
    assert any("cambia casa por cosa" in t for t in hud.voz._motor.dicho)
    assert "CORRIGIENDO" in hud.etiqueta_dictado.cget("text")
    _escuchar(hud)


def test_tras_dictar_se_recuerda_como_corregir(hud_corrector):
    hud = hud_corrector
    hud.voz._motor.dicho.clear()
    _dictar(hud, "una frase de más de cuatro palabras")
    assert any("Para corregir" in t for t in hud.voz._motor.dicho)


def test_el_recordatorio_se_puede_apagar(hud_corrector):
    hud = hud_corrector
    hud.ajustes["correccion"]["recordatorio"] = False
    hud.voz._motor.dicho.clear()
    _dictar(hud, "una frase de más de cuatro palabras")
    assert not any("Para corregir" in t for t in hud.voz._motor.dicho)


def test_cancelar_deja_el_texto_intacto(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "Texto que no debe cambiar.")
    hud.voz._motor.dicho.clear()
    _corregir(hud, "cancela")
    assert hud._texto() == "Texto que no debe cambiar."
    assert hud.correccion is None
    assert any("cancelada" in t for t in hud.voz._motor.dicho)


def test_escape_cancela(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "Texto.")
    hud.respuestas.append("cambia Texto por Otro")
    hud.accion_corregir()
    hud.accion_cancelar_correccion()        # antes de que llegue nada
    _escuchar(hud)
    assert hud.correccion is None
    assert hud._texto() == "Texto."


def test_escape_sin_correccion_activa_no_hace_nada(hud_corrector):
    hud = hud_corrector
    hud.voz._motor.dicho.clear()
    hud.accion_cancelar_correccion()
    assert hud.voz._motor.dicho == []


def test_leelo_enumera_y_luego_acepta_el_numero(hud_corrector):
    """El recurso para cuando la palabra mal reconocida es irreconocible."""
    hud = hud_corrector
    hud.editor.insert("1.0", "Aquella noche no dormí.")
    hud.editor.mark_set("insert", "end-1c")

    hud.voz._motor.dicho.clear()
    hud.respuestas.append("léelo")
    hud.respuestas.append("la dos por tarde")
    hud.accion_corregir()
    _escuchar(hud)               # procesa "léelo": enumera y vuelve a escuchar
    _escuchar(hud)               # procesa "la dos por tarde"

    assert any("1, Aquella. 2, noche." in t for t in hud.voz._motor.dicho)
    assert hud._texto() == "Aquella tarde no dormí."


def test_varias_apariciones_pregunta_y_resuelve(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "la casa grande y la casa pequeña")
    hud.editor.mark_set("insert", "end-1c")

    hud.voz._motor.dicho.clear()
    hud.respuestas.append("cambia casa por cosa")
    hud.respuestas.append("dos")
    hud.accion_corregir()
    _escuchar(hud)
    _escuchar(hud)

    assert any("aparece 2 veces" in t for t in hud.voz._motor.dicho)
    assert hud._texto() == "la casa grande y la cosa pequeña"
    assert hud.correccion is None


def test_palabra_no_encontrada_vuelve_a_escuchar(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "Aquella noche.")
    hud.editor.mark_set("insert", "end-1c")
    hud.voz._motor.dicho.clear()
    hud.respuestas.append("cambia bicicleta por moto")
    hud.respuestas.append("cancela")
    hud.accion_corregir()
    _escuchar(hud)
    _escuchar(hud)
    dicho = hud.voz._motor.dicho
    assert any("No encuentro bicicleta" in t for t in dicho)
    # Volvió a escuchar: se consumió la segunda respuesta, "cancela"
    assert hud.respuestas == []
    assert any("cancelada" in t for t in dicho)
    assert hud.correccion is None
    assert hud._texto() == "Aquella noche."         # nada tocado


def test_lo_nuevo_pasa_por_la_puntuacion_hablada(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "Hola mundo")
    hud.editor.mark_set("insert", "end-1c")
    _corregir(hud, "cambia mundo por amigo coma")
    assert hud._texto() == "Hola amigo,"


def test_corregir_respeta_la_sangria_del_parrafo(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "     Aquella noche no dormí.\n\n  —No me lo creo.")
    hud.editor.mark_set("insert", "1.10")
    _corregir(hud, "cambia noche por tarde")
    assert hud._texto() == "     Aquella tarde no dormí.\n\n  —No me lo creo."


def test_corregir_actua_sobre_el_parrafo_del_cursor(hud_corrector):
    """'casa' está en los dos párrafos; solo se toca el del cursor."""
    hud = hud_corrector
    hud.editor.insert("1.0", "la casa uno.\n\nla casa dos.")
    hud.editor.mark_set("insert", "3.3")
    _corregir(hud, "cambia casa por cosa")
    assert hud._texto() == "la casa uno.\n\nla cosa dos."


def test_deshacer_por_voz(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "Aquella noche.")
    hud.editor.mark_set("insert", "end-1c")
    _corregir(hud, "cambia noche por tarde")
    assert "tarde" in hud._texto()
    _corregir(hud, "deshacer")
    assert hud._texto() == "Aquella noche."


def test_corregir_sin_texto_avisa(hud_corrector):
    hud = hud_corrector
    hud.voz._motor.dicho.clear()
    hud.accion_corregir()
    assert "No hay nada escrito" in _dicho(hud)
    assert hud.correccion is None


def test_corregir_en_modo_externo(hud_corrector, monkeypatch):
    """En Word: se captura la línea, se corrige y se vuelve a escribir."""
    hud = hud_corrector
    escrito = {}
    monkeypatch.setattr("vozclip.puente.capturar_linea_actual",
                        lambda: "La casa estaba en silencio.")
    monkeypatch.setattr("vozclip.puente.reemplazar_linea_actual",
                        lambda t: escrito.setdefault("texto", t))
    hud.modo = "externo"
    _corregir(hud, "cambia casa por cosa")
    assert escrito["texto"] == "La cosa estaba en silencio."
    assert hud.correccion is None


def test_f1_y_f9_no_se_pisan(hud_corrector):
    """Con F9 activo, el texto dictado va a la corrección, no al editor."""
    hud = hud_corrector
    hud.editor.insert("1.0", "Aquella noche.")
    hud.editor.mark_set("insert", "end-1c")
    _corregir(hud, "cambia noche por tarde")
    assert hud._texto() == "Aquella tarde."         # corregido, no añadido
    _dictar(hud, "y punto")
    assert hud._texto() == "Aquella tarde. Y."       # el dictado normal sigue igual


def test_corregir_esta_en_la_ayuda(hud):
    hud.accion_ayuda()
    dicho = _dicho(hud)
    assert "Efe nueve" in dicho
    assert "cambia casa por cosa" in dicho


# ===========================================================================
# F9 en modo numerado: numerar -> elegir -> dictar la nueva -> sustituir
# ===========================================================================
def test_modo_numerado_flujo_completo(hud_corrector):
    """El flujo pedido: F9 numera, se dice el número, se lee la palabra
    elegida, se dicta la nueva y se sustituye solo esa."""
    hud = hud_corrector
    hud.ajustes["correccion"]["modo"] = "numerado"
    hud.editor.insert("1.0", "Aquella noche no dormí.")
    hud.editor.mark_set("insert", "end-1c")

    hud.voz._motor.dicho.clear()
    hud.respuestas.append("dos")           # ¿cuál? -> la dos
    hud.respuestas.append("tarde")         # la palabra correcta
    hud.accion_corregir()
    _escuchar(hud)                          # procesa "dos"
    _escuchar(hud)                          # procesa "tarde"

    dicho = " ".join(hud.voz._motor.dicho)
    assert "1, Aquella. 2, noche." in dicho          # se numeró
    assert "¿Cuál cambio?" in dicho
    assert "noche. Dime la palabra correcta" in dicho  # se leyó la elegida
    assert "He cambiado noche por tarde" in dicho
    assert hud._texto() == "Aquella tarde no dormí."
    assert hud.correccion is None


def test_modo_numerado_con_rango(hud_corrector):
    hud = hud_corrector
    hud.ajustes["correccion"]["modo"] = "numerado"
    hud.editor.insert("1.0", "Aquella noche no dormí.")
    hud.editor.mark_set("insert", "end-1c")
    hud.respuestas.append("del tres al cuatro")
    hud.respuestas.append("me desvelé")
    hud.accion_corregir()
    _escuchar(hud)
    _escuchar(hud)
    assert hud._texto() == "Aquella noche me desvelé."


def test_modo_numerado_borrar(hud_corrector):
    hud = hud_corrector
    hud.ajustes["correccion"]["modo"] = "numerado"
    hud.editor.insert("1.0", "Aquella noche no dormí.")
    hud.editor.mark_set("insert", "end-1c")
    hud.respuestas.append("tres")
    hud.respuestas.append("borrar")
    hud.accion_corregir()
    _escuchar(hud)
    _escuchar(hud)
    assert hud._texto() == "Aquella noche dormí."


def test_modo_numerado_sin_numero_insiste(hud_corrector):
    hud = hud_corrector
    hud.ajustes["correccion"]["modo"] = "numerado"
    hud.editor.insert("1.0", "Aquella noche.")
    hud.editor.mark_set("insert", "end-1c")
    hud.voz._motor.dicho.clear()
    hud.respuestas.append("no sé")
    hud.respuestas.append("cancela")
    hud.accion_corregir()
    _escuchar(hud)
    _escuchar(hud)
    assert any("No he oído un número" in t for t in hud.voz._motor.dicho)
    assert hud._texto() == "Aquella noche."


def test_modo_numerado_acepta_la_orden_entera_de_una_vez(hud_corrector):
    """Si en vez del número dice 'la dos por tarde', también vale."""
    hud = hud_corrector
    hud.ajustes["correccion"]["modo"] = "numerado"
    hud.editor.insert("1.0", "Aquella noche.")
    hud.editor.mark_set("insert", "end-1c")
    hud.respuestas.append("la dos por tarde")
    hud.accion_corregir()
    _escuchar(hud)
    assert hud._texto() == "Aquella tarde."


def test_modo_directo_pasa_al_guiado_con_leelo(hud_corrector):
    """Desde el directo, 'léelo' entra en el mismo flujo guiado."""
    hud = hud_corrector
    hud.editor.insert("1.0", "Aquella noche.")
    hud.editor.mark_set("insert", "end-1c")
    hud.voz._motor.dicho.clear()
    hud.respuestas.append("léelo")
    hud.respuestas.append("dos")
    hud.respuestas.append("tarde")
    hud.accion_corregir()
    _escuchar(hud)
    _escuchar(hud)
    _escuchar(hud)
    assert "¿Cuál cambio?" in " ".join(hud.voz._motor.dicho)
    assert hud._texto() == "Aquella tarde."


def test_f9_por_el_atajo_global_activa_la_correccion(hud_corrector):
    """Con la ventana sin foco, F9 llega por pynput y tiene que funcionar."""
    from vozclip.atajos import construir_mapa

    hud = hud_corrector
    hud.editor.insert("1.0", "Aquella noche.")
    hud.editor.mark_set("insert", "end-1c")
    hud.raiz.withdraw()
    hud.raiz.update()
    assert not hud._ventana_tiene_foco()

    mapa = construir_mapa(config.DEFAULTS["atajos"], hud.encolar_orden_global,
                          set(hud.acciones()))
    assert "<f9>" in mapa
    hud.voz._motor.dicho.clear()
    hud.respuestas.append("cambia noche por tarde")
    mapa["<f9>"]()                                # pynput encola la orden global
    hud._atender_cola()                           # el hilo principal la ejecuta
    _escuchar(hud)

    # Se activó por la ruta global (se oyó la invitación) y corrigió
    assert any("Dime el cambio" in t for t in hud.voz._motor.dicho)
    assert hud._texto() == "Aquella tarde."
    assert hud.correccion is None                 # y se cerró al terminar
    hud.raiz.deiconify()


def test_f9_con_foco_no_se_activa_dos_veces(hud_corrector):
    """El mismo doble disparo de F3: local + global. Con F9, dos disparos
    serían 'empezar' y luego 'parar' al instante."""
    from vozclip.atajos import construir_mapa

    hud = hud_corrector
    hud.raiz.focus_force()
    hud.raiz.update()
    if not hud._ventana_tiene_foco():
        pytest.skip("El servidor gráfico no da el foco a la ventana")

    hud.editor.insert("1.0", "Aquella noche.")
    hud.editor.mark_set("insert", "end-1c")
    llamadas = []
    original = hud.accion_corregir
    hud.accion_corregir = lambda: (llamadas.append(1), original())[1]
    mapa = construir_mapa(config.DEFAULTS["atajos"], hud.encolar_orden_global,
                          set(hud.acciones()))
    hud.respuestas.append("cancela")
    hud.acciones()["corregir"]()          # ruta local
    mapa["<f9>"]()                        # ruta global, misma pulsación
    _procesar_cola(hud)
    assert len(llamadas) == 1
    _escuchar(hud)


# ===========================================================================
# La versión se oye
# ===========================================================================
def test_el_saludo_dice_la_version(hud):
    """Sin ver la pantalla, es la única forma de saber si un arreglo ha
    llegado a este ordenador o se ejecuta una versión antigua."""
    from vozclip import __version__
    from vozclip.hud import version_hablada

    hud.saludar()
    assert version_hablada(__version__) in _dicho(hud)


def test_donde_estoy_dice_la_version(hud):
    from vozclip.hud import version_hablada

    hud.accion_donde_estoy()
    assert version_hablada() in _dicho(hud)


def test_el_titulo_lleva_la_version(hud):
    from vozclip import __version__

    assert __version__ in hud.raiz.title()


def test_version_hablada():
    from vozclip.hud import version_hablada

    assert version_hablada("2.10.0") == "2 punto 10"
    assert version_hablada("2.10.1") == "2 punto 10 punto 1"


# ===========================================================================
# Corregir con F1, en mitad del dictado (lo que hizo Julián)
# ===========================================================================
def test_f1_con_cambia_corrige_en_vez_de_escribir(hud_corrector):
    """La captura real: dictó, oyó 'alpiste' mal, y volvió a pulsar F1 para
    arreglarlo. Con el verbo delante, se aplica como corrección."""
    hud = hud_corrector
    _dictar(hud, "come alpiste mientras está bailando con un cisne")
    assert "Come alpiste" in hud._texto()

    hud.voz._motor.dicho.clear()
    _dictar(hud, "cambia alpiste por rueda")

    assert hud._texto() == "Come rueda mientras está bailando con un cisne"
    assert "cambia" not in hud._texto()                # no se escribió la orden
    assert any("He cambiado alpiste por rueda" in t for t in hud.voz._motor.dicho)


def test_f1_sin_verbo_escribe_tal_cual(hud_corrector):
    """'alpiste por rueda' a secas es texto: 'fue por pan' también lo sería."""
    hud = hud_corrector
    _dictar(hud, "come alpiste mientras baila")
    _dictar(hud, "alpiste por rueda")
    assert hud._texto().endswith("alpiste por rueda")


def test_f1_con_cambia_pero_sin_la_palabra_es_prosa(hud_corrector):
    """'Cambia de opinión y se va' empieza por cambia, pero es una frase."""
    hud = hud_corrector
    _dictar(hud, "ella duda un momento punto")
    _dictar(hud, "cambia de opinión y se va")
    assert "Cambia de opinión y se va" in hud._texto()


def test_f1_con_borra_quita_la_palabra(hud_corrector):
    hud = hud_corrector
    _dictar(hud, "come alpiste mientras baila")
    _dictar(hud, "borra mientras")
    assert hud._texto() == "Come alpiste baila"


def test_f1_corrige_por_numero(hud_corrector):
    hud = hud_corrector
    _dictar(hud, "come alpiste mientras baila")
    _dictar(hud, "sustituye la dos por rueda")
    assert hud._texto() == "Come rueda mientras baila"


def test_f1_con_varias_apariciones_pregunta(hud_corrector):
    """Si la palabra está dos veces, pasa al flujo de elegir, como F9."""
    hud = hud_corrector
    _dictar(hud, "la casa grande y la casa pequeña")
    hud.voz._motor.dicho.clear()
    # Las respuestas se consumen en orden: primero la orden, luego "dos"
    hud.respuestas.append("cambia casa por cosa")
    hud.respuestas.append("dos")
    hud.accion_dictar()
    _escuchar(hud)          # procesa la orden: pregunta y vuelve a escuchar
    _escuchar(hud)          # procesa "dos"
    assert any("aparece 2 veces" in t for t in hud.voz._motor.dicho)
    assert hud._texto() == "La casa grande y la cosa pequeña"


def test_f1_correccion_conserva_la_sangria(hud_corrector):
    hud = hud_corrector
    hud.editor.insert("1.0", "     Aquella noche no dormí.")
    hud.editor.mark_set("insert", "end-1c")
    _dictar(hud, "cambia noche por tarde")
    assert hud._texto() == "     Aquella tarde no dormí."


def test_el_recordatorio_ensena_la_frase(hud_corrector):
    """Que aprenda la frase, no una tecla más."""
    hud = hud_corrector
    hud.voz._motor.dicho.clear()
    _dictar(hud, "una frase de más de cuatro palabras")
    assert any("cambia, la palabra, por, la buena" in t for t in hud.voz._motor.dicho)


def test_perfil_julian_tiene_atajo(hud):
    assert "perfil_julian" in config.DEFAULTS["atajos"]
    assert "perfil_julian" in hud.acciones()


# ===========================================================================
# El ciclo real: micrófono que no termina solo, dos rutas por tecla
# ===========================================================================
class _CapturaComoElMicrofono:
    """Bloquea hasta que se ordena parar, como el micrófono de verdad.
    `CapturaFalsa` termina sola y por eso nunca se había probado el
    'pulsar otra vez para parar'."""
    desbordamientos = 0

    def trozos(self, parar):
        import time as _t

        while not parar.is_set():
            _t.sleep(0.1)
            yield b"\x10\x00" * 4000

    def cerrar(self):
        pass


class _MotorConParciales:
    def __init__(self, frase):
        self.frase = frase
        self.n = 0

    def iniciar(self):
        self.n = 0

    def alimentar(self, _trozo):
        self.n += 1
        palabras = self.frase.split()
        return " ".join(palabras[: self.n]) if self.n <= len(palabras) else self.frase

    def finalizar(self):
        return self.frase

    def cerrar(self):
        pass


@pytest.fixture
def hud_real():
    """HUD con un micrófono que no se calla solo, y con las DOS rutas de
    cada tecla activas y el filtro por foco anulado: el peor caso."""
    from vozclip import dictado as moddictado
    from vozclip.atajos import construir_mapa
    from vozclip.hud import HUD
    from vozclip.voz import ServicioVoz

    crear_tk_o_saltar().destroy()
    voz = ServicioVoz(motor_forzado="falso")
    voz.arrancar()
    frases: list[str] = []

    def fabrica(notificar):
        return moddictado.ServicioDictado(
            notificar=notificar, ajustes={"activado": True, "modelo": "fingido"},
            fabrica_motor=lambda: _MotorConParciales(frases.pop(0)),
            fabrica_captura=lambda: _CapturaComoElMicrofono(), voz=voz,
        )

    try:
        hud = HUD(voz, copy.deepcopy(config.DEFAULTS), fabrica_dictado=fabrica)
        hud.raiz.update()
        hud.frases = frases
        hud._ventana_tiene_foco = lambda: False
        mapa = construir_mapa(config.DEFAULTS["atajos"], hud.encolar_orden_global,
                              set(hud.acciones()))

        def tecla(nombre):
            hud._envolver_evento(hud.acciones()[nombre])()          # tkinter
            mapa[config.DEFAULTS["atajos"][nombre]]()               # pynput

        hud.tecla = tecla
        yield hud
        try:
            hud.detener_bucle()
            hud.servicio_dictado.cerrar()
            hud.raiz.destroy()
        except Exception:
            pass
    finally:
        voz.cerrar()
        _recoger_basura_tk()


def _bombear(hud, segundos):
    import time as _t

    fin = _t.monotonic() + segundos
    while _t.monotonic() < fin:
        hud.raiz.update()
        _t.sleep(0.02)


def test_f1_para_al_pulsar_otra_vez_aunque_llegue_por_las_dos_rutas(hud_real):
    """El bug de Windows: la orden global se procesaba tras el evento
    'fin' y volvía a arrancar la escucha. Se quedaba escuchando."""
    hud = hud_real
    hud.frases.append("seis del nueve comeremos espagueti")
    hud.tecla("dictar")
    _bombear(hud, 1.2)
    assert hud.dictando

    hud.tecla("dictar")
    _bombear(hud, 1.2)
    assert not hud.dictando
    assert not hud.servicio_dictado.activo
    assert hud._texto() == "Seis del nueve comeremos espagueti"


def test_se_puede_seguir_dictando_en_un_segundo_ciclo(hud_real):
    """'Necesitaría seguir con el texto después.'"""
    hud = hud_real
    hud.frases.append("primera frase")
    hud.tecla("dictar")
    _bombear(hud, 1.0)
    hud.tecla("dictar")
    _bombear(hud, 1.2)

    hud.frases.append("y segunda frase")
    hud.tecla("dictar")
    _bombear(hud, 1.0)
    assert hud.dictando                              # sí arranca el segundo
    hud.tecla("dictar")
    _bombear(hud, 1.2)
    assert not hud.dictando                          # y sí para
    assert hud._texto() == "Primera frase y segunda frase"


def test_f9_se_aplica_solo_al_callar(hud_real):
    """'Veo que detecta el texto: que instantáneamente se cambie.'"""
    hud = hud_real
    hud.editor.insert("1.0", "Seis del nueve del dos mil veintiséis comeremos espagueti")
    hud.editor.mark_set("insert", "end-1c")
    hud.ajustes["correccion"]["parar_tras_silencio"] = 0.6
    hud.frases.append("corrige veintiséis por treinta y seis")

    hud.tecla("corregir")
    _bombear(hud, 0.5)
    assert "CORRIGIENDO" in hud.etiqueta_dictado.cget("text")
    _bombear(hud, 3.0)                              # sin segundo F9

    assert hud._texto() == "Seis del nueve del dos mil treinta y seis comeremos espagueti"
    assert hud.correccion is None
    assert not hud.dictando
    assert any("He cambiado veintiséis por treinta y seis" in t for t in hud.voz._motor.dicho)


def test_f9_tambien_se_aplica_con_la_segunda_pulsacion(hud_real):
    """'Si le vuelvo a dar al F9, actúa y cámbialo.'"""
    hud = hud_real
    hud.editor.insert("1.0", "Aquella noche no dormí.")
    hud.editor.mark_set("insert", "end-1c")
    hud.ajustes["correccion"]["parar_tras_silencio"] = 0      # manual
    hud.frases.append("cambia noche por tarde")

    hud.tecla("corregir")

    _bombear(hud, 1.0)
    assert hud.dictando and hud.correccion is not None
    hud.tecla("corregir")
    _bombear(hud, 1.2)                 # las dos rutas otra vez
    assert hud._texto() == "Aquella tarde no dormí."
    assert hud.correccion is None
    assert not hud.dictando


def test_la_etiqueta_dice_corrigiendo_durante_la_orden(hud_real):
    hud = hud_real
    hud.editor.insert("1.0", "Texto.")
    hud.editor.mark_set("insert", "end-1c")
    hud.ajustes["correccion"]["parar_tras_silencio"] = 0
    hud.frases.append("cambia texto por otro")
    hud.tecla("corregir")
    _bombear(hud, 0.8)
    assert hud.etiqueta_dictado.cget("text").startswith("● CORRIGIENDO")
    hud.tecla("corregir")
    _bombear(hud, 1.0)


def test_el_guard_descarta_la_repeticion_inmediata(hud):
    llamadas = []
    f = lambda: llamadas.append(1)  # noqa: E731
    assert hud._disparar("x", f) is True
    assert hud._disparar("x", f) is False          # 50 ms después: repetición
    assert llamadas == [1]


def test_el_guard_deja_pasar_pulsaciones_distintas(hud):
    import time as _t

    llamadas = []
    f = lambda: llamadas.append(1)  # noqa: E731
    hud._disparar("x", f)
    _t.sleep(hud.VENTANA_REPETICION + 0.05)
    hud._disparar("x", f)
    assert llamadas == [1, 1]


def test_el_guard_no_confunde_acciones_distintas(hud):
    llamadas = []
    assert hud._disparar("a", lambda: llamadas.append("a"))
    assert hud._disparar("b", lambda: llamadas.append("b"))
    assert llamadas == ["a", "b"]


def test_detener_desde_la_ventana_no_bloquea(hud_real):
    """El join en el hilo principal congelaba la ventana y retrasaba la
    cola de órdenes: era parte del doble disparo."""
    import time as _t

    hud = hud_real
    hud.frases.append("frase")
    hud.tecla("dictar")
    _bombear(hud, 0.8)
    t0 = _t.monotonic()
    hud.accion_dictar()                 # parar
    assert _t.monotonic() - t0 < 0.1    # vuelve al instante
    _bombear(hud, 1.2)
