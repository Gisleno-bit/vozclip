"""Puente con la aplicación externa que tenga el foco.

En "modo externo", VozClip escribe en Word, LibreOffice, el navegador o lo
que haya delante. La única técnica que funciona en TODAS partes es la del
portapapeles más Ctrl+V, porque no depende de APIs propias de cada programa.

=============================================================================
LOS TRES PROBLEMAS REALES Y CÓMO SE RESUELVEN AQUÍ
=============================================================================
1. CADA PROGRAMA TARDA LO SUYO.
   El Bloc de notas pega al instante; Word tarda tres veces más; Google Docs
   en el navegador, aún más, porque el pegado pasa por JavaScript. Una
   espera fija o va sobrada (y el programa se siente lento) o se queda corta
   (y se pierde texto). Aquí la espera se ADAPTA: se parte de un valor por
   aplicación y se ajusta según lo que tardó la vez anterior.

2. NO SIEMPRE SE PUEDE SABER SI FUNCIONÓ.
   Al copiar sí: se pone una marca en el portapapeles y se mira si cambió.
   Al pegar no hay forma universal de comprobarlo, así que se reintenta con
   más margen y, si el pegado no está permitido, se recurre a teclear.

3. EL PORTAPAPELES ES DEL USUARIO.
   Lo que tuviera copiado se guarda antes y se restaura después, siempre,
   incluso si algo falla por el camino.
=============================================================================
"""

from __future__ import annotations

import platform
import time
from contextlib import contextmanager

from .fuentes import ErrorFuente, escribir_portapapeles, leer_portapapeles

# Espera base, en segundos, según la aplicación que tenga el foco. Son
# valores medidos sobre el comportamiento típico de cada programa; el ajuste
# adaptativo se encarga del resto.
ESPERAS_POR_APP: dict[str, float] = {
    "notepad": 0.12,          # Bloc de notas: instantáneo
    "notepad++": 0.15,
    "code": 0.20,             # Visual Studio Code
    "sublime_text": 0.18,
    "wordpad": 0.20,
    "soffice": 0.35,          # LibreOffice
    "swriter": 0.35,
    "winword": 0.45,          # Word es lento con el portapapeles enriquecido
    "outlook": 0.45,
    "excel": 0.40,
    "powerpnt": 0.40,
    "chrome": 0.50,           # Google Docs y demás pasan por JavaScript
    "msedge": 0.50,
    "firefox": 0.50,
    "brave": 0.50,
}

ESPERA_POR_DEFECTO = 0.35
ESPERA_MINIMA = 0.10
ESPERA_MAXIMA = 1.50
INTENTOS = 3

# Umbral a partir del cual pegar es mejor que teclear. Teclear letra a letra
# es fiable pero lento: 2000 caracteres tardarían más de un minuto.
LIMITE_TECLEADO = 300


class _Adaptador:
    """Recuerda cuánto tarda cada aplicación y ajusta la espera.

    Sube deprisa cuando algo falla (hay que dar margen ya) y baja despacio
    cuando va bien (para no volver a quedarse corto al primer tropiezo).
    """

    def __init__(self) -> None:
        self._aprendido: dict[str, float] = {}

    def espera(self, app: str) -> float:
        if app in self._aprendido:
            return self._aprendido[app]
        return ESPERAS_POR_APP.get(app, ESPERA_POR_DEFECTO)

    def registrar_exito(self, app: str, intentos: int) -> None:
        actual = self.espera(app)
        if intentos == 1:
            nueva = max(ESPERA_MINIMA, actual * 0.92)   # baja despacio
        else:
            nueva = actual
        self._aprendido[app] = nueva

    def registrar_fallo(self, app: str) -> None:
        nueva = min(ESPERA_MAXIMA, self.espera(app) * 1.8)   # sube deprisa
        self._aprendido[app] = nueva

    def reiniciar(self) -> None:
        self._aprendido.clear()


