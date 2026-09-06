"""Punto de entrada de VozClip Escritor.

Modos:
    vozclip                     abre el HUD (lo normal)
    vozclip guion.txt           abre el HUD con ese archivo cargado
    vozclip --leer "hola"       lee un texto y sale
    vozclip --diagnostico       comprueba el entorno y dice qué falla
    vozclip --voces             enumera las voces instaladas
    vozclip --config            dice dónde está el archivo de ajustes

=============================================================================
DIAGNÓSTICO EN VOZ ALTA
=============================================================================
La versión anterior fallaba en silencio: abría una consola y ahí se quedaba.
Ahora, si algo va mal en el arranque, se dice por consola Y por voz cuando
es posible, y el programa devuelve un código de salida distinto de cero.
Un usuario ciego no puede leer un traceback: tiene que oírlo.
=============================================================================
"""

from __future__ import annotations

import argparse
import platform
import sys
from datetime import datetime
from pathlib import Path

from . import __version__
from . import config as cfg
from .atajos import EscuchadorAtajos, construir_mapa
from .voz import ServicioVoz


# ---------------------------------------------------------------------------
# Registro de arranque
# ---------------------------------------------------------------------------
# Cuando el .exe se compila sin consola (que es lo correcto para no molestar
# con una ventana negra), los print() no van a ninguna parte. Por eso todo lo
# importante se escribe también en un archivo de registro que se puede mirar
# después. Es la diferencia entre "no hace nada" y "sé exactamente qué falló".
def _ruta_registro() -> Path:
    return cfg.carpeta_config() / "ultimo_arranque.log"


def _log(mensaje: str, error: bool = False) -> None:
    marca = datetime.now().strftime("%H:%M:%S")
    linea = f"[{marca}] {mensaje}"
    print(linea, file=sys.stderr if error else sys.stdout)
    try:
        ruta = _ruta_registro()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "a", encoding="utf-8") as f:
            f.write(linea + "\n")
    except OSError:
        pass


def _iniciar_registro() -> None:
    try:
        ruta = _ruta_registro()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        cabecera = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ruta.write_text(
            f"VozClip · arranque {cabecera}\n"
            f"Python {sys.version.split()[0]} en {platform.system()}\n"
            f"{'-' * 50}\n",
            encoding="utf-8",
        )
    except OSError:
        pass


# ---------------------------------------------------------------------------
# Supervivencia en un .exe compilado con --windowed
# ---------------------------------------------------------------------------
# Cuando PyInstaller compila sin consola, `sys.stdout` y `sys.stderr` valen
# None. CPython no revienta por eso (print() simplemente no hace nada), pero
# TODO rastro se pierde: si algo falla, el usuario ve un doble clic que no
# produce ninguna ventana y nada más. Aquí redirigimos ambos flujos al
# archivo de registro y ponemos un manejador global de excepciones que además
# lo dice en voz alta.
def _forzar_utf8() -> None:
    """Hace que la consola de Windows entienda los acentos.

    Por defecto, una consola de Windows usa cp1252 o cp437, pero Python
    escribe UTF-8. El resultado es que "están" sale como "estÃ¡n", y
    cualquier script que busque una palabra con acento en esa salida no la
    encuentra. Eso es exactamente lo que hacía fallar la comprobación del
    ejecutable en la CI: el autotest pasaba, pero el paso siguiente no
    reconocía su propia salida.
    """
    if platform.system() == "Windows":
        try:
            import ctypes

            # 65001 = UTF-8. Afecta solo a la consola de este proceso.
            ctypes.windll.kernel32.SetConsoleOutputCP(65001)
        except Exception:
            pass

    for flujo in (sys.stdout, sys.stderr):
        try:
            if flujo is not None and hasattr(flujo, "reconfigure"):
                flujo.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def _preparar_salida() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return  # hay consola: no tocamos nada

    try:
        ruta = _ruta_registro()
        ruta.parent.mkdir(parents=True, exist_ok=True)
        destino = open(ruta, "a", encoding="utf-8", buffering=1)
    except OSError:
        return

    if sys.stdout is None:
        sys.stdout = destino
    if sys.stderr is None:
        sys.stderr = destino


