"""Tests del motor faster-whisper.

No se descarga ningún modelo (harían falta cientos de MB y acceso a
Hugging Face). Se inyecta un `faster_whisper` falso en `sys.modules` que
registra lo que se le pide y devuelve segmentos preparados. Con eso se
prueba todo lo que es de VozClip: la selección del motor, el WAV que se
genera, los parámetros de la transcripción, la caché del modelo y el
fallback a Vosk cuando la librería no está.
"""

from __future__ import annotations

import sys
import types
import wave

import pytest

from vozclip import dictado


# ===========================================================================
# El faster_whisper falso
# ===========================================================================
class _Segmento:
    def __init__(self, texto):
        self.text = texto


class _ModeloFalso:
    creados: list[dict] = []
    transcripciones: list[dict] = []
    respuesta: list[str] = ["hola coma qué tal punto"]

    def __init__(self, tamano, device="cpu", compute_type="int8"):
        _ModeloFalso.creados.append(
            {"tamano": tamano, "device": device, "compute_type": compute_type}
        )

    def transcribe(self, ruta, **opciones):
        with wave.open(ruta, "rb") as w:
            info = {
                "canales": w.getnchannels(),
                "ancho": w.getsampwidth(),
                "frecuencia": w.getframerate(),
                "frames": w.getnframes(),
            }
        _ModeloFalso.transcripciones.append({"ruta": ruta, "wav": info, **opciones})
        return [_Segmento(t) for t in _ModeloFalso.respuesta], {"language": "es"}


@pytest.fixture
def whisper_falso(monkeypatch):
    modulo = types.ModuleType("faster_whisper")
    modulo.WhisperModel = _ModeloFalso
    monkeypatch.setitem(sys.modules, "faster_whisper", modulo)
    _ModeloFalso.creados.clear()
    _ModeloFalso.transcripciones.clear()
    _ModeloFalso.respuesta = ["hola coma qué tal punto"]
    dictado.MotorFasterWhisper._modelo_cache = None
    dictado.MotorFasterWhisper._clave_cache = None
    yield _ModeloFalso
    dictado.MotorFasterWhisper._modelo_cache = None
    dictado.MotorFasterWhisper._clave_cache = None


@pytest.fixture
def sin_whisper(monkeypatch):
    """Simula que la librería no está instalada."""
    monkeypatch.setitem(sys.modules, "faster_whisper", None)


def _audio(segundos: float) -> bytes:
    """Silencio de int16 a 16 kHz."""
    return b"\x00\x01" * int(dictado.FRECUENCIA * segundos)


# ===========================================================================
# El motor
# ===========================================================================
def test_sin_la_libreria_el_motor_dice_como_instalarla(sin_whisper):
    with pytest.raises(dictado.ErrorDictado, match="pip install faster-whisper"):
        dictado.MotorFasterWhisper()


def test_el_motor_carga_el_modelo_con_los_parametros(whisper_falso):
    motor = dictado.MotorFasterWhisper(tamano="base", tipo_calculo="int8")
    motor.iniciar()
    assert whisper_falso.creados == [
        {"tamano": "base", "device": "cpu", "compute_type": "int8"}
    ]


def test_el_modelo_se_carga_una_sola_vez(whisper_falso):
    """Cargarlo tarda segundos: dos dictados seguidos comparten el modelo."""
    motor = dictado.MotorFasterWhisper()
    motor.iniciar()
    motor.iniciar()
    otro = dictado.MotorFasterWhisper()
    otro.iniciar()
    assert len(whisper_falso.creados) == 1


def test_un_tamano_distinto_recarga(whisper_falso):
    dictado.MotorFasterWhisper(tamano="small").iniciar()
    dictado.MotorFasterWhisper(tamano="medium").iniciar()
    assert len(whisper_falso.creados) == 2


def test_alimentar_no_da_parciales(whisper_falso):
    """Whisper no es streaming: acumula y no dice nada hasta el final."""
    motor = dictado.MotorFasterWhisper()
    motor.iniciar()
    assert motor.alimentar(_audio(1)) is None
    assert motor.alimentar(_audio(1)) is None


def test_finalizar_genera_un_wav_correcto_y_transcribe(whisper_falso):
    motor = dictado.MotorFasterWhisper()
    motor.iniciar()
    motor.alimentar(_audio(1.5))
    motor.alimentar(_audio(1.5))

    texto = motor.finalizar()

    assert texto == "hola coma qué tal punto"
    [t] = whisper_falso.transcripciones
    assert t["wav"] == {
        "canales": 1, "ancho": 2, "frecuencia": dictado.FRECUENCIA,
        "frames": dictado.FRECUENCIA * 3,
    }
    assert t["language"] == "es"
    assert t["vad_filter"] is True