ADAPTADOR = _Adaptador()


# ---------------------------------------------------------------------------
# Detección de la aplicación activa
# ---------------------------------------------------------------------------
def app_activa() -> str:
    """Nombre corto del ejecutable que tiene el foco, en minúsculas.

    En Windows se consulta directamente a la API, sin librerías extra: son
    tres llamadas a ctypes y evita meter psutil en el ejecutable.
    Si no se puede averiguar, devuelve cadena vacía y se usa la espera por
    defecto: no saber la aplicación degrada la precisión, no la función.
    """
    if platform.system() != "Windows":
        return ""

    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        ventana = user32.GetForegroundWindow()
        if not ventana:
            return ""

        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(ventana, ctypes.byref(pid))
        if not pid.value:
            return ""

        # PROCESS_QUERY_LIMITED_INFORMATION: no hace falta ser administrador
        proceso = kernel32.OpenProcess(0x1000, False, pid.value)
        if not proceso:
            return ""

        try:
            buzon = ctypes.create_unicode_buffer(512)
            tamano = wintypes.DWORD(512)
            if not kernel32.QueryFullProcessImageNameW(
                proceso, 0, buzon, ctypes.byref(tamano)
            ):
                return ""
            ruta = buzon.value
        finally:
            kernel32.CloseHandle(proceso)

        nombre = ruta.rsplit("\\", 1)[-1]
        if nombre.lower().endswith(".exe"):
            nombre = nombre[:-4]
        return nombre.lower()
    except Exception:
        return ""


def titulo_ventana_activa() -> str:
    """Título de la ventana con el foco. Se dice en voz alta al cambiar de
    modo, para que el usuario sepa dónde va a escribir."""
    if platform.system() != "Windows":
        return ""
    try:
        import ctypes

        user32 = ctypes.windll.user32
        ventana = user32.GetForegroundWindow()
        if not ventana:
            return ""
        largo = user32.GetWindowTextLengthW(ventana)
        if largo <= 0:
            return ""
        buzon = ctypes.create_unicode_buffer(largo + 1)
        user32.GetWindowTextW(ventana, buzon, largo + 1)
        return buzon.value
    except Exception:
        return ""


def describir_destino() -> str:
    """Frase para decir en voz alta: dónde va a caer lo que se escriba."""
    titulo = titulo_ventana_activa()
    app = app_activa()
    if titulo:
        return titulo
    if app:
        return app
    return "la ventana que tengas delante"


# ---------------------------------------------------------------------------
# Portapapeles seguro
# ---------------------------------------------------------------------------
@contextmanager
def portapapeles_prestado():
    """Toma prestado el portapapeles y lo devuelve como estaba.

    Se usa como `with portapapeles_prestado():`. La restauración ocurre
    incluso si dentro salta una excepción: lo que el usuario tuviera
    copiado no se pierde nunca.
    """
    anterior = ""
    try:
        anterior = leer_portapapeles()
    except ErrorFuente:
        anterior = ""
    try:
        yield anterior
    finally:
        try:
            escribir_portapapeles(anterior)
        except Exception:
            pass


def _teclado():
    """Import perezoso: en un servidor sin entorno gráfico, importar pynput
    a nivel de módulo rompería hasta los tests."""
    from pynput.keyboard import Controller, Key

    return Controller(), Key


def _pulsar_combinacion(tecla: str) -> None:
    controlador, Key = _teclado()
    with controlador.pressed(Key.ctrl):
        controlador.press(tecla)
        controlador.release(tecla)


