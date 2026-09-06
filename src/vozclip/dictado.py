"""Dictado por voz: hablar y que el texto aparezca en el guion.

=============================================================================
POR QUÉ VOSK Y NO OTRA COSA
=============================================================================
  * Vosk         39 MB de modelo en español, 7 MB de librería, reconoce en
                 tiempo real con un núcleo de CPU y SIN INTERNET. Es la
                 elección.
  * Whisper      Mucho más preciso, pero arrastra PyTorch: cientos de MB en
                 el .exe y varios segundos de espera por frase en una CPU
                 normal. Para dictar mientras se escribe, esa latencia lo
                 hace inservible.
  * Google Web   Precisión excelente y cero instalación, pero necesita
    Speech       internet. Depender de la conexión para poder escribir es
                 inaceptable en una herramienta de accesibilidad: el día que
                 se cae el router, tu amigo se queda sin poder trabajar.
  * SAPI de      Ya está en Windows, pero su motor de dictado en español
    Windows      exige instalar el paquete de idioma de reconocimiento, que
                 no viene por defecto, y la API COM de eventos es frágil.
                 Queda como posible añadido futuro.

Vosk gana por lo único que aquí no se negocia: funciona siempre, sin red, y
no engorda el programa.
=============================================================================

Reglas de hilos, las mismas de siempre:
  * La captura de audio y el reconocimiento van en un hilo propio.
  * Ese hilo NO toca widgets ni el motor de voz directamente: avisa por un
    callback que el HUD convierte en cola y procesa en el hilo principal.
"""

from __future__ import annotations

import json
import os
import platform
import sys
import threading
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, Callable, Protocol

FRECUENCIA = 16000       # Hz. Es lo que esperan los modelos de Vosk.
TAMANO_BLOQUE = 4000     # muestras por lectura (~0,25 s): buen equilibrio
                         # entre latencia y número de llamadas.


class ErrorDictado(Exception):
    """Fallo del dictado. El mensaje va en castellano y listo para hablarse."""


# ===========================================================================
# Comandos de puntuación hablada
# ===========================================================================
# Sin esto, el dictado devuelve un chorro de palabras sin puntuar, que para
# escribir diálogo no vale nada. La raya (—) es imprescindible en guion.
#
# Se ordenan por número de palabras: las frases largas se buscan primero,
# para que "punto y aparte" no se parta en "punto" + "y" + "aparte".
COMANDOS: dict[str, str] = {
    "punto y aparte": ".\n",
    "punto y seguido": ".",
    "punto y coma": ";",
    "abrir interrogación": "¿",
    "cerrar interrogación": "?",
    "abrir exclamación": "¡",
    "cerrar exclamación": "!",
    "abrir paréntesis": "(",
    "cerrar paréntesis": ")",
    "abre paréntesis": "(",
    "cierra paréntesis": ")",
    "puntos suspensivos": "…",
    "salto de línea": "\n",
    "nueva línea": "\n",
    "dos puntos": ":",
    "guion de diálogo": "—",
    "raya de diálogo": "—",
    "comillas": '"',
    "punto": ".",
    "coma": ",",
    "raya": "—",
    "guion": "-",
}

# Signos que se pegan a la palabra anterior, sin espacio delante.
PEGADOS_IZQUIERDA = set(".,;:?!)…\"")
# Signos tras los que no va espacio.
PEGADOS_DERECHA = set("¿¡(—\"")
# Tras estos, la siguiente palabra va en mayúscula.
FIN_DE_FRASE = set(".?!\n")


def _ordenar_comandos() -> list[tuple[list[str], str]]:
    """Prepara los comandos como listas de palabras, los largos primero."""
    pares = [(frase.split(), simbolo) for frase, simbolo in COMANDOS.items()]
    pares.sort(key=lambda p: len(p[0]), reverse=True)
    return pares


_COMANDOS_ORDENADOS = _ordenar_comandos()


def aplicar_puntuacion(texto: str) -> str:
    """Convierte los comandos hablados en signos de puntuación reales.

        "hola coma qué tal punto"       ->  "hola, qué tal."
        "raya no me lo creo punto"      ->  "—no me lo creo."
    """
    if not texto:
        return ""

    palabras = texto.split()
    piezas: list[str] = []
    i = 0

    while i < len(palabras):
        encontrado = False
        for secuencia, simbolo in _COMANDOS_ORDENADOS:
            largo = len(secuencia)
            candidato = [p.lower().strip(".,;:") for p in palabras[i : i + largo]]
            if candidato == secuencia:
                piezas.append(simbolo)
                i += largo
                encontrado = True
                break
        if not encontrado:
            piezas.append(palabras[i])
            i += 1

    return _unir(piezas)