def _instalar_manejador_de_errores(voz=None) -> None:
    """Un error no capturado en modo ventana es invisible. Aquí no."""

    def manejador(tipo, valor, traza) -> None:
        import traceback

        detalle = "".join(traceback.format_exception(tipo, valor, traza))
        _log(f"ERROR NO CAPTURADO:\n{detalle}", error=True)

        if voz is not None:
            try:
                voz.hablar(
                    f"Ha ocurrido un error inesperado: {tipo.__name__}. "
                    "Está anotado en el archivo de registro."
                )
                voz.esperar_silencio(limite=8)
            except Exception:
                pass

        # Aviso visible, por si quien mira es una persona vidente ayudando
        try:
            import tkinter.messagebox as mb

            mb.showerror(
                "VozClip",
                f"Error inesperado: {tipo.__name__}\n\n"
                f"Detalles en:\n{_ruta_registro()}",
            )
        except Exception:
            pass

    sys.excepthook = manejador


def construir_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="vozclip",
        description="Editor de guiones parlante para escritores sin visión.",
    )
    p.add_argument("archivo", nargs="?", help="Archivo de guion que abrir.")
    p.add_argument("--version", action="version", version=f"VozClip {__version__}")
    p.add_argument("--leer", metavar="TEXTO", help="Lee el texto indicado y sale.")
    p.add_argument("--voces", action="store_true", help="Enumera las voces instaladas.")
    p.add_argument("--config", action="store_true", help="Muestra la ruta de ajustes.")
    p.add_argument(
        "--diagnostico",
        action="store_true",
        help="Comprueba que todo está instalado y funcionando.",
    )
    p.add_argument(
        "--autotest",
        action="store_true",
        help="Verifica este binario de principio a fin y sale (para CI).",
    )
    p.add_argument(
        "--instalar-modelo-dictado",
        action="store_true",
        help="Descarga el modelo de voz en español para poder dictar (39 MB).",
    )
    p.add_argument(
        "--motor",
        choices=["sapi5", "comando", "falso"],
        help="Fuerza un motor de voz concreto.",
    )
    p.add_argument(
        "--sin-atajos-globales",
        action="store_true",
        help="No registra atajos globales (útil si otra app los bloquea).",
    )
    p.add_argument("--silencio", action="store_true", help="No dice el saludo inicial.")
    return p