def test_el_wav_temporal_se_borra(whisper_falso):
    import os

    motor = dictado.MotorFasterWhisper()
    motor.iniciar()
    motor.alimentar(_audio(1))
    motor.finalizar()
    ruta = whisper_falso.transcripciones[0]["ruta"]
    assert not os.path.exists(ruta)


def test_varios_segmentos_se_unen(whisper_falso):
    whisper_falso.respuesta = ["  Primera frase. ", " Segunda frase.  "]
    motor = dictado.MotorFasterWhisper()
    motor.iniciar()
    motor.alimentar(_audio(2))
    assert motor.finalizar() == "Primera frase. Segunda frase."


def test_un_audio_minusculo_no_se_transcribe(whisper_falso):
    """Medio segundo es el clic de la tecla: Whisper alucinaría."""
    motor = dictado.MotorFasterWhisper()
    motor.iniciar()
    motor.alimentar(_audio(0.2))
    assert motor.finalizar() == ""
    assert whisper_falso.transcripciones == []


def test_finalizar_vacia_el_acumulador(whisper_falso):
    motor = dictado.MotorFasterWhisper()
    motor.iniciar()
    motor.alimentar(_audio(1))
    motor.finalizar()
    assert motor.finalizar() == ""       # sin audio nuevo, nada


def test_la_puntuacion_hablada_funciona_igual_con_whisper(whisper_falso):
    """El texto de Whisper pasa por el mismo `aplicar_puntuacion`."""
    motor = dictado.MotorFasterWhisper()
    motor.iniciar()
    motor.alimentar(_audio(1))
    assert dictado.aplicar_puntuacion(motor.finalizar()) == "Hola, qué tal."


# ===========================================================================
# La selección del motor y el fallback
# ===========================================================================
def test_por_defecto_se_usa_vosk(tmp_path, monkeypatch):
    monkeypatch.setattr(dictado, "localizar_modelo", lambda *a, **k: tmp_path)
    motor, aviso = dictado.crear_motor_reconocimiento({"motor": "vosk"}, tmp_path)
    assert isinstance(motor, dictado.MotorVosk)
    assert aviso is None


def test_se_puede_elegir_whisper(whisper_falso):
    motor, aviso = dictado.crear_motor_reconocimiento(
        {"motor": "whisper", "whisper_modelo": "base"}, None
    )
    assert isinstance(motor, dictado.MotorFasterWhisper)
    assert motor.tamano == "base"
    assert aviso is None


@pytest.mark.parametrize("nombre", ["whisper", "faster-whisper", "faster_whisper", "WHISPER"])
def test_se_aceptan_varios_nombres(whisper_falso, nombre):
    motor, _ = dictado.crear_motor_reconocimiento({"motor": nombre}, None)
    assert isinstance(motor, dictado.MotorFasterWhisper)


def test_sin_whisper_se_vuelve_a_vosk_y_se_avisa(sin_whisper, tmp_path):
    """Que falte una librería OPCIONAL no puede dejar el dictado mudo."""
    motor, aviso = dictado.crear_motor_reconocimiento({"motor": "whisper"}, tmp_path)
    assert isinstance(motor, dictado.MotorVosk)
    assert aviso is not None
    assert "vosk" in aviso.lower()
    assert "pip install faster-whisper" in aviso


def test_el_servicio_emite_el_aviso_del_fallback(sin_whisper, tmp_path):
    """El aviso llega al HUD por la cola de eventos, y de ahí a la voz."""
    modelo = tmp_path / "vosk"
    (modelo / "am").mkdir(parents=True)
    (modelo / "am" / "final.mdl").write_bytes(b"x")

    eventos = []
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: eventos.append((t, d)),
        ajustes={"activado": True, "motor": "whisper", "modelo": str(modelo)},
    )
    motor = servicio._motor_por_defecto()
    assert isinstance(motor, dictado.MotorVosk)
    assert any(t == "aviso" for t, _ in eventos)


def test_la_configuracion_trae_las_opciones_de_whisper():
    from vozclip import config

    d = config.DEFAULTS["dictado"]
    assert d["motor"] == "vosk"                  # el incluido, por defecto
    assert d["whisper_modelo"] == "auto"         # large-v3 con GPU, small sin
    assert d["whisper_dispositivo"] == "auto"
    assert d["whisper_calculo"] == "auto"
    assert d["whisper_url"].startswith("http://127.0.0.1")