def _unir(piezas: list[str]) -> str:
    """Junta palabras y signos con los espacios y mayúsculas correctos."""
    salida = ""
    mayuscula_siguiente = True

    for pieza in piezas:
        if not pieza:
            continue

        caracteres_de_signo = PEGADOS_IZQUIERDA | PEGADOS_DERECHA | {"\n", "-"}
        es_signo = all(c in caracteres_de_signo for c in pieza)

        # --- ¿Espacio de separación? ---------------------------------------
        if not salida:
            separador = ""
        elif pieza[0] == "\n" or pieza[0] in PEGADOS_IZQUIERDA:
            separador = ""          # ni antes de un salto ni antes de ",.;:"
        elif salida.endswith("\n") or salida[-1] in PEGADOS_DERECHA:
            separador = ""          # ni después de "¿¡(—"
        else:
            separador = " "

        # --- ¿Mayúscula? ----------------------------------------------------
        contenido = pieza
        if not es_signo:
            if mayuscula_siguiente and contenido:
                contenido = contenido[0].upper() + contenido[1:]
            mayuscula_siguiente = False
        else:
            # Un signo de fin de frase pide mayúscula después.
            # Los de APERTURA (— ¿ ¡ « comillas) no consumen la mayúscula
            # pendiente: en castellano se escribe "—No me lo creo" y
            # "¿Quién anda ahí?", con la inicial en mayúscula.
            # Los de cierre y la coma sí la cancelan: sin esto, "coma y
            # sigue" salía como ", Y sigue".
            if any(c in FIN_DE_FRASE for c in pieza):
                mayuscula_siguiente = True
            elif all(c in PEGADOS_DERECHA for c in pieza):
                pass    # se conserva lo que hubiera
            else:
                mayuscula_siguiente = False

        salida += separador + contenido

    return salida.strip()


def formatear_para_insercion(texto: str, contexto_previo: str = "") -> str:
    """Ajusta el texto dictado al sitio donde va a caer.

    Si el cursor está a mitad de frase, no se pone mayúscula ni punto de
    más; si está al principio de línea o después de un punto, sí.
    """
    if not texto:
        return ""

    limpio = aplicar_puntuacion(texto)
    if not limpio:
        return ""

    anterior = contexto_previo.rstrip(" \t")

    # ¿Hay que empezar en minúscula porque venimos de media frase?
    if anterior and anterior[-1] not in FIN_DE_FRASE and anterior[-1] not in PEGADOS_DERECHA:
        if limpio[0].isupper() and not _parece_nombre_propio(limpio):
            limpio = limpio[0].lower() + limpio[1:]

    # ¿Hace falta un espacio de separación?
    if (
        contexto_previo
        and not contexto_previo[-1].isspace()
        and limpio[0] not in PEGADOS_IZQUIERDA
    ):
        limpio = " " + limpio

    return limpio


def _parece_nombre_propio(texto: str) -> bool:
    """Heurística mínima: si la segunda palabra también va en mayúscula,
    probablemente sea un nombre y no el principio de una frase."""
    partes = texto.split()
    return len(partes) > 1 and partes[1][:1].isupper()


# ===========================================================================
# Motores de reconocimiento
# ===========================================================================
class MotorReconocimiento(Protocol):
    def iniciar(self) -> None: ...
    def alimentar(self, trozo: bytes) -> str | None: ...
    def finalizar(self) -> str: ...
    def cerrar(self) -> None: ...


class MotorVosk:
    """Reconocimiento offline con Vosk.

    El modelo se carga UNA vez y se reutiliza: cargarlo tarda un par de
    segundos, y hacerlo en cada dictado sería insoportable.
    """

    _modelo_cache: Any = None
    _ruta_cache: str | None = None
    ultima_explicacion: str = ""     # qué ruta se usó y por qué

    def __init__(self, ruta_modelo: str | Path | None = None) -> None:
        if ruta_modelo:
            self.ruta_modelo = _buscar_en(Path(ruta_modelo)) or Path(ruta_modelo)
        else:
            self.ruta_modelo = localizar_modelo()
        if self.ruta_modelo is None or not self.ruta_modelo.exists():
            raise ErrorDictado(
                "No encuentro el modelo de voz en español. "
                "Ejecuta VozClip con la opción instalar modelo de dictado, "
                "o descárgalo a mano. Solo hay que hacerlo una vez."
            )
        self._reconocedor = None

    def _cargar_modelo(self) -> Any:
        ruta = str(self.ruta_modelo)
        if MotorVosk._modelo_cache is not None and MotorVosk._ruta_cache == ruta:
            return MotorVosk._modelo_cache

        try:
            from vosk import Model, SetLogLevel
        except ImportError as e:
            raise ErrorDictado(
                "La librería de reconocimiento de voz no está instalada."
            ) from e

        SetLogLevel(-1)   # Vosk es muy hablador por consola; lo callamos

        # La ruta que la librería en C pueda abrir de verdad
        usable, explicacion = ruta_segura_para_vosk(self.ruta_modelo)
        MotorVosk.ultima_explicacion = explicacion

        try:
            modelo = Model(str(usable))
        except Exception as e:
            if not es_ascii(str(usable)):
                raise ErrorDictado(
                    "El modelo está en una carpeta con tildes o eñes en el "
                    "nombre, y la librería de reconocimiento no puede abrirla. "
                    "Ejecuta instalar modelos punto bat: lo dejará en una "
                    "carpeta sin acentos."
                ) from e
            raise ErrorDictado(
                "El modelo de voz está dañado o incompleto. Ejecuta "
                "instalar modelos punto bat para descargarlo de nuevo."
            ) from e

        MotorVosk._modelo_cache = modelo
        MotorVosk._ruta_cache = ruta
        return modelo

    def iniciar(self) -> None:
        from vosk import KaldiRecognizer

        modelo = self._cargar_modelo()
        self._reconocedor = KaldiRecognizer(modelo, FRECUENCIA)
        self._reconocedor.SetWords(False)

    def alimentar(self, trozo: bytes) -> str | None:
        """Devuelve texto parcial cuando Vosk cierra una frase, o None."""
        if self._reconocedor is None:
            return None
        if self._reconocedor.AcceptWaveform(trozo):
            resultado = json.loads(self._reconocedor.Result())
            return resultado.get("text") or None
        return None

    def finalizar(self) -> str:
        if self._reconocedor is None:
            return ""
        resultado = json.loads(self._reconocedor.FinalResult())
        return resultado.get("text", "")

    def cerrar(self) -> None:
        self._reconocedor = None