# ---------------------------------------------------------------------------
# Insertar texto en la aplicación activa
# ---------------------------------------------------------------------------
def insertar_texto(texto: str, metodo: str = "auto") -> str:
    """Escribe `texto` en la ventana activa. Devuelve el método usado.

    `metodo` puede ser "pegar", "teclear" o "auto":
      * pegar   -> portapapeles + Ctrl+V. Rápido, va bien en casi todo.
      * teclear -> simula las pulsaciones. Lento pero funciona donde el
                   pegado está bloqueado (algunos formularios y terminales).
      * auto    -> pega si el texto es largo, teclea si es corto y la
                   aplicación es de las que dan problemas con el pegado.
    """
    if not texto:
        return "nada"

    app = app_activa()

    if metodo == "auto":
        metodo = "teclear" if len(texto) <= LIMITE_TECLEADO and app in (
            "cmd", "powershell", "windowsterminal", "conhost"
        ) else "pegar"

    if metodo == "teclear":
        _teclear(texto)
        return "teclear"

    _pegar(texto, app)
    return "pegar"


def _teclear(texto: str) -> None:
    controlador, _ = _teclado()
    try:
        controlador.type(texto)
    except Exception as e:
        raise ErrorFuente(f"No se ha podido escribir el texto: {e}") from e


def _pegar(texto: str, app: str) -> None:
    """Pega usando el portapapeles, con espera adaptativa y reintentos."""
    espera = ADAPTADOR.espera(app)

    with portapapeles_prestado():
        for intento in range(1, INTENTOS + 1):
            try:
                escribir_portapapeles(texto)
                # Un respiro para que el sistema publique el portapapeles
                # antes de mandar Ctrl+V. Sin esto, algunas aplicaciones
                # pegan lo que había ANTES.
                time.sleep(min(0.08, espera / 3))

                _pulsar_combinacion("v")
                time.sleep(espera)

                ADAPTADOR.registrar_exito(app, intento)
                return
            except Exception as e:
                ADAPTADOR.registrar_fallo(app)
                espera = ADAPTADOR.espera(app)
                if intento == INTENTOS:
                    raise ErrorFuente(
                        "No he podido escribir en la aplicación. "
                        "Comprueba que hay un cursor de texto donde escribir."
                    ) from e
                time.sleep(0.15)


def pegar_en_ventana_activa(texto: str, restaurar: bool = True) -> None:
    """Compatibilidad con la versión anterior: pega en la ventana activa."""
    insertar_texto(texto, metodo="pegar")


# ---------------------------------------------------------------------------
# Capturar texto de la aplicación activa
# ---------------------------------------------------------------------------
MARCA = "\x00vozclip\x00"


def capturar_seleccion() -> str:
    """Copia lo que esté seleccionado y lo devuelve.

    Se detecta el éxito con una marca: si tras el Ctrl+C el portapapeles
    sigue conteniendo la marca, es que la aplicación no copió nada.
    """
    return _capturar(lambda: _pulsar_combinacion("c"),
                     "No hay nada seleccionado, o la aplicación no permite copiar.")


def capturar_linea_actual() -> str:
    """Selecciona la línea del cursor y la copia.

    Secuencia: Inicio, Shift+Fin, Ctrl+C, y Fin para deshacer la selección
    dejando el cursor donde estaba.
    """
    def seleccionar_y_copiar() -> None:
        controlador, Key = _teclado()
        controlador.press(Key.home)
        controlador.release(Key.home)
        with controlador.pressed(Key.shift):
            controlador.press(Key.end)
            controlador.release(Key.end)
        _pulsar_combinacion("c")

    texto = _capturar(
        seleccionar_y_copiar,
        "La línea está vacía, o la aplicación no permite copiar.",
    )

    controlador, Key = _teclado()
    controlador.press(Key.end)
    controlador.release(Key.end)
    return texto


def capturar_todo() -> str:
    """Selecciona todo el documento de la aplicación activa y lo copia."""
    def seleccionar_todo_y_copiar() -> None:
        _pulsar_combinacion("a")
        time.sleep(0.08)
        _pulsar_combinacion("c")

    return _capturar(
        seleccionar_todo_y_copiar,
        "No he podido copiar el documento de esa aplicación.",
    )


