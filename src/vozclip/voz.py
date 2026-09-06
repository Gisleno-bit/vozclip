"""Motores de síntesis de voz (TTS) y el servicio que los gobierna.

=============================================================================
POR QUÉ ESTE ARCHIVO CAMBIÓ POR COMPLETO
=============================================================================
En la versión anterior el objeto COM de SAPI5 se creaba en el hilo principal
y luego se llamaba desde el hilo del escuchador de teclado. Windows no
permite eso: los objetos COM viven en un "apartamento" (STA) y solo pueden
usarse desde el hilo que hizo CoInitialize. El resultado era que los atajos
sí se detectaban, pero la llamada a Speak lanzaba una excepción que el
envoltorio de seguridad se tragaba en silencio.

La solución correcta no es poner más "try/except", sino tener UN SOLO hilo
dueño de la voz. `ServicioVoz` es ese hilo: crea el motor dentro de sí
mismo, hace CoInitialize, y recibe órdenes por una cola. Cualquier otro
hilo (el teclado, la ventana de tkinter) puede pedirle que hable sin tocar
nunca el objeto COM.
=============================================================================
"""

from __future__ import annotations

import os
import platform
import queue
import shutil
import subprocess
import threading
import time
from typing import Protocol


class MotorVoz(Protocol):
    """Contrato que cumple cualquier motor de voz."""

    def hablar(self, texto: str) -> None: ...
    def parar(self) -> None: ...
    def pausar(self) -> None: ...
    def reanudar(self) -> None: ...
    def voces(self) -> list[str]: ...
    def poner_voz(self, nombre: str) -> bool: ...
    def poner_velocidad(self, valor: int) -> None: ...
    def poner_volumen(self, valor: int) -> None: ...
    def cerrar(self) -> None: ...


# ---------------------------------------------------------------------------
# Windows: SAPI5
# ---------------------------------------------------------------------------
class MotorSAPI5:
    """Motor nativo de Windows a través de COM.

    ATENCIÓN: debe instanciarse y usarse SIEMPRE desde el mismo hilo.
    `ServicioVoz` se encarga de garantizarlo.
    """

    ASINCRONO = 1   # SVSFlagsAsync: no bloquea al que llama
    PURGAR = 2      # SVSFPurgeBeforeSpeak: corta lo que se esté diciendo

    def __init__(self) -> None:
        import win32com.client

        self._voz = win32com.client.Dispatch("SAPI.SpVoice")
        self._pausado = False

    def hablar(self, texto: str) -> None:
        if not texto:
            return
        self._pausado = False
        self._voz.Speak(texto, self.ASINCRONO | self.PURGAR)

    def encolar(self, texto: str) -> None:
        """Añade texto sin cortar lo que ya está sonando."""
        if not texto:
            return
        self._voz.Speak(texto, self.ASINCRONO)

    def parar(self) -> None:
        if self._pausado:
            self._voz.Resume()
            self._pausado = False
        self._voz.Speak("", self.ASINCRONO | self.PURGAR)

    def pausar(self) -> None:
        if not self._pausado:
            self._voz.Pause()
            self._pausado = True

    def reanudar(self) -> None:
        if self._pausado:
            self._voz.Resume()
            self._pausado = False

    @property
    def pausado(self) -> bool:
        return self._pausado

    def esperar(self, milisegundos: int = 600000) -> None:
        self._voz.WaitUntilDone(milisegundos)

    def voces(self) -> list[str]:
        catalogo = self._voz.GetVoices()
        return [catalogo.Item(i).GetDescription() for i in range(catalogo.Count)]

    def poner_voz(self, nombre: str) -> bool:
        if not nombre:
            return False
        catalogo = self._voz.GetVoices()
        for i in range(catalogo.Count):
            token = catalogo.Item(i)
            if nombre.lower() in token.GetDescription().lower():
                self._voz.Voice = token
                return True
        return False

    def poner_velocidad(self, valor: int) -> None:
        self._voz.Rate = max(-10, min(10, int(valor)))

    def poner_volumen(self, valor: int) -> None:
        self._voz.Volume = max(0, min(100, int(valor)))

    def cerrar(self) -> None:
        try:
            self.parar()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Linux / macOS: proceso externo