# ---------------------------------------------------------------------------
# Diagnóstico
# ---------------------------------------------------------------------------
def diagnostico() -> int:
    """Comprueba una a una las piezas y explica qué falta.

    Este comando es la respuesta directa al problema de 'se abre el cmd y no
    hace nada': ahora se puede saber exactamente qué pieza falta.
    """
    print(f"VozClip {__version__} · diagnóstico")
    print("=" * 50)
    print(f"Sistema      : {platform.system()} {platform.release()}")
    print(f"Python       : {sys.version.split()[0]}")
    print(f"Ejecutable   : {sys.executable}")
    print("-" * 50)

    fallos = 0

    def comprobar(nombre: str, modulo: str, pista: str) -> None:
        nonlocal fallos
        try:
            __import__(modulo)
            print(f"[ OK ] {nombre}")
        except Exception as e:
            fallos += 1
            print(f"[FALLA] {nombre}: {e}")
            print(f"        Solución: {pista}")

    comprobar("tkinter (ventana)", "tkinter", "instala Python desde python.org con la opción tcl/tk")
    comprobar("pyperclip (portapapeles)", "pyperclip", "pip install pyperclip")
    comprobar("pynput (atajos globales)", "pynput", "pip install pynput")

    if platform.system() == "Windows":
        comprobar("pywin32 (voces SAPI5)", "win32com.client", "pip install pywin32")
        comprobar("pythoncom (hilos COM)", "pythoncom", "pip install pywin32")

    # --- Dictado por voz ---------------------------------------------
    print("-" * 50)
    print("Dictado por voz:")
    comprobar("vosk (reconocimiento)", "vosk", "pip install vosk")
    comprobar("sounddevice (micrófono)", "sounddevice", "pip install sounddevice")

    try:
        from .dictado import carpetas_de_modelos, localizar_modelo

        modelo = localizar_modelo()
        if modelo:
            print(f"[ OK ] Modelo de voz: {modelo}")
            from .dictado import es_ascii, ruta_segura_para_vosk

            if not es_ascii(str(modelo)):
                usable, explicacion = ruta_segura_para_vosk(modelo)
                print("[AVISO] La ruta del modelo tiene tildes o eñes. La librería")
                print("        de reconocimiento no puede abrirla tal cual.")
                print(f"        Remedio: {explicacion}")
                if not es_ascii(str(usable)):
                    print("[FALLA] No se ha encontrado una ruta sin acentos.")
                    print("        Solución: ejecuta instalar_modelos.bat, que lo")
                    print("        deja en C:\\Users\\Public\\VozClip\\modelos")
                    fallos += 1
        else:
            print("[FALLA] No hay modelo de voz en español.")
            print("        Se ha buscado en:")
            for candidata in carpetas_de_modelos():
                existe = "existe" if candidata.exists() else "no existe"
                print(f"          · {candidata}  ({existe})")
            print("        Solución: doble clic en instalar_modelos.bat,")
            print("        o ejecuta este programa con --instalar-modelo-dictado")
            fallos += 1
    except Exception as e:
        print(f"[FALLA] No se ha podido comprobar el modelo: {e}")
        fallos += 1

    try:
        import sounddevice as _sd

        entradas = [d for d in _sd.query_devices() if d.get("max_input_channels", 0)]
        if entradas:
            print(f"[ OK ] {len(entradas)} micrófono(s) detectado(s):")
            for d in entradas[:3]:
                print(f"        · {d['name']}")
        else:
            print("[AVISO] No hay ningún micrófono conectado.")
    except Exception as e:
        print(f"[AVISO] No se ha podido consultar el micrófono: {e}")

    print("-" * 50)

    # La prueba de verdad: arrancar el servicio de voz.
    try:
        servicio = ServicioVoz()
        servicio.arrancar()
        voces = servicio.voces()
        print(f"[ OK ] Motor de voz arrancado. {len(voces)} voces:")
        for v in voces:
            print(f"        · {v}")
        from .hud import version_hablada

        servicio.hablar(
            f"VozClip {version_hablada()}. El diagnóstico ha terminado. "
            "Si oyes esto, la voz funciona."
        )
        servicio.esperar_silencio(limite=15)
        servicio.cerrar()
        print("[ OK ] Se ha emitido una frase de prueba. ¿La has oído?")
    except Exception as e:
        fallos += 1
        print(f"[FALLA] Motor de voz: {e}")
        if platform.system() == "Windows":
            print("        Solución: pip install pywin32 y reinicia la consola.")
        else:
            print("        Solución: sudo apt install espeak-ng")

    print("=" * 50)
    if fallos:
        print(f"{fallos} problema(s). Corrígelos y vuelve a ejecutar --diagnostico.")
    else:
        print("Todo correcto. Ejecuta 'vozclip' para abrir el programa.")
    return 1 if fallos else 0


# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# Instalación del modelo de dictado
# ---------------------------------------------------------------------------
def instalar_modelo() -> int:
    """Descarga el modelo de voz, avisando por voz del progreso.

    Una descarga de 39 MB sin poder ver una barra de progreso es
    desconcertante, así que se va diciendo el porcentaje en voz alta.
    """
    from . import modelo as modmodelo

    voz = None
    try:
        voz = ServicioVoz()
        voz.arrancar()
    except Exception:
        voz = None   # sin voz también se puede instalar; se ve por consola

    def avisar(mensaje: str) -> None:
        print(mensaje)
        if voz is not None:
            voz.hablar(mensaje)
            voz.esperar_silencio(limite=20)

    try:
        destino = modmodelo.instalar(progreso=avisar)
        print(f"Modelo instalado en: {destino}")
        codigo = 0
    except Exception as e:
        avisar(f"No se ha podido instalar el modelo. {e}")
        codigo = 1

    if voz is not None:
        voz.esperar_silencio(limite=20)
        voz.cerrar()
    return codigo