# ===========================================================================
# GPU automática
# ===========================================================================
def test_sin_gpu_se_elige_small_en_cpu_int8(monkeypatch):
    monkeypatch.setattr(dictado, "hay_gpu_cuda", lambda: False)
    assert dictado.resolver_whisper({}) == ("small", "cpu", "int8")


def test_con_gpu_se_elige_large_v3_en_float16(monkeypatch):
    """La máxima precisión que existe, cuando el hardware lo permite."""
    monkeypatch.setattr(dictado, "hay_gpu_cuda", lambda: True)
    assert dictado.resolver_whisper({}) == ("large-v3", "cuda", "float16")


def test_los_ajustes_explicitos_mandan(monkeypatch):
    monkeypatch.setattr(dictado, "hay_gpu_cuda", lambda: True)
    resultado = dictado.resolver_whisper(
        {"whisper_modelo": "medium", "whisper_dispositivo": "cpu", "whisper_calculo": "int8"}
    )
    assert resultado == ("medium", "cpu", "int8")


def test_sin_ctranslate2_no_hay_gpu(monkeypatch):
    monkeypatch.setitem(sys.modules, "ctranslate2", None)
    assert dictado.hay_gpu_cuda() is False


# ===========================================================================
# El servidor local, levantado de verdad con un transcriptor simulado
# ===========================================================================
@pytest.fixture
def servidor():
    import importlib.util
    from pathlib import Path

    ruta = Path(__file__).resolve().parent.parent / "scripts" / "servidor_whisper.py"
    spec = importlib.util.spec_from_file_location("servidor_whisper", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)

    class TranscriptorFalso:
        nombre = "falso"
        dispositivo = "cpu"
        calculo = "int8"
        recibidos: list[bytes] = []
        respuesta = "hola coma qué tal punto"
        fallar = False

        def transcribir(self, wav: bytes) -> str:
            self.recibidos.append(wav)
            if self.fallar:
                raise RuntimeError("modelo roto")
            return self.respuesta

    transcriptor = TranscriptorFalso()
    TranscriptorFalso.recibidos = []
    srv = modulo.servir(transcriptor, puerto=0, silencio=True)
    puerto = srv.server_address[1]
    yield f"http://127.0.0.1:{puerto}", transcriptor
    srv.shutdown()
    srv.server_close()


def test_el_servidor_responde_a_salud(servidor):
    import json
    import urllib.request

    url, _ = servidor
    with urllib.request.urlopen(url + "/salud", timeout=5) as r:
        datos = json.loads(r.read())
    assert datos == {"ok": True, "modelo": "falso", "dispositivo": "cpu", "calculo": "int8"}


def test_el_motor_remoto_detecta_el_servidor(servidor):
    url, _ = servidor
    motor = dictado.MotorWhisperRemoto(url)
    assert motor.disponible() is True
    assert motor.ultima_info["modelo"] == "falso"


def test_el_motor_remoto_sin_servidor_no_esta_disponible():
    motor = dictado.MotorWhisperRemoto("http://127.0.0.1:1")     # nadie escucha
    assert motor.disponible() is False


def test_el_ciclo_completo_por_http(servidor):
    """VozClip graba, manda el WAV, recibe el texto."""
    url, transcriptor = servidor
    motor = dictado.MotorWhisperRemoto(url)
    motor.iniciar()
    motor.alimentar(_audio(1.0))
    motor.alimentar(_audio(1.0))

    assert motor.finalizar() == "hola coma qué tal punto"

    [wav] = transcriptor.recibidos
    assert wav[:4] == b"RIFF"                # un WAV de verdad
    with wave.open(__import__("io").BytesIO(wav), "rb") as w:
        assert w.getnchannels() == 1
        assert w.getframerate() == dictado.FRECUENCIA
        assert w.getnframes() == dictado.FRECUENCIA * 2


def test_el_servidor_rechaza_lo_que_no_es_wav(servidor):
    import urllib.error
    import urllib.request

    url, _ = servidor
    peticion = urllib.request.Request(url + "/transcribir", data=b"basura", method="POST")
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(peticion, timeout=5)
    assert info.value.code == 400


def test_un_fallo_del_modelo_llega_como_error_hablable(servidor):
    url, transcriptor = servidor
    transcriptor.fallar = True
    motor = dictado.MotorWhisperRemoto(url)
    motor.iniciar()
    motor.alimentar(_audio(1.0))
    with pytest.raises(dictado.ErrorDictado, match="ha fallado"):
        motor.finalizar()


