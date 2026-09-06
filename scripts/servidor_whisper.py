"""Servidor local de faster-whisper para VozClip.

=============================================================================
QUÉ HACE Y POR QUÉ EXISTE
=============================================================================
Carga el modelo de Whisper UNA vez y se queda esperando audio. VozClip le
manda cada dictado por HTTP en el puerto 8765 y recibe el texto.

Es la forma de usar `large-v3` con GPU sin que VozClip lo note: el modelo
ocupa 3 GB y tarda hasta medio minuto en cargarse, pero eso pasa aquí, una
sola vez, en un proceso aparte. VozClip sigue siendo un .exe ligero, y
puede ser la versión estándar sin nada instalado.

Sin dependencias de red: `http.server` de la biblioteca estándar. Solo
escucha en 127.0.0.1, así que nada fuera de tu ordenador puede hablar con
él.

    python scripts/servidor_whisper.py                  # auto: GPU si hay
    python scripts/servidor_whisper.py --modelo large-v3 --dispositivo cuda
    python scripts/servidor_whisper.py --puerto 9000

Protocolo:
    GET  /salud        -> {"ok": true, "modelo": "large-v3", "dispositivo": "cuda"}
    POST /transcribir  -> cuerpo: un WAV (mono, 16 bits, 16 kHz)
                          respuesta: {"texto": "...", "segundos": 1.8}
=============================================================================
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

PUERTO_POR_DEFECTO = 8765


class Transcriptor:
    """Envuelve el modelo. Separado del servidor para poder sustituirlo en
    los tests por uno falso."""

    def __init__(self, modelo: str, dispositivo: str, calculo: str, idioma: str = "es"):
        from faster_whisper import WhisperModel

        self.nombre = modelo
        self.dispositivo = dispositivo
        self.calculo = calculo
        self.idioma = idioma
        self.modelo = WhisperModel(modelo, device=dispositivo, compute_type=calculo)

    def transcribir(self, wav: bytes) -> str:
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f:
            f.write(wav)
            ruta = f.name
        try:
            segmentos, _ = self.modelo.transcribe(
                ruta,
                language=self.idioma,
                beam_size=5,
                vad_filter=True,
                condition_on_previous_text=False,   # evita bucles de alucinación
            )
            return " ".join(s.text.strip() for s in segmentos).strip()
        finally:
            Path(ruta).unlink(missing_ok=True)


def crear_manejador(transcriptor):
    """Fabrica la clase manejadora con el transcriptor ya enlazado."""

    class Manejador(BaseHTTPRequestHandler):
        def log_message(self, formato, *args):  # silencio: la consola es para lo útil
            pass

        def _responder(self, codigo: int, datos: dict) -> None:
            cuerpo = json.dumps(datos, ensure_ascii=False).encode("utf-8")
            self.send_response(codigo)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(cuerpo)))
            self.end_headers()
            self.wfile.write(cuerpo)

        def do_GET(self):
            if self.path.rstrip("/") == "/salud":
                self._responder(200, {
                    "ok": True,
                    "modelo": transcriptor.nombre,
                    "dispositivo": transcriptor.dispositivo,
                    "calculo": transcriptor.calculo,
                })
            else:
                self._responder(404, {"error": "ruta desconocida"})

        def do_POST(self):
            if self.path.rstrip("/") != "/transcribir":
                self._responder(404, {"error": "ruta desconocida"})
                return

            largo = int(self.headers.get("Content-Length", "0"))
            if largo <= 0:
                self._responder(400, {"error": "cuerpo vacío"})
                return

            wav = self.rfile.read(largo)
            if wav[:4] != b"RIFF":
                self._responder(400, {"error": "se esperaba un WAV"})
                return

            inicio = time.monotonic()
            try:
                texto = transcriptor.transcribir(wav)
            except Exception as e:
                self._responder(500, {"error": f"{type(e).__name__}: {e}"})
                return

            self._responder(200, {
                "texto": texto,
                "segundos": round(time.monotonic() - inicio, 2),
            })

    return Manejador


def servir(transcriptor, puerto: int = PUERTO_POR_DEFECTO, silencio: bool = False):
    """Arranca el servidor. Devuelve el objeto servidor (ya sirviendo en
    un hilo si `silencio`, o bloqueando si no)."""
    servidor = ThreadingHTTPServer(("127.0.0.1", puerto), crear_manejador(transcriptor))
    if silencio:
        import threading

        hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
        hilo.start()
        return servidor

    print(f"Servidor de whisper escuchando en http://127.0.0.1:{puerto}")
    print("Ctrl+C para parar.")
    try:
        servidor.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        servidor.server_close()
    return servidor


def main() -> int:
    parser = argparse.ArgumentParser(description="Servidor local de faster-whisper.")
    parser.add_argument("--modelo", default="auto", help="tiny, base, small, medium, large-v3 o auto")
    parser.add_argument("--dispositivo", default="auto", help="cpu, cuda o auto")
    parser.add_argument("--calculo", default="auto", help="int8, float16, float32 o auto")
    parser.add_argument("--puerto", type=int, default=PUERTO_POR_DEFECTO)
    parser.add_argument("--idioma", default="es")
    args = parser.parse_args()

    try:
        from vozclip.dictado import resolver_whisper
    except ImportError:
        print("No encuentro el paquete vozclip. Ejecuta esto desde la carpeta del proyecto.")
        return 1

    modelo, dispositivo, calculo = resolver_whisper({
        "whisper_modelo": args.modelo,
        "whisper_dispositivo": args.dispositivo,
        "whisper_calculo": args.calculo,
    })

    print("VozClip · servidor de whisper")
    print("=" * 56)
    print(f"Modelo: {modelo}   Dispositivo: {dispositivo}   Cálculo: {calculo}")
    if dispositivo == "cpu" and modelo.startswith("large"):
        print("AVISO: large en CPU tarda medio minuto por cada 10 s de audio.")
    print("Cargando el modelo (la primera vez lo descarga)...")

    try:
        transcriptor = Transcriptor(modelo, dispositivo, calculo, args.idioma)
    except ImportError:
        print("faster-whisper no está instalado: pip install -r requirements-whisper.txt")
        return 1
    except Exception as e:
        print(f"No se ha podido cargar el modelo: {e}")
        return 1

    print("Modelo cargado.")
    servir(transcriptor, args.puerto)
    return 0


if __name__ == "__main__":
    sys.exit(main())