def hay_gpu_cuda() -> bool:
    """¿CTranslate2 ve una GPU NVIDIA con CUDA?"""
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


def resolver_whisper(ajustes: dict[str, Any]) -> tuple[str, str, str]:
    """Traduce los ajustes a (modelo, dispositivo, tipo de cálculo).

    Con "auto":
      * GPU:  large-v3 en float16. Es el modelo más preciso que existe y
              en una GPU de 8 GB transcribe 10 s de audio en 1 o 2 s.
      * CPU:  small en int8. large-v3 en CPU tarda medio minuto por cada
              10 s de audio: inservible para dictar.
    """
    gpu = hay_gpu_cuda()
    dispositivo = str(ajustes.get("whisper_dispositivo", "auto")).lower()
    if dispositivo == "auto":
        dispositivo = "cuda" if gpu else "cpu"

    modelo = str(ajustes.get("whisper_modelo", "auto")).lower()
    if modelo == "auto":
        modelo = "large-v3" if dispositivo == "cuda" else "small"

    calculo = str(ajustes.get("whisper_calculo", "auto")).lower()
    if calculo == "auto":
        calculo = "float16" if dispositivo == "cuda" else "int8"

    return modelo, dispositivo, calculo


class MotorFasterWhisper:
    """Reconocimiento offline con faster-whisper, opcional.

    =========================================================================
    QUÉ ES Y QUÉ NO ES
    =========================================================================
    faster-whisper es Whisper (OpenAI) reimplementado sobre CTranslate2. Es
    MUCHO más preciso que el modelo pequeño de Vosk, sobre todo con nombres
    propios y frases largas, y funciona sin internet una vez descargado el
    modelo. A cambio:

      * No es streaming. Vosk devuelve frases a medida que hablas; Whisper
        necesita el audio entero y lo transcribe al terminar. Con F1 esto
        encaja: grabas, pulsas F1, y en unos segundos aparece el texto.
        Pero no habrá parciales en pantalla mientras dictas.
      * Pesa: 81 MB de librerías (ctranslate2, numpy, onnxruntime...) más
        el modelo: 75 MB el `base`, 250 MB el `small`. Por eso NO va en el
        ejecutable estándar; se instala aparte con `pip install
        faster-whisper` y se activa en el config.json.
      * Consume CPU: un audio de 10 segundos tarda 3 a 6 segundos con el
        modelo `small` en int8 en un portátil normal.

    Es un motor más detrás de `MotorReconocimiento`: el servicio, el HUD y
    los atajos no saben cuál está debajo.
    =========================================================================
    """

    _modelo_cache: Any = None
    _clave_cache: tuple | None = None

    def __init__(
        self,
        tamano: str = "small",
        dispositivo: str = "cpu",
        tipo_calculo: str = "int8",
        idioma: str = "es",
    ) -> None:
        try:
            from faster_whisper import WhisperModel  # noqa: F401
        except ImportError as e:
            raise ErrorDictado(
                "faster-whisper no está instalado. Se instala con pip install "
                "faster-whisper, o cambia el motor de dictado a vosk."
            ) from e

        self.tamano = tamano
        self.dispositivo = dispositivo
        self.tipo_calculo = tipo_calculo
        self.idioma = idioma
        self._trozos: list[bytes] = []

    def _cargar_modelo(self) -> Any:
        """Carga el modelo una vez y lo reutiliza: cargarlo tarda segundos."""
        clave = (self.tamano, self.dispositivo, self.tipo_calculo)
        if MotorFasterWhisper._modelo_cache is not None and \
                MotorFasterWhisper._clave_cache == clave:
            return MotorFasterWhisper._modelo_cache

        from faster_whisper import WhisperModel

        try:
            modelo = WhisperModel(
                self.tamano, device=self.dispositivo, compute_type=self.tipo_calculo,
            )
        except Exception as e:
            raise ErrorDictado(
                f"No se ha podido cargar el modelo {self.tamano} de whisper. "
                "La primera vez necesita internet para descargarlo."
            ) from e

        MotorFasterWhisper._modelo_cache = modelo
        MotorFasterWhisper._clave_cache = clave
        return modelo

    def iniciar(self) -> None:
        self._cargar_modelo()
        self._trozos = []

    def alimentar(self, trozo: bytes) -> str | None:
        """Whisper no da parciales: solo acumula el audio."""
        self._trozos.append(trozo)
        return None

    def finalizar(self) -> str:
        if not self._trozos:
            return ""
        audio = b"".join(self._trozos)
        self._trozos = []

        # Menos de medio segundo de audio no es una frase: es el clic de la
        # tecla. Transcribirlo daría alucinaciones ("Gracias por ver").
        if len(audio) < FRECUENCIA * 2 // 2:
            return ""

        # faster-whisper acepta un archivo o un array de numpy. Se le pasa un
        # WAV temporal: así este módulo sigue sin depender de numpy.
        import tempfile
        import wave

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as archivo:
            ruta = archivo.name
        try:
            with wave.open(ruta, "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(FRECUENCIA)
                w.writeframes(audio)

            segmentos, _info = self._cargar_modelo().transcribe(
                ruta,
                language=self.idioma,
                beam_size=5,
                vad_filter=True,        # descarta silencios y ruido de fondo
            )
            return " ".join(s.text.strip() for s in segmentos).strip()
        finally:
            try:
                os.remove(ruta)
            except OSError:
                pass

    def cerrar(self) -> None:
        self._trozos = []


class MotorWhisperRemoto:
    """Envía el audio a un servidor local de whisper y recibe el texto.

    =========================================================================
    POR QUÉ UN SERVIDOR APARTE
    =========================================================================
    `large-v3` ocupa 3 GB y tarda entre 10 y 30 segundos en cargarse. Hacer
    eso dentro del proceso de la ventana significa esperar ese tiempo al
    pulsar F1 por primera vez, y llevar 3 GB en el proceso de tkinter para
    siempre. Un servidor local (`scripts/servidor_whisper.py`) carga el
    modelo UNA vez, se queda caliente entre dictados, y puede vivir en un
    Python distinto, con CUDA, aunque VozClip sea un .exe.

    Protocolo, deliberadamente mínimo y sin dependencias:
        GET  /salud          -> {"ok": true, "modelo": "...", "dispositivo": "..."}
        POST /transcribir    -> cuerpo: WAV; respuesta: {"texto": "..."}
    =========================================================================
    """

    def __init__(self, url: str = "http://127.0.0.1:8765", limite: float = 120.0) -> None:
        self.url = url.rstrip("/")
        self.limite = limite
        self._trozos: list[bytes] = []
        self.ultima_info: dict[str, Any] = {}

    def disponible(self) -> bool:
        import json
        import urllib.request

        try:
            with urllib.request.urlopen(self.url + "/salud", timeout=2) as r:
                datos = json.loads(r.read().decode("utf-8"))
            self.ultima_info = datos
            return bool(datos.get("ok"))
        except Exception:
            return False

    def iniciar(self) -> None:
        self._trozos = []

    def alimentar(self, trozo: bytes) -> str | None:
        self._trozos.append(trozo)
        return None

    def finalizar(self) -> str:
        import io
        import json
        import urllib.error
        import urllib.request
        import wave

        if not self._trozos:
            return ""
        audio = b"".join(self._trozos)
        self._trozos = []
        if len(audio) < FRECUENCIA:      # menos de medio segundo
            return ""

        buzon = io.BytesIO()
        with wave.open(buzon, "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(FRECUENCIA)
            w.writeframes(audio)

        peticion = urllib.request.Request(
            self.url + "/transcribir",
            data=buzon.getvalue(),
            headers={"Content-Type": "audio/wav"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(peticion, timeout=self.limite) as r:
                datos = json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # El servidor SÍ ha respondido, pero con un error: es otro
            # problema distinto de "no está arrancado", y merece su mensaje.
            try:
                detalle = json.loads(e.read().decode("utf-8")).get("error", "")
            except Exception:
                detalle = f"código {e.code}"
            raise ErrorDictado(f"El servidor de whisper ha fallado: {detalle}") from e
        except Exception as e:
            raise ErrorDictado(
                "El servidor de whisper no ha respondido. "
                "Comprueba que sigue arrancado."
            ) from e

        if "error" in datos:
            raise ErrorDictado(f"El servidor de whisper ha fallado: {datos['error']}")
        return str(datos.get("texto", "")).strip()

    def cerrar(self) -> None:
        self._trozos = []


def crear_motor_reconocimiento(ajustes: dict[str, Any], modelo_vosk: Path | None) -> Any:
    """Elige el motor según `dictado.motor` del config.json.

    Devuelve (motor, aviso). `aviso` es una frase hablable si se ha tenido
    que recurrir a Vosk porque whisper no estaba disponible: la función de
    dictado no puede quedarse muda porque falte una librería opcional.
    """
    eleccion = str(ajustes.get("motor", "vosk")).lower()

    if eleccion in ("whisper-servidor", "servidor", "whisper_servidor"):
        url = str(ajustes.get("whisper_url", "http://127.0.0.1:8765"))
        motor = MotorWhisperRemoto(url)
        if motor.disponible():
            return motor, None
        aviso = (
            "El servidor de whisper no responde en " + url + ". "
            "Arráncalo con iniciar servidor whisper punto bat. "
            "Usando vosk mientras tanto."
        )
        return MotorVosk(modelo_vosk), aviso

    if eleccion in ("whisper", "faster-whisper", "faster_whisper"):
        modelo, dispositivo, calculo = resolver_whisper(ajustes)
        try:
            return MotorFasterWhisper(
                tamano=modelo, dispositivo=dispositivo, tipo_calculo=calculo,
            ), None
        except ErrorDictado as e:
            aviso = f"{e} Usando vosk mientras tanto."
            return MotorVosk(modelo_vosk), aviso

    return MotorVosk(modelo_vosk), None


class MotorDictadoFalso:
    """Reconocedor de mentira para los tests.

    Devuelve las frases que se le den, en orden, sin tocar audio.
    """

    def __init__(self, respuestas: list[str] | None = None) -> None:
        self.respuestas = list(respuestas or ["texto de prueba"])
        self.trozos_recibidos: list[bytes] = []
        self.iniciado = False
        self.cerrado = False
        self._parciales = self.respuestas[:-1] if len(self.respuestas) > 1 else []
        self._entregados = 0

    def iniciar(self) -> None:
        self.iniciado = True
        self._entregados = 0

    def alimentar(self, trozo: bytes) -> str | None:
        self.trozos_recibidos.append(trozo)
        if self._entregados < len(self._parciales):
            texto = self._parciales[self._entregados]
            self._entregados += 1
            return texto
        return None

    def finalizar(self) -> str:
        return self.respuestas[-1] if self.respuestas else ""

    def cerrar(self) -> None:
        self.cerrado = True


# ===========================================================================
# Captura de audio
# ===========================================================================
class CapturaAudio(Protocol):
    def trozos(self, parar: threading.Event) -> Iterator[bytes]: ...
    def cerrar(self) -> None: ...


def nivel_rms(audio: bytes, paso: int = 4) -> float:
    """Nivel medio de la señal, de 0 a 1, sin numpy.

    Se muestrea una de cada `paso` muestras: para decidir si hay voz o el
    micrófono está mudo no hace falta más, y así un minuto de audio se
    evalúa en milisegundos.
    """
    import array
    import math

    muestras = array.array("h")
    muestras.frombytes(audio[: len(audio) - (len(audio) % 2)])
    if not muestras:
        return 0.0
    sub = muestras[::paso]
    return math.sqrt(sum(m * m for m in sub) / len(sub)) / 32768.0


# Por debajo de esto, lo grabado es silencio: micrófono mudo, desconectado,
# o el de otro dispositivo. Es preferible avisar a transcribir la nada.
UMBRAL_SILENCIO = 0.002


class CapturaMicrofono:
    """Micrófono real, vía sounddevice.

    Se usa `RawInputStream`, que entrega bytes crudos, en vez de
    `InputStream`, que devuelve arrays de numpy. Así el programa no depende
    de numpy y el ejecutable no engorda 30 MB por nada.
    """

    def __init__(self, dispositivo: int | str | None = None) -> None:
        try:
            import sounddevice as sd
        except (ImportError, OSError) as e:
            raise ErrorDictado(
                "No se ha podido acceder al sistema de audio. "
                "El dictado no está disponible."
            ) from e

        self._sd = sd
        self._dispositivo = dispositivo
        self._flujo = None
        self.desbordamientos = 0     # bloques perdidos por no leer a tiempo

        # Comprobamos que hay micrófono ANTES de decir "escuchando": es
        # mucho mejor avisar que quedarse grabando silencio.
        try:
            dispositivos = sd.query_devices()
            entradas = [d for d in dispositivos if d.get("max_input_channels", 0) > 0]
        except Exception as e:
            raise ErrorDictado("No se ha podido consultar el micrófono.") from e

        if not entradas:
            raise ErrorDictado(
                "No hay ningún micrófono conectado. Conecta uno y vuelve a "
                "intentarlo."
            )

    def trozos(self, parar: threading.Event) -> Iterator[bytes]:
        try:
            self._flujo = self._sd.RawInputStream(
                samplerate=FRECUENCIA,
                blocksize=TAMANO_BLOQUE,
                dtype="int16",
                channels=1,
                device=self._dispositivo,
            )
            self._flujo.start()
        except Exception as e:
            raise ErrorDictado(f"No se ha podido abrir el micrófono: {e}") from e

        while not parar.is_set():
            try:
                datos, desbordado = self._flujo.read(TAMANO_BLOQUE)
            except Exception as e:
                raise ErrorDictado(f"Se ha perdido el micrófono: {e}") from e
            if desbordado:
                # Antes se tiraba el bloque entero. Eso recortaba palabras
                # sin avisar. Ahora se entrega igual (los datos que hay son
                # válidos) y se cuenta, para poder decir al usuario que el
                # equipo iba justo.
                self.desbordamientos += 1
            yield bytes(datos)

    def cerrar(self) -> None:
        if self._flujo is not None:
            try:
                self._flujo.stop()
                self._flujo.close()
            except Exception:
                pass
            self._flujo = None


class CapturaFalsa:
    """Fuente de audio de mentira: entrega trozos preparados.

    Sirve tanto para los tests como para reproducir una grabación guardada
    y comprobar el reconocimiento sin micrófono.
    """

    def __init__(self, trozos: list[bytes] | None = None, repetir: bool = False) -> None:
        self._trozos = list(trozos or [b"\x00" * (TAMANO_BLOQUE * 2)] * 3)
        self.repetir = repetir
        self.cerrada = False

    def trozos(self, parar: threading.Event) -> Iterator[bytes]:
        while True:
            for trozo in self._trozos:
                if parar.is_set():
                    return
                yield trozo
            if not self.repetir:
                return

    def cerrar(self) -> None:
        self.cerrada = True


def leer_wav(ruta: str | Path) -> list[bytes]:
    """Trocea un WAV mono de 16 kHz y 16 bits, para pruebas con audio real."""
    import wave

    with wave.open(str(ruta), "rb") as f:
        if f.getnchannels() != 1 or f.getsampwidth() != 2:
            raise ErrorDictado("El archivo debe ser WAV mono de 16 bits.")
        trozos = []
        while True:
            datos = f.readframes(TAMANO_BLOQUE)
            if not datos:
                break
            trozos.append(datos)
    return trozos


# ===========================================================================
# Localización del modelo
# ===========================================================================
def _es_windows() -> bool:
    """Separado para poder simular Windows en los tests sin tocar `os.name`,
    que rompería `pathlib` en Linux."""
    return os.name == "nt"


def carpeta_modelos() -> Path:
    """Dónde se instalan los modelos descargados por el usuario.

    En Windows se usa `C:\\Users\\Public\\VozClip\\modelos` y NO la carpeta del
    perfil. El motivo es serio: la librería de Vosk está escrita en C y abre
    los archivos con la página de códigos ANSI, así que una ruta con tilde o
    eñe (`C:\\Users\\Julián\\...`) no la puede abrir y falla con "Failed to
    create a model". `Public` es ASCII por construcción y siempre es
    escribible.
    """
    if _es_windows():
        publica = os.environ.get("PUBLIC")
        if publica:
            return Path(publica) / "VozClip" / "modelos"
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "VozClip" / "modelos"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "vozclip" / "modelos"


def carpeta_modelos_perfil() -> Path:
    """La carpeta antigua, en el perfil del usuario. Se sigue mirando por
    compatibilidad con instalaciones anteriores."""
    if _es_windows():
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "VozClip" / "modelos"
    return carpeta_modelos()


def carpeta_junto_al_programa() -> Path:
    """La carpeta `modelos` que viaja al lado del ejecutable.

    Es la que hace que el modelo pueda venir YA INCLUIDO en la descarga: el
    usuario descomprime el ZIP, hace doble clic y dicta, sin instalar nada.

    En un .exe de PyInstaller hay que mirar junto a `sys.executable`, que es
    el .exe de verdad, y NO junto a `sys._MEIPASS`, que es la carpeta
    temporal donde se descomprime el programa y desaparece al cerrarlo.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "modelos"
    # Ejecutando desde el código fuente: la raíz del proyecto
    return Path(__file__).resolve().parent.parent.parent / "modelos"


def carpetas_de_modelos(configurada: str | Path | None = None) -> list[Path]:
    """Todos los sitios donde se busca un modelo, por orden de prioridad.

    1. La ruta puesta a mano en el config.json, si la hay.
    2. La carpeta `modelos` junto al programa: el modelo que viene incluido.
    3. La carpeta de datos del usuario: el que instala `instalar_modelos.bat`.

    Buscar en varios sitios es lo que permite las dos formas de tenerlo:
    incluido en la descarga, o descargado después. Antes solo se miraba en
    la tercera, así que un modelo que viniera junto al .exe se ignoraba y
    el programa decía que faltaba.
    """
    candidatas: list[Path] = []
    if configurada:
        ruta = Path(configurada).expanduser()
        # Vale tanto la carpeta del modelo como la que lo contiene
        candidatas += [ruta, ruta.parent]
    candidatas.append(carpeta_junto_al_programa())
    candidatas.append(carpeta_modelos())
    candidatas.append(carpeta_modelos_perfil())

    vistas: set[Path] = set()
    unicas: list[Path] = []
    for c in candidatas:
        if c not in vistas:
            vistas.add(c)
            unicas.append(c)
    return unicas


def es_modelo_valido(carpeta: Path) -> bool:
    """Un modelo de Vosk lleva su modelo acústico en `am/final.mdl`.

    Comprobarlo evita dos cosas: el error críptico que suelta Vosk cuando le
    das una carpeta equivocada, y dar por bueno un modelo a medio descargar.
    Es la misma comprobación que hace `instalar_modelos.bat`.
    """
    try:
        if (carpeta / "am" / "final.mdl").exists():
            return True
        return (carpeta / "am").is_dir() and (carpeta / "conf" / "model.conf").exists()
    except OSError:
        return False


def localizar_modelo(carpeta: Path | None = None) -> Path | None:
    """Busca un modelo de Vosk válido.

    Con `carpeta`, busca solo ahí. Sin ella, recorre todos los sitios de
    `carpetas_de_modelos()`.
    """
    if carpeta is not None:
        return _buscar_en(Path(carpeta))

    for candidata in carpetas_de_modelos():
        encontrado = _buscar_en(candidata)
        if encontrado is not None:
            return encontrado
    return None


def _buscar_en(carpeta: Path) -> Path | None:
    """Mira si la carpeta ES un modelo, o si CONTIENE uno."""
    if not carpeta.exists():
        return None
    if es_modelo_valido(carpeta):
        return carpeta
    try:
        subcarpetas = sorted(p for p in carpeta.iterdir() if p.is_dir())
    except OSError:
        return None
    for sub in subcarpetas:
        if es_modelo_valido(sub):
            return sub
    return None


# ===========================================================================
# Rutas que la librería nativa pueda abrir
# ===========================================================================
# vosk hace `model_path.encode("utf-8")` y se lo pasa a la librería en C.
# En Windows, esa librería abre archivos con la página de códigos ANSI, así
# que los bytes de "Julián" en UTF-8 (Juli\xc3\xa1n) los lee como "JuliÃ¡n":
# una carpeta que no existe. Resultado: "Failed to create a model", con el
# modelo perfectamente instalado.
#
# Dos remedios, por orden:
#   1. El nombre corto 8.3 de Windows (C:\\Users\\JULIN~1\\...), que es ASCII
#      puro y apunta a la misma carpeta. No copia nada.
#   2. Si el nombre corto no está disponible (los 8.3 se pueden desactivar
#      en el disco), copiar el modelo a una carpeta ASCII y usar la copia.

def es_ascii(texto: str) -> bool:
    return all(ord(c) < 128 for c in texto)


def _ruta_corta_windows(ruta: Path) -> Path | None:
    """El nombre 8.3 de una ruta, o None si Windows no lo tiene."""
    if platform.system() != "Windows":
        return None
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        largo = kernel32.GetShortPathNameW(str(ruta), None, 0)
        if largo == 0:
            return None
        buzon = ctypes.create_unicode_buffer(largo)
        if kernel32.GetShortPathNameW(str(ruta), buzon, largo) == 0:
            return None
        corta = Path(buzon.value)
        return corta if corta.exists() else None
    except Exception:
        return None


def carpetas_seguras() -> list[Path]:
    """Sitios ASCII donde copiar un modelo si hace falta."""
    candidatas: list[Path] = []
    if _es_windows():
        for variable in ("PUBLIC", "ProgramData"):
            base = os.environ.get(variable)
            if base and es_ascii(base):
                candidatas.append(Path(base) / "VozClip" / "modelos")
        candidatas.append(Path("C:/VozClip/modelos"))
    else:
        import tempfile

        candidatas.append(Path(tempfile.gettempdir()) / "vozclip" / "modelos")
    return candidatas


def _copiar_a_carpeta_segura(modelo: Path) -> Path | None:
    """Copia el modelo a una carpeta ASCII. Si ya estaba, la reutiliza."""
    import shutil

    for carpeta in carpetas_seguras():
        destino = carpeta / modelo.name
        try:
            if es_modelo_valido(destino):
                return destino
            carpeta.mkdir(parents=True, exist_ok=True)
            if destino.exists():
                shutil.rmtree(destino, ignore_errors=True)
            shutil.copytree(modelo, destino)
            if es_modelo_valido(destino):
                return destino
        except OSError:
            continue
    return None


def ruta_segura_para_vosk(modelo: Path) -> tuple[Path, str]:
    """Devuelve (ruta_usable, explicación) para pasar a la librería nativa.

    La explicación es una frase en castellano de lo que se ha hecho, para
    el registro y el diagnóstico.
    """
    if es_ascii(str(modelo)):
        return modelo, "ruta sin acentos, se usa tal cual"

    corta = _ruta_corta_windows(modelo)
    if corta is not None and es_ascii(str(corta)):
        return corta, f"ruta con acentos; se usa el nombre corto {corta}"

    copia = _copiar_a_carpeta_segura(modelo)
    if copia is not None:
        return copia, f"ruta con acentos y sin nombre corto; copiado a {copia}"

    return modelo, "ruta con acentos y no se ha podido copiar a un sitio seguro"


# ===========================================================================
# El servicio de dictado
# ===========================================================================
class ServicioDictado:
    """Gobierna el ciclo grabar → reconocer → entregar texto.

    Avisa de todo por `notificar(evento, dato)`. Los eventos son:
        ("inicio",  None)      ha empezado a escuchar
        ("parcial", texto)     frase reconocida a mitad del dictado
        ("texto",   texto)     resultado final, listo para insertar
        ("error",   mensaje)   algo ha fallado; el mensaje se puede hablar
        ("fin",     None)      ha terminado, pase lo que pase

    Todos los avisos llegan desde el hilo de grabación, así que quien los
    reciba debe encolarlos, nunca tocar widgets directamente.
    """

    def __init__(
        self,
        notificar: Callable[[str, Any], None],
        ajustes: dict[str, Any] | None = None,
        fabrica_motor: Callable[[], MotorReconocimiento] | None = None,
        fabrica_captura: Callable[[], CapturaAudio] | None = None,
        voz: Any = None,
    ) -> None:
        self._notificar = notificar
        self._ajustes = ajustes or {}
        # Si alguien trae su propio reconocedor, el modelo de Vosk deja de
        # ser un requisito: el motor lo pone él. Comprobarlo igualmente
        # bloquearía un servicio que funciona perfectamente.
        self._motor_propio = fabrica_motor is not None
        self._fabrica_motor = fabrica_motor or self._motor_por_defecto
        self._fabrica_captura = fabrica_captura or self._captura_por_defecto
        self._voz = voz

        self._parar = threading.Event()
        self._hilo: threading.Thread | None = None
        self._parar_tras_silencio = 0.0
        self._activo = False
        self._lock = threading.Lock()

    # -- Fábricas por defecto ----------------------------------------------
    def _motor_por_defecto(self) -> MotorReconocimiento:
        motor, aviso = crear_motor_reconocimiento(
            self._ajustes, self._modelo() or self._ajustes.get("modelo") or None,
        )
        if aviso:
            self._notificar("aviso", aviso)
        return motor

    def _captura_por_defecto(self) -> CapturaAudio:
        return CapturaMicrofono(self._ajustes.get("dispositivo"))

    # -- Estado -------------------------------------------------------------
    @property
    def activo(self) -> bool:
        return self._activo

    @property
    def disponible(self) -> bool:
        """¿Se puede dictar en este ordenador ahora mismo?"""
        if not self._ajustes.get("activado", True):
            return False
        try:
            import sounddevice  # noqa: F401
            import vosk  # noqa: F401
        except Exception:
            return False
        return self._motor_propio or self._modelo() is not None

    def _modelo(self) -> Path | None:
        """El modelo que usaría este servicio, mirando la ruta configurada
        y después los sitios habituales."""
        for candidata in carpetas_de_modelos(self._ajustes.get("modelo")):
            encontrado = _buscar_en(candidata)
            if encontrado is not None:
                return encontrado
        return None

    def motivo_no_disponible(self) -> str | None:
        """Explicación en castellano de por qué no se puede dictar."""
        if not self._ajustes.get("activado", True):
            return "El dictado está desactivado en la configuración."
        try:
            import vosk  # noqa: F401
        except ImportError:
            return "Falta la librería de reconocimiento de voz."
        try:
            import sounddevice  # noqa: F401
        except (ImportError, OSError):
            return "No se ha podido acceder al sistema de audio."
        if not self._motor_propio and self._modelo() is None:
            return (
                "Falta el modelo de voz en español. Haz doble clic en "
                "instalar modelos punto bat, en la carpeta de VozClip."
            )
        return None

    # -- Control -------------------------------------------------------------
    def alternar(self) -> bool:
        """Enciende o apaga el dictado. Devuelve el estado nuevo."""
        if self._activo:
            self.detener()
            return False
        self.empezar()
        return True

    def empezar(self, parar_tras_silencio: float = 0.0) -> None:
        """Arranca la escucha.

        `parar_tras_silencio`: si es mayor que cero, la escucha termina sola
        cuando el reconocedor lleva esos segundos sin cambiar el parcial
        (es decir, el usuario ha dejado de hablar). Sirve para las órdenes
        cortas de corrección: "corrige veintiséis por treinta y seis" y ya,
        sin tener que volver a pulsar la tecla. Para el dictado normal se
        deja a cero, porque quien escribe hace pausas para pensar.
        """
        with self._lock:
            if self._activo:
                return
            self._activo = True
            self._parar_tras_silencio = parar_tras_silencio
            self._parar.clear()
            self._hilo = threading.Thread(
                target=self._grabar, name="VozClip-Dictado", daemon=True
            )
            self._hilo.start()

    def detener(self, esperar: float = 6.0) -> None:
        """Pide al hilo que pare. Con `esperar=0` no bloquea.

        Desde la ventana hay que llamar con `esperar=0`: un `join` en el
        hilo principal congela la interfaz mientras Vosk finaliza, y
        además retrasa el procesado de la cola de órdenes, que es justo
        lo que provocaba el doble disparo. El hilo pone `_activo = False`
        él mismo al terminar, y avisa con el evento "fin".
        """
        self._parar.set()
        hilo = self._hilo
        if esperar > 0 and hilo is not None and hilo.is_alive():
            hilo.join(timeout=esperar)
            self._activo = False

    def cerrar(self) -> None:
        self.detener(esperar=2.0)

    # -- El trabajo ----------------------------------------------------------
    def _grabar(self) -> None:
        motor = None
        captura = None
        try:
            # El aviso va antes que nada: el HUD se pone en rojo al instante
            self._notificar("inicio", None)

            motor = self._fabrica_motor()
            motor.iniciar()
            captura = self._fabrica_captura()

            # Esperamos a que la voz del programa termine ANTES de abrir el
            # micrófono. Si no, el propio "Escuchando" se graba y se
            # transcribe, y el guion se llena de basura.
            self._esperar_silencio()
            self._pitido(880, 90)

            energia_total = 0.0
            bloques = 0
            ultimo_parcial = ""
            ultimo_cambio = time.monotonic()
            for trozo in captura.trozos(self._parar):
                energia_total += nivel_rms(trozo)
                bloques += 1
                parcial = motor.alimentar(trozo)
                if parcial:
                    self._notificar("parcial", parcial)
                    if parcial != ultimo_parcial:
                        ultimo_parcial = parcial
                        ultimo_cambio = time.monotonic()

                # Parada automática: hay algo reconocido y lleva un rato
                # sin cambiar. El usuario ha terminado de decir la orden.
                if (
                    self._parar_tras_silencio > 0
                    and ultimo_parcial
                    and time.monotonic() - ultimo_cambio >= self._parar_tras_silencio
                ):
                    self._parar.set()

            texto = motor.finalizar()
            self._pitido(660, 90)

            # Distinguir "no ha dicho nada" de "el micrófono no capta":
            # son dos problemas distintos con dos soluciones distintas.
            nivel_medio = energia_total / bloques if bloques else 0.0
            if not texto.strip() and bloques and nivel_medio < UMBRAL_SILENCIO:
                self._notificar(
                    "error",
                    "No he captado ningún sonido. Comprueba que el micrófono "
                    "no está silenciado ni conectado a otro dispositivo.",
                )
            elif texto.strip():
                self._notificar("texto", texto.strip())
            else:
                self._notificar("error", "No he entendido nada. Prueba otra vez.")

            perdidos = getattr(captura, "desbordamientos", 0)
            if perdidos:
                self._notificar(
                    "aviso",
                    f"Se han perdido {perdidos} bloques de audio: el equipo iba justo.",
                )

        except ErrorDictado as e:
            self._notificar("error", str(e))
        except Exception as e:
            self._notificar("error", f"Fallo inesperado del dictado: {type(e).__name__}")
        finally:
            for recurso in (captura, motor):
                try:
                    if recurso is not None:
                        recurso.cerrar()
                except Exception:
                    pass
            self._activo = False
            self._notificar("fin", None)

    def _esperar_silencio(self) -> None:
        if self._voz is None:
            return
        esperar = getattr(self._voz, "esperar_silencio", None)
        if callable(esperar):
            try:
                esperar(limite=4.0)
            except Exception:
                pass

    @staticmethod
    def _pitido(frecuencia: int, milisegundos: int) -> None:
        """Un pitido corto marca el principio y el final mejor que una frase.

        Con voz habría que esperar a que termine de hablar; el pitido es
        instantáneo, y eso importa cuando estás dictando.
        """
        if platform.system() == "Windows":
            try:
                import winsound

                winsound.Beep(frecuencia, milisegundos)
                return
            except Exception:
                pass
        try:
            print("\a", end="", flush=True)
        except Exception:
            pass