# ---------------------------------------------------------------------------
# Autotest: verifica el EJECUTABLE, no el código fuente
# ---------------------------------------------------------------------------
def autotest() -> int:
    """Comprueba que este binario funciona de verdad.

    Se ejecuta sobre el .exe ya compilado, que es donde aparecen los
    problemas que los tests del código fuente no ven: que PyInstaller no haya
    empaquetado Tcl/Tk, que falte un import perezoso, que el bundle no
    encuentre pywin32...

    Usa el motor de voz falso, así que no necesita tarjeta de sonido: puede
    correr en un runner de CI. La comprobación de SAPI5 se hace aparte y solo
    avisa, porque en un servidor sin audio puede fallar sin que eso signifique
    que el ejecutable esté mal.
    """
    fallos = 0
    marcas: dict[str, str] = {}

    def comprobar(
        descripcion: str,
        condicion: bool,
        critico: bool = True,
        clave: str | None = None,
    ) -> None:
        """Escribe el resultado para una persona y, si se le da `clave`,
        también una marca en ASCII para que lo lea un script.

        Las marcas existen porque la salida bonita lleva acentos, y una
        consola de Windows con la página de códigos equivocada los
        destroza: buscar "están empaquetados" en esa salida no encuentra
        nada aunque la comprobación haya ido bien.
        """
        nonlocal fallos
        if condicion:
            print(f"  [ OK ] {descripcion}")
            estado = "OK"
        elif critico:
            fallos += 1
            print(f"  [FALLA] {descripcion}")
            estado = "FALLO"
        else:
            print(f"  [AVISO] {descripcion}")
            estado = "AVISO"

        if clave:
            marcas[clave] = estado

    congelado = getattr(sys, "frozen", False)
    print(f"VozClip {__version__} · autotest")
    print("=" * 60)
    print(f"Modo: {'ejecutable compilado' if congelado else 'código fuente'}")
    print(f"Sistema: {platform.system()} {platform.release()}")
    print("-" * 60)

    # 1. Tcl/Tk empaquetado -------------------------------------------------
    print("\n1. Interfaz gráfica")
    try:
        import tkinter as tk

        prueba = tk.Tk()
        prueba.withdraw()
        version = prueba.tk.call("info", "patchlevel")
        prueba.destroy()
        comprobar(f"tkinter abre ventana (Tcl/Tk {version})", True, clave="TKINTER")
    except Exception as e:
        comprobar(f"tkinter NO abre ventana: {e}", False, clave="TKINTER")
        print("\nSin Tcl/Tk no hay programa. Aborto.")
        return 1

    # 2. Servicio de voz ----------------------------------------------------
    print("\n2. Motor de voz")
    try:
        voz = ServicioVoz(motor_forzado="falso")
        voz.arrancar()
        comprobar("el servicio de voz arranca en su hilo", voz._hilo.is_alive(),
                  clave="VOZ")
    except Exception as e:
        comprobar(f"el servicio de voz NO arranca: {e}", False)
        return 1

    # SAPI5 de verdad: informativo. Sin audio puede fallar legítimamente.
    if platform.system() == "Windows":
        try:
            real = ServicioVoz(motor_forzado="sapi5")
            real.arrancar()
            comprobar(f"SAPI5 disponible con {len(real.voces())} voces", True,
                      clave="SAPI5")
            real.cerrar()
        except Exception as e:
            comprobar(f"SAPI5 no disponible aquí ({e})", False, critico=False)

    # 3. El HUD se construye entero -----------------------------------------
    print("\n3. HUD")
    import copy

    try:
        from .hud import HUD

        ajustes = copy.deepcopy(cfg.DEFAULTS)
        ventana = HUD(voz, ajustes)
        ventana.raiz.update()
        comprobar("la ventana se construye", bool(ventana.raiz.winfo_exists()),
                  clave="HUD")
        comprobar("hay 11 botones grandes", len(ventana.botones) == 11,
                  clave="BOTONES")
        comprobar("el editor existe", bool(ventana.editor.winfo_exists()))
    except Exception as e:
        comprobar(f"el HUD NO se construye: {e}", False)
        voz.cerrar()
        return 1

    # 4. Las acciones hacen lo que dicen ------------------------------------
    print("\n4. Acciones")
    try:
        ventana.accion_insertar_plantilla()
        ventana.raiz.update()
        comprobar("insertar plantilla escribe texto",
                  bool(ventana._texto().strip()))
        comprobar("no quedan marcas de cursor", "|" not in ventana._texto())

        ventana.accion_cambiar_plantilla()
        comprobar("cambiar plantilla rota el catálogo",
                  ventana.plantilla.clave == "narrativo")

        ventana.editor.delete("1.0", "end")
        ventana.editor.insert("1.0", "diálogo")
        ventana.accion_aplicar_sangria()
        comprobar("la sangría va al margen", ventana._texto().startswith(" "))

        voz._motor.dicho.clear()
        ventana.accion_leer_linea()
        voz.esperar_silencio(limite=5)
        comprobar("leer línea produce voz",
                  any("Línea" in t for t in voz._motor.dicho))
    except Exception as e:
        comprobar(f"una acción ha fallado: {e}", False)

    # 5. Los atajos globales se registran -----------------------------------
    print("\n5. Atajos")
    try:
        mapa = construir_mapa(
            cfg.DEFAULTS["atajos"], ventana.encolar_orden, set(ventana.acciones())
        )
        comprobar(f"se construyen {len(mapa)} combinaciones", len(mapa) >= 18)

        ventana.encolar_orden("cambiar_plantilla")
        ventana._atender_cola()
        comprobar("una orden encolada se ejecuta",
                  ventana.plantilla.clave == "escaleta")
    except Exception as e:
        comprobar(f"los atajos han fallado: {e}", False)

    # 5b. Accesibilidad, importación y exportación ---------------------------
    print("\n5b. Accesibilidad y archivos")
    try:
        from .hud import ORDEN_TEMAS

        for _ in ORDEN_TEMAS:
            ventana.accion_alto_contraste()
        comprobar("los tres temas se aplican sin fallar", True, clave="TEMAS")

        inicial = ventana.tamano
        ventana.accion_letra_mas_grande()
        comprobar("la letra se puede agrandar", ventana.tamano > inicial)
        ventana.accion_letra_mas_pequena()

        ventana.accion_modo_solo_voz()
        ventana.raiz.update()
        oculto = not ventana.editor.winfo_ismapped()
        ventana.accion_modo_solo_voz()
        ventana.raiz.update()
        comprobar("el modo solo voz se activa y se deshace",
                  oculto and ventana.editor.winfo_ismapped())

        import tempfile as _tmp
        from pathlib import Path as _Path

        with _tmp.TemporaryDirectory() as carpeta:
            origen = _Path(carpeta) / "guion.txt"
            origen.write_text(
                "INT. CASA - DÍA\n\n                    ELENA\n          Hola.\n",
                encoding="utf-8",
            )
            ventana.abrir(origen)
            lineas = ventana._texto().split("\n")
            comprobar(
                "importar conserva las sangrías",
                lineas[2].startswith(" " * 20) and lineas[3].startswith(" " * 10),
                clave="IMPORTAR",
            )
    except Exception as e:
        comprobar(f"la accesibilidad ha fallado: {e}", False, clave="IMPORTAR")

    # 5c. Exportación a LibreOffice y Word --------------------------------
    print("\n5c. Exportar con el formato de Julián")
    try:
        import tempfile as _tmpx
        from pathlib import Path as _Pathx

        from . import exportar_odt as _eo
        from . import plantillas as _plx

        with _tmpx.TemporaryDirectory() as carpeta:
            odt = _Pathx(carpeta) / "prueba.odt"
            _eo.exportar("     Narrador.\n\n  —Diálogo.", odt, _plx.NOVELA)
            leido = _eo.leer(odt)
            dial = {k.split("}")[1]: v for k, v in leido["estilos"]["Dialogo"].items()}
            comprobar(
                "el .odt lleva las medidas de Julián",
                leido["mimetype_primero"]
                and dial.get("margin-left") == "0.63cm"
                and dial.get("text-indent") == "-0.63cm"
                and dial.get("margin-bottom") == "18pt",
                clave="ODT",
            )
    except Exception as e:
        comprobar(f"la exportación a LibreOffice ha fallado: {e}", False, clave="ODT")

    # 6. Dictado por voz -----------------------------------------------------
    print("\n6. Dictado")
    try:
        from . import dictado as moddictado

        comprobar(
            "los comandos de puntuación funcionan",
            moddictado.aplicar_puntuacion("hola coma qué tal punto") == "Hola, qué tal.",
        )

        # Ciclo completo con reconocedor y micrófono falsos: verifica que el
        # texto dictado llega al editor a través de la cola de eventos.
        servicio = moddictado.ServicioDictado(
            notificar=ventana._evento_dictado,
            ajustes={"activado": True, "modelo": "fingido"},
            fabrica_motor=lambda: moddictado.MotorDictadoFalso(["prueba de dictado"]),
            fabrica_captura=lambda: moddictado.CapturaFalsa(),
        )
        ventana.servicio_dictado = servicio
        ventana.editor.delete("1.0", "end")
        servicio.empezar()

        import time as _t

        plazo = _t.monotonic() + 6
        while servicio.activo and _t.monotonic() < plazo:
            ventana._atender_dictado()
            ventana.raiz.update()
            _t.sleep(0.02)
        _t.sleep(0.15)
        ventana._atender_dictado()
        ventana.raiz.update()

        comprobar(
            "el texto dictado llega al editor",
            "Prueba de dictado" in ventana._texto(),
        )

        # Y las librerías reales, que solo son un aviso: el programa
        # funciona sin dictado, simplemente sin esa función.
        try:
            import sounddevice  # noqa: F401
            import vosk  # noqa: F401

            comprobar("vosk y sounddevice están empaquetados", True,
                      clave="DICTADO_EMPAQUETADO")
        except Exception as e:
            comprobar(f"dictado real no disponible ({type(e).__name__})", False,
                      critico=False, clave="DICTADO_EMPAQUETADO")

        if moddictado.localizar_modelo() is None:
            comprobar("falta el modelo de voz (se descarga aparte)", False,
                      critico=False, clave="MODELO")
        else:
            comprobar("el modelo de voz está instalado", True, clave="MODELO")
    except Exception as e:
        comprobar(f"el dictado ha fallado: {e}", False)

    # 6b. Corrección por voz -------------------------------------------------
    print("\n6b. Corrección por voz (F9)")
    try:
        from . import correccion as modcorr

        comprobar(
            "la orden 'cambia casa por cosa' se interpreta",
            modcorr.interpretar_orden("cambia casa por cosa").tipo == "cambiar",
        )
        r = modcorr.aplicar(
            "la casa estaba en silencio.",
            modcorr.interpretar_orden("cambia casa por cosa"), (0, 27),
        )
        comprobar("se sustituye solo esa palabra",
                  r.texto == "la cosa estaba en silencio.", clave="CORRECCION")

        # Ciclo completo en el HUD, con dictado simulado
        ventana.editor.delete("1.0", "end")
        ventana.editor.insert("1.0", "Aquella noche no dormí.")
        ventana.editor.mark_set("insert", "end-1c")
        servicio = moddictado.ServicioDictado(
            notificar=ventana._evento_dictado,
            ajustes={"activado": True, "modelo": "fingido"},
            fabrica_motor=lambda: moddictado.MotorDictadoFalso(["cambia noche por tarde"]),
            fabrica_captura=lambda: moddictado.CapturaFalsa(),
        )
        ventana.servicio_dictado = servicio
        ventana.accion_corregir()
        plazo = _t.monotonic() + 6
        while _t.monotonic() < plazo:
            ventana._atender_dictado()
            ventana.raiz.update()
            _t.sleep(0.02)
            if not servicio.activo and ventana.cola_dictado.empty():
                break
        _t.sleep(0.15)
        ventana._atender_dictado()
        comprobar("F9 corrige la palabra en el editor",
                  ventana._texto() == "Aquella tarde no dormí.")
    except Exception as e:
        comprobar(f"la corrección ha fallado: {e}", False, clave="CORRECCION")

    # 7. Guardar en disco ----------------------------------------------------
    print("\n7. Guardado")
    import tempfile

    try:
        with tempfile.TemporaryDirectory() as tmp:
            ventana.ajustes["carpeta_guiones"] = tmp
            ventana.ruta_actual = None
            ventana.editor.delete("1.0", "end")
            ventana.editor.insert("1.0", "INT. PRUEBA - DÍA")
            ventana.accion_guardar()
            comprobar("el archivo se crea",
                      bool(ventana.ruta_actual and ventana.ruta_actual.exists()),
                      clave="GUARDADO")
    except Exception as e:
        comprobar(f"el guardado ha fallado: {e}", False)

    try:
        ventana.raiz.destroy()
    except Exception:
        pass
    voz.cerrar()

    print("\n" + "=" * 60)
    if fallos:
        print(f"AUTOTEST FALLIDO: {fallos} comprobación(es) crítica(s).")
    else:
        print("AUTOTEST CORRECTO: este binario arranca, habla y responde.")

    # --- Marcas para la CI, sin un solo carácter fuera de ASCII ----------
    # Un script que busque texto acentuado en la salida de una consola de
    # Windows falla aunque todo haya ido bien. Estas líneas se leen igual
    # con cualquier página de códigos.
    print()
    print("--- MARCAS ---")
    for clave, estado in sorted(marcas.items()):
        print(f"VOZCLIP_{clave}={estado}")
    print(f"VOZCLIP_RESULTADO={'FALLO' if fallos else 'OK'}")
    print("--- FIN MARCAS ---")

    return 1 if fallos else 0