def test_la_fabrica_elige_el_servidor_si_responde(servidor):
    url, _ = servidor
    motor, aviso = dictado.crear_motor_reconocimiento(
        {"motor": "whisper-servidor", "whisper_url": url}, None
    )
    assert isinstance(motor, dictado.MotorWhisperRemoto)
    assert aviso is None


def test_la_fabrica_vuelve_a_vosk_si_el_servidor_no_responde(tmp_path):
    motor, aviso = dictado.crear_motor_reconocimiento(
        {"motor": "whisper-servidor", "whisper_url": "http://127.0.0.1:1"}, tmp_path
    )
    assert isinstance(motor, dictado.MotorVosk)
    assert "no responde" in aviso
    assert "bat" in aviso


def test_el_servidor_solo_escucha_en_local(servidor):
    """Nada fuera del ordenador puede hablar con él."""
    url, _ = servidor
    assert url.startswith("http://127.0.0.1:")


# ===========================================================================
# Captura: nivel de señal y bloques perdidos
# ===========================================================================
def test_el_silencio_tiene_nivel_cero():
    assert dictado.nivel_rms(b"\x00\x00" * 8000) == 0.0


def test_una_senal_tiene_nivel():
    import math
    import struct

    tono = b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(8000))
    assert dictado.nivel_rms(tono) > dictado.UMBRAL_SILENCIO * 10


def test_un_microfono_mudo_se_distingue_de_no_decir_nada():
    """Son dos problemas con dos soluciones. Antes se confundían."""
    eventos = []
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: eventos.append((t, d)),
        ajustes={"activado": True},
        fabrica_motor=lambda: dictado.MotorDictadoFalso([""]),      # no entiende nada
        fabrica_captura=lambda: dictado.CapturaFalsa([b"\x00\x00" * 4000] * 3),  # silencio
    )
    servicio.empezar()
    import time as _t

    plazo = _t.monotonic() + 5
    while servicio.activo and _t.monotonic() < plazo:
        _t.sleep(0.02)

    errores = [d for t, d in eventos if t == "error"]
    assert errores
    assert "micrófono" in errores[0]
    assert "silenciado" in errores[0]


def test_los_bloques_perdidos_se_avisan():
    class CapturaQueSeDesborda(dictado.CapturaFalsa):
        desbordamientos = 3

    eventos = []
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: eventos.append((t, d)),
        ajustes={"activado": True},
        fabrica_motor=lambda: dictado.MotorDictadoFalso(["texto"]),
        fabrica_captura=lambda: CapturaQueSeDesborda(),
    )
    servicio.empezar()
    import time as _t

    plazo = _t.monotonic() + 5
    while servicio.activo and _t.monotonic() < plazo:
        _t.sleep(0.02)

    avisos = [d for t, d in eventos if t == "aviso"]
    assert any("3 bloques" in a for a in avisos)


# ===========================================================================
# Los archivos de instalación
# ===========================================================================
def test_requirements_whisper_existe_y_no_va_al_exe():
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    req = (raiz / "requirements-whisper.txt").read_text(encoding="utf-8")
    assert "faster-whisper" in req
    # y el requirements normal NO lo lleva: el .exe estándar no lo incluye
    normal = (raiz / "requirements.txt").read_text(encoding="utf-8")
    assert "faster-whisper" not in normal


def test_el_bat_del_servidor_existe_y_es_ascii():
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    bat = raiz / "scripts" / "iniciar_servidor_whisper.bat"
    crudo = bat.read_bytes()
    assert all(b < 128 for b in crudo)
    assert b"servidor_whisper.py" in crudo
    assert b"requirements-whisper.txt" in crudo


def test_el_servidor_es_un_script_de_la_biblioteca_estandar():
    """Sin flask, sin fastapi, sin websockets: nada que instalar aparte de
    faster-whisper."""
    import ast
    from pathlib import Path

    raiz = Path(__file__).resolve().parent.parent
    arbol = ast.parse((raiz / "scripts" / "servidor_whisper.py").read_text(encoding="utf-8"))
    importados = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            importados |= {a.name.split(".")[0] for a in nodo.names}
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            importados.add(nodo.module.split(".")[0])
    externos = importados - set(sys.stdlib_module_names) - {"vozclip", "faster_whisper"}
    assert externos == set(), f"Dependencias no previstas: {externos}"