# ---------------------------------------------------------------------------
class MotorComando:
    """Lanza `espeak-ng` (Linux) o `say` (macOS) como proceso hijo."""

    def __init__(self, ejecutable: str | None = None) -> None:
        self._exe = ejecutable or self._detectar()
        if not self._exe:
            raise RuntimeError(
                "No se encontró ningún motor de voz. En Linux instala "
                "espeak-ng con: sudo apt install espeak-ng"
            )
        self._proceso: subprocess.Popen | None = None
        self._velocidad = 0
        self._voz_actual: str | None = None

    @staticmethod
    def _detectar() -> str | None:
        for candidato in ("espeak-ng", "espeak", "say"):
            if shutil.which(candidato):
                return candidato
        return None

    def _argumentos(self, texto: str) -> list[str]:
        ritmo = str(175 + self._velocidad * 15)
        if self._exe == "say":  # macOS
            args = [self._exe]
            if self._voz_actual:
                args += ["-v", self._voz_actual]
            return args + ["-r", ritmo, texto]
        return [self._exe, "-s", ritmo, "-v", self._voz_actual or "es", texto]

    def hablar(self, texto: str) -> None:
        if not texto:
            return
        self.parar()
        self._proceso = subprocess.Popen(
            self._argumentos(texto),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def encolar(self, texto: str) -> None:
        """espeak no tiene cola: esperamos a que acabe y seguimos."""
        if not texto:
            return
        if self._proceso:
            try:
                self._proceso.wait(timeout=300)
            except Exception:
                pass
        self.hablar(texto)

    def parar(self) -> None:
        if self._proceso and self._proceso.poll() is None:
            self._proceso.terminate()
        self._proceso = None

    def pausar(self) -> None:
        self.parar()  # espeak no sabe pausar de verdad

    def reanudar(self) -> None:
        pass

    @property
    def pausado(self) -> bool:
        return False

    def esperar(self, milisegundos: int = 600000) -> None:
        if self._proceso:
            try:
                self._proceso.wait(timeout=milisegundos / 1000)
            except Exception:
                pass

    def voces(self) -> list[str]:
        return [self._voz_actual or "es"]

    def poner_voz(self, nombre: str) -> bool:
        self._voz_actual = nombre
        return True

    def poner_velocidad(self, valor: int) -> None:
        self._velocidad = max(-10, min(10, int(valor)))

    def poner_volumen(self, valor: int) -> None:
        pass  # se ajusta desde el mezclador del sistema

    def cerrar(self) -> None:
        self.parar()


# ---------------------------------------------------------------------------
# Motor de mentira, para tests
# ---------------------------------------------------------------------------
class MotorFalso:
    """No emite sonido: solo apunta lo que le han pedido."""

    def __init__(self) -> None:
        self.dicho: list[str] = []
        self.velocidad = 0
        self.volumen = 100
        self.voz_actual: str | None = None
        self.pausado = False
        self.paradas = 0

    def hablar(self, texto: str) -> None:
        if texto:
            self.dicho.append(texto)
            self.pausado = False

    def encolar(self, texto: str) -> None:
        if texto:
            self.dicho.append(texto)

    def parar(self) -> None:
        self.paradas += 1
        self.pausado = False

    def pausar(self) -> None:
        self.pausado = True

    def reanudar(self) -> None:
        self.pausado = False

    def esperar(self, milisegundos: int = 0) -> None:
        pass

    def voces(self) -> list[str]:
        return ["Voz de prueba A", "Voz de prueba B"]

    def poner_voz(self, nombre: str) -> bool:
        self.voz_actual = nombre
        return True

    def poner_velocidad(self, valor: int) -> None:
        self.velocidad = max(-10, min(10, int(valor)))

    def poner_volumen(self, valor: int) -> None:
        self.volumen = max(0, min(100, int(valor)))

    def cerrar(self) -> None:
        pass


def eleccion_motor(forzar: str | None = None) -> str:
    """Decide QUÉ motor se va a usar, sin construirlo todavía.

    Hace falta saberlo antes de tocar COM: solo el motor SAPI5 necesita
    CoInitialize, y hacerlo cuando no se va a usar es inicializar y
    desinicializar apartamentos COM para nada, cientos de veces durante los
    tests. En los runners de Windows eso acaba provocando un
    "Windows fatal exception: code 0x80000003" al recolectar basura.
    """
    peticion = (forzar or os.environ.get("VOZCLIP_MOTOR") or "").lower()
    if peticion in ("falso", "comando", "sapi5"):
        return peticion
    return "sapi5" if platform.system() == "Windows" else "comando"


def crear_motor(forzar: str | None = None) -> MotorVoz:
    """Devuelve el motor adecuado para este ordenador.

    OJO: hay que llamarlo desde el hilo que vaya a usar el motor. Crearlo en
    un hilo y usarlo en otro es exactamente el fallo que dejó muda la
    versión anterior.
    """
    eleccion = eleccion_motor(forzar)

    if eleccion == "falso":
        return MotorFalso()
    if eleccion == "comando":
        return MotorComando()
    return MotorSAPI5()


# ===========================================================================
# EL SERVICIO DE VOZ: un hilo, un motor, una cola
# ===========================================================================
class ServicioVoz:
    """Único propietario del motor de voz.

    Cumple el mismo contrato `MotorVoz`, así que el resto del programa lo usa
    igual que antes; pero por dentro todo ocurre en un hilo propio y seguro.
    """

    def __init__(self, motor_forzado: str | None = None) -> None:
        self._cola: queue.Queue = queue.Queue()
        self._motor: MotorVoz | None = None
        self._motor_forzado = motor_forzado
        self._listo = threading.Event()
        self._inactivo = threading.Event()
        self._inactivo.set()
        self._error: Exception | None = None
        self._pausado = False
        self._voces_cache: list[str] = []
        self._hilo = threading.Thread(
            target=self._bucle, name="VozClip-TTS", daemon=True
        )

    # -- Ciclo de vida ------------------------------------------------------
    def arrancar(self, espera: float = 10.0) -> None:
        """Lanza el hilo y espera a que el motor esté creado.

        Si el motor falla (por ejemplo, falta pywin32), la excepción se
        propaga AQUÍ, en el arranque, en vez de perderse dentro de un
        callback. Ese es el otro motivo por el que antes no se oía nada:
        el error ocurría demasiado tarde y demasiado lejos.
        """
        self._hilo.start()
        if not self._listo.wait(espera):
            raise RuntimeError("El motor de voz no respondió al arrancar.")
        if self._error:
            raise self._error

    def _bucle(self) -> None:
        # --- COM, solo si de verdad hace falta ----------------------------
        # CoInitialize declara este hilo como apartamento COM, y sin eso
        # Dispatch("SAPI.SpVoice") falla. Pero SOLO lo necesita SAPI5: con
        # el motor falso o con espeak es puro lastre, y en Windows acaba
        # provocando un fallo al recolectar basura tras cientos de hilos.
        pythoncom = None
        if eleccion_motor(self._motor_forzado) == "sapi5":
            try:
                import pythoncom  # viene con pywin32

                pythoncom.CoInitialize()
            except Exception:
                pythoncom = None

        # Todo lo demás va dentro de un try/finally: antes, si la creación
        # del motor fallaba, el `return` se saltaba el CoUninitialize y
        # dejaba el apartamento COM colgado.
        try:
            try:
                self._motor = crear_motor(self._motor_forzado)
                self._voces_cache = list(self._motor.voces())
            except Exception as e:
                self._error = e
                return
            finally:
                self._listo.set()   # arrancar() deja de esperar, haya ido bien o mal

            while True:
                orden, dato = self._cola.get()
                if orden == "fin":
                    break
                self._inactivo.clear()
                try:
                    self._ejecutar(orden, dato)
                except Exception:
                    # Una orden que falle no debe dejar el servicio mudo
                    # para siempre: seguimos atendiendo la cola.
                    pass
                finally:
                    if self._cola.empty():
                        self._inactivo.set()
        finally:
            self._inactivo.set()    # nadie se queda esperando un silencio
            try:
                if self._motor:
                    self._motor.cerrar()
            except Exception:
                pass
            if pythoncom is not None:
                try:
                    pythoncom.CoUninitialize()
                except Exception:
                    pass

    def _ejecutar(self, orden: str, dato) -> None:
        m = self._motor
        if m is None:
            return

        if orden == "hablar":
            m.hablar(dato)
        elif orden == "encolar":
            encolar = getattr(m, "encolar", None)
            (encolar or m.hablar)(dato)
        elif orden == "parar":
            m.parar()
        elif orden == "pausar":
            m.pausar()
        elif orden == "reanudar":
            m.reanudar()
        elif orden == "velocidad":
            m.poner_velocidad(dato)
        elif orden == "volumen":
            m.poner_volumen(dato)
        elif orden == "voz":
            m.poner_voz(dato)

    # -- API pública: se puede llamar desde cualquier hilo ------------------
    def hablar(self, texto: str) -> None:
        if texto:
            self._vaciar_cola()   # lo urgente manda: descartamos lo pendiente
            self._cola.put(("hablar", texto))
            self._pausado = False

    def encolar(self, texto: str) -> None:
        if texto:
            self._cola.put(("encolar", texto))

    def parar(self) -> None:
        self._vaciar_cola()
        self._cola.put(("parar", None))
        self._pausado = False

    def pausar(self) -> None:
        self._cola.put(("pausar", None))
        self._pausado = True

    def reanudar(self) -> None:
        self._cola.put(("reanudar", None))
        self._pausado = False

    @property
    def pausado(self) -> bool:
        return self._pausado

    def voces(self) -> list[str]:
        return list(self._voces_cache)

    def poner_voz(self, nombre: str) -> bool:
        self._cola.put(("voz", nombre))
        return True

    def poner_velocidad(self, valor: int) -> None:
        self._cola.put(("velocidad", max(-10, min(10, int(valor)))))

    def poner_volumen(self, valor: int) -> None:
        self._cola.put(("volumen", max(0, min(100, int(valor)))))

    def cerrar(self) -> None:
        self._cola.put(("fin", None))
        if self._hilo.is_alive():
            self._hilo.join(timeout=3.0)

    def esperar_silencio(self, limite: float = 600.0) -> None:
        """Bloquea hasta que se haya dicho todo lo pendiente.

        Se usa en los modos de un solo disparo (`--leer`), donde si el
        proceso terminara de golpe la voz se cortaría a media frase.
        """
        plazo = time.monotonic() + limite
        while not self._cola.empty() and time.monotonic() < plazo:
            time.sleep(0.05)
        self._inactivo.wait(timeout=max(0.0, plazo - time.monotonic()))

        esperar = getattr(self._motor, "esperar", None)
        if callable(esperar):
            try:
                esperar(int(max(0.0, plazo - time.monotonic()) * 1000))
            except Exception:
                pass

    def _vaciar_cola(self) -> None:
        try:
            while True:
                self._cola.get_nowait()
        except queue.Empty:
            pass