def main(argv: list[str] | None = None) -> int:
    _preparar_salida()
    _forzar_utf8()
    args = construir_parser().parse_args(argv)

    _iniciar_registro()
    ruta_config = cfg.crear_si_no_existe()
    ajustes = cfg.cargar()

    if args.config:
        print(f"Archivo de configuración: {ruta_config}")
        print(f"Carpeta de guiones:       {cfg.carpeta_guiones(ajustes)}")
        return 0

    if args.instalar_modelo_dictado:
        return instalar_modelo()

    if args.autotest:
        return autotest()

    if args.diagnostico:
        return diagnostico()

    # --- Arranque del servicio de voz -------------------------------------
    # Si esto falla, falla AQUÍ y se ve, en vez de dejar el programa mudo.
    try:
        voz = ServicioVoz(args.motor)
        voz.arrancar()
    except Exception as e:
        _log("ERROR: no se ha podido iniciar el motor de voz.", error=True)
        _log(f"  Detalle: {e}", error=True)
        _log("  Ejecuta VozClip-Diagnostico.exe para ver qué falta.", error=True)
        return 1

    _instalar_manejador_de_errores(voz)
    voz.poner_velocidad(ajustes.get("velocidad", 0))
    voz.poner_volumen(ajustes.get("volumen", 100))
    if ajustes.get("voz"):
        voz.poner_voz(ajustes["voz"])

    # --- Modos de un solo disparo -----------------------------------------
    if args.voces:
        nombres = voz.voces()
        print("\n".join(nombres) if nombres else "No hay voces instaladas.")
        voz.hablar("Voces instaladas: " + ", ".join(nombres))
        voz.esperar_silencio(limite=60)
        voz.cerrar()
        return 0

    if args.leer:
        voz.hablar(args.leer)
        voz.esperar_silencio(limite=300)
        voz.cerrar()
        return 0

    # --- Modo normal: abrir el HUD ----------------------------------------
    try:
        from .hud import HUD
    except Exception as e:
        _log("ERROR: no se ha podido cargar la interfaz gráfica.", error=True)
        _log(f"  Detalle: {e}", error=True)
        voz.hablar(
            "No se ha podido abrir la ventana. Falta tkinter. "
            "Reinstala Python marcando la opción tcl y tk."
        )
        voz.esperar_silencio(limite=15)
        voz.cerrar()
        return 1

    try:
        ventana = HUD(voz, ajustes, guardar_ajustes=cfg.guardar)
    except Exception as e:
        _log(f"ERROR al construir la ventana: {e}", error=True)
        voz.hablar(f"Error al abrir la ventana: {type(e).__name__}")
        voz.esperar_silencio(limite=10)
        voz.cerrar()
        return 1

    if args.archivo:
        ventana.abrir(Path(args.archivo))

    # --- Atajos globales ---------------------------------------------------
    escuchador = None
    if not args.sin_atajos_globales:
        mapa = construir_mapa(
            ajustes.get("atajos", {}),
            ventana.encolar_orden_global,      # cede si la ventana tiene el foco
            acciones_validas=set(ventana.acciones()),
        )
        escuchador = EscuchadorAtajos(mapa)
        if escuchador.arrancar():
            _log(f"Atajos globales activos ({len(mapa)} combinaciones).")
        else:
            # Degradación elegante: la ventana sigue siendo usable.
            _log(f"AVISO: atajos globales no disponibles ({escuchador.error}).", error=True)
            _log("       Los atajos siguen funcionando dentro de la ventana.")
            ventana.decir(
                "Aviso: los atajos globales no están disponibles. "
                "Dentro de la ventana sí funcionan."
            )

    if not args.silencio:
        ventana.saludar()

    _log("VozClip Escritor en marcha. Ctrl+Alt+H para oír los atajos.")

    try:
        ventana.arrancar()          # bucle de tkinter, bloquea aquí
    except KeyboardInterrupt:
        pass
    finally:
        if escuchador:
            escuchador.parar()
        voz.cerrar()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