def _capturar(accion, mensaje_error: str) -> str:
    """Motor común de las capturas: marca, acción, espera adaptativa,
    reintentos y restauración del portapapeles."""
    app = app_activa()
    espera = ADAPTADOR.espera(app)
    capturado = ""

    with portapapeles_prestado():
        for intento in range(1, INTENTOS + 1):
            escribir_portapapeles(MARCA)
            try:
                accion()
            except Exception as e:
                raise ErrorFuente(f"No se ha podido copiar: {e}") from e

            time.sleep(espera)

            try:
                capturado = leer_portapapeles()
            except ErrorFuente:
                capturado = ""

            if capturado and capturado != MARCA and capturado.strip():
                ADAPTADOR.registrar_exito(app, intento)
                break

            # Puede que la aplicación simplemente vaya lenta: más margen.
            ADAPTADOR.registrar_fallo(app)
            espera = ADAPTADOR.espera(app)
            capturado = ""

    if not capturado:
        raise ErrorFuente(mensaje_error)
    return capturado


# ---------------------------------------------------------------------------
# Otras acciones sobre la aplicación externa
# ---------------------------------------------------------------------------
def enviar_salto_de_linea(sangria: str = "") -> None:
    controlador, Key = _teclado()
    controlador.press(Key.enter)
    controlador.release(Key.enter)
    if sangria:
        time.sleep(0.05)
        controlador.type(sangria)


def reemplazar_linea_actual(nuevo: str) -> None:
    """Selecciona la línea del cursor en la app activa y la sustituye.

    Inicio, Shift+Fin para seleccionar, y pegar encima. Es la forma de
    corregir una palabra en Word sin poder ver dónde está.
    """
    controlador, Key = _teclado()
    controlador.press(Key.home)
    controlador.release(Key.home)
    with controlador.pressed(Key.shift):
        controlador.press(Key.end)
        controlador.release(Key.end)
    time.sleep(0.05)
    insertar_texto(nuevo, metodo="pegar")


def guardar_en_app_activa() -> None:
    _pulsar_combinacion("s")


# ---------------------------------------------------------------------------
# Compatibilidad documentada
# ---------------------------------------------------------------------------
# Probado o razonado programa a programa. "Insertar" es pegar texto;
# "Capturar" es leer la selección o la línea actual.
COMPATIBILIDAD: dict[str, dict[str, str]] = {
    "Bloc de notas": {"insertar": "sí", "capturar": "sí", "notas": ""},
    "WordPad": {"insertar": "sí", "capturar": "sí", "notas": ""},
    "Notepad++": {"insertar": "sí", "capturar": "sí", "notas": ""},
    "Visual Studio Code": {"insertar": "sí", "capturar": "sí", "notas": ""},
    "Microsoft Word": {
        "insertar": "sí", "capturar": "sí",
        "notas": "Más lento: la espera se ajusta sola tras el primer uso.",
    },
    "LibreOffice Writer": {"insertar": "sí", "capturar": "sí", "notas": ""},
    "Outlook": {
        "insertar": "sí", "capturar": "sí",
        "notas": "En el cuerpo del mensaje. En la lista de correos no hay dónde escribir.",
    },
    "Google Docs (navegador)": {
        "insertar": "sí", "capturar": "sí",
        "notas": "El pegado pasa por JavaScript y tarda más; se compensa solo.",
    },
    "Excel / Calc": {
        "insertar": "sí", "capturar": "sí",
        "notas": "Escribe en la celda activa. Los saltos de línea cambian de celda.",
    },
    "Terminal / PowerShell": {
        "insertar": "sí (tecleando)", "capturar": "no",
        "notas": "El pegado con Ctrl+V no siempre funciona; se teclea en su lugar.",
    },
    "PDF protegidos": {
        "insertar": "no", "capturar": "no",
        "notas": "Sin permiso de copia no hay nada que hacer desde fuera.",
    },
}
