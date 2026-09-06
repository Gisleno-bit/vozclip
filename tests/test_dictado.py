"""Tests del dictado por voz.

No hace falta micrófono ni modelo: se usan un reconocedor y una fuente de
audio falsos. Los tests de puntuación sí ejercitan el código real, que es
donde está la lógica que más se puede romper.
"""

from __future__ import annotations

import threading
import time
import wave

import pytest

from vozclip import dictado


# ===========================================================================
# Comandos de puntuación hablada
# ===========================================================================
@pytest.mark.parametrize(
    "dicho, esperado",
    [
        ("hola coma qué tal punto", "Hola, qué tal."),
        ("raya no me lo creo punto", "—No me lo creo."),
        ("abrir interrogación quién anda ahí cerrar interrogación", "¿Quién anda ahí?"),
        ("primera línea salto de línea segunda línea", "Primera línea\nSegunda línea"),
        ("abre paréntesis en voz baja cerrar paréntesis", "(En voz baja)"),
        ("uno dos puntos dos", "Uno: dos"),
        ("frase uno punto y aparte frase dos", "Frase uno.\nFrase dos"),
        ("esto punto y coma aquello", "Esto; aquello"),
    ],
)
def test_puntuacion_hablada(dicho, esperado):
    assert dictado.aplicar_puntuacion(dicho) == esperado


def test_la_raya_de_dialogo_conserva_la_mayuscula():
    """En castellano se escribe '—No me lo creo', no '—no me lo creo'."""
    assert dictado.aplicar_puntuacion("raya vete punto") == "—Vete."


def test_una_coma_inicial_no_pone_mayuscula():
    """Regresión: antes salía ', Y sigue'."""
    assert dictado.aplicar_puntuacion("coma y sigue") == ", y sigue"


def test_sin_comandos_solo_capitaliza():
    assert dictado.aplicar_puntuacion("hola mundo") == "Hola mundo"


def test_texto_vacio():
    assert dictado.aplicar_puntuacion("") == ""
    assert dictado.formatear_para_insercion("") == ""


def test_los_comandos_largos_ganan_a_los_cortos():
    """'punto y aparte' no debe partirse en 'punto' + 'y' + 'aparte'."""
    salida = dictado.aplicar_puntuacion("fin punto y aparte")
    assert salida == "Fin."
    assert "aparte" not in salida


# ===========================================================================
# Colocación en el contexto
# ===========================================================================
def test_al_principio_de_linea_va_en_mayuscula():
    assert dictado.formatear_para_insercion("hola", "") == "Hola"


def test_a_mitad_de_frase_va_en_minuscula_y_con_espacio():
    assert dictado.formatear_para_insercion("hola", "el dice") == " hola"


def test_despues_de_un_punto_va_en_mayuscula():
    assert dictado.formatear_para_insercion("hola", "Fin.") == " Hola"


def test_no_pone_espacio_antes_de_una_coma():
    assert dictado.formatear_para_insercion("coma sigue", "algo") == ", sigue"


def test_respeta_los_nombres_propios():
    salida = dictado.formatear_para_insercion("Elena Ramos", "dice")
    assert "Elena Ramos" in salida


# ===========================================================================
# Motor falso
# ===========================================================================
def test_motor_falso_devuelve_lo_preparado():
    motor = dictado.MotorDictadoFalso(["hola mundo"])
    motor.iniciar()
    motor.alimentar(b"\x00" * 100)
    assert motor.finalizar() == "hola mundo"


def test_motor_falso_entrega_parciales():
    motor = dictado.MotorDictadoFalso(["primera frase", "segunda frase", "final"])
    motor.iniciar()
    assert motor.alimentar(b"\x00") == "primera frase"
    assert motor.alimentar(b"\x00") == "segunda frase"
    assert motor.finalizar() == "final"


def test_motor_falso_registra_el_audio():
    motor = dictado.MotorDictadoFalso()
    motor.iniciar()
    motor.alimentar(b"abc")
    motor.alimentar(b"def")
    assert motor.trozos_recibidos == [b"abc", b"def"]


# ===========================================================================
# Captura de audio
# ===========================================================================
def test_captura_falsa_entrega_los_trozos():
    captura = dictado.CapturaFalsa([b"uno", b"dos", b"tres"])
    parar = threading.Event()
    assert list(captura.trozos(parar)) == [b"uno", b"dos", b"tres"]


def test_la_captura_se_detiene_cuando_se_pide():
    captura = dictado.CapturaFalsa([b"x"] * 100, repetir=True)
    parar = threading.Event()
    recogidos = []
    for trozo in captura.trozos(parar):
        recogidos.append(trozo)
        if len(recogidos) == 5:
            parar.set()
    assert len(recogidos) == 5


def test_leer_wav_trocea_audio_real(tmp_path):
    """Con un WAV de verdad, para validar el troceado sin micrófono."""
    ruta = tmp_path / "prueba.wav"
    with wave.open(str(ruta), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(dictado.FRECUENCIA)
        f.writeframes(b"\x00\x01" * (dictado.FRECUENCIA * 2))   # 2 segundos

    trozos = dictado.leer_wav(ruta)
    assert len(trozos) > 1
    assert all(isinstance(t, bytes) for t in trozos)
    assert sum(len(t) for t in trozos) == dictado.FRECUENCIA * 2 * 2


def test_leer_wav_rechaza_estereo(tmp_path):
    ruta = tmp_path / "estereo.wav"
    with wave.open(str(ruta), "wb") as f:
        f.setnchannels(2)
        f.setsampwidth(2)
        f.setframerate(dictado.FRECUENCIA)
        f.writeframes(b"\x00\x01" * 100)

    with pytest.raises(dictado.ErrorDictado, match="mono"):
        dictado.leer_wav(ruta)


# ===========================================================================
# El servicio completo
# ===========================================================================
def _servicio(respuestas=None, trozos=None, ajustes=None, continuo=False):
    """`continuo=True` imita un micrófono real: no deja de dar audio hasta
    que se le dice que pare. Sin eso, la captura falsa se agota sola y el
    dictado termina antes de que el test pueda pararlo."""
    eventos = []
    servicio = dictado.ServicioDictado(
        notificar=lambda tipo, dato: eventos.append((tipo, dato)),
        ajustes=ajustes if ajustes is not None else {"activado": True, "modelo": "x"},
        fabrica_motor=lambda: dictado.MotorDictadoFalso(respuestas or ["hola mundo"]),
        fabrica_captura=lambda: dictado.CapturaFalsa(trozos, repetir=continuo),
    )
    return servicio, eventos


def _esperar(servicio, limite=5.0):
    plazo = time.monotonic() + limite
    while servicio.activo and time.monotonic() < plazo:
        time.sleep(0.02)


def test_el_dictado_entrega_el_texto():
    servicio, eventos = _servicio(["esto es una prueba"])
    servicio.empezar()
    _esperar(servicio)

    tipos = [t for t, _ in eventos]
    assert "inicio" in tipos
    assert "texto" in tipos
    assert "fin" in tipos

    texto = next(d for t, d in eventos if t == "texto")
    assert texto == "esto es una prueba"


def test_el_aviso_de_inicio_llega_el_primero():
    """El HUD tiene que ponerse en rojo antes de grabar nada."""
    servicio, eventos = _servicio()
    servicio.empezar()
    _esperar(servicio)
    assert eventos[0][0] == "inicio"


def test_el_fin_llega_siempre_el_ultimo():
    servicio, eventos = _servicio()
    servicio.empezar()
    _esperar(servicio)
    assert eventos[-1][0] == "fin"


def test_los_parciales_se_notifican():
    servicio, eventos = _servicio(["primera", "segunda", "final"])
    servicio.empezar()
    _esperar(servicio)
    parciales = [d for t, d in eventos if t == "parcial"]
    assert "primera" in parciales


def test_alternar_enciende_y_apaga():
    servicio, _ = _servicio(trozos=[b"\x00" * 100], continuo=True)
    assert servicio.alternar() is True
    time.sleep(0.05)
    assert servicio.alternar() is False
    _esperar(servicio)
    assert not servicio.activo


def test_detener_corta_la_grabacion():
    servicio, eventos = _servicio(trozos=[b"\x00" * 100], continuo=True)
    servicio.empezar()
    time.sleep(0.1)
    servicio.detener()
    assert not servicio.activo
    assert any(t == "fin" for t, _ in eventos)


def test_empezar_dos_veces_no_lanza_dos_hilos():
    servicio, _ = _servicio(trozos=[b"\x00"], continuo=True)
    servicio.empezar()
    hilo = servicio._hilo
    servicio.empezar()
    assert servicio._hilo is hilo
    servicio.detener()


def test_si_no_se_entiende_nada_avisa():
    """Hay sonido, pero el reconocedor no saca nada: 'no he entendido'.
    Distinto de grabar silencio, que es 'micrófono mudo'."""
    import math
    import struct

    con_voz = b"".join(struct.pack("<h", int(8000 * math.sin(i / 10))) for i in range(4000))
    servicio, eventos = _servicio([""], trozos=[con_voz] * 3)
    servicio.empezar()
    _esperar(servicio)
    errores = [d for t, d in eventos if t == "error"]
    assert errores
    assert "No he entendido" in errores[0]


def test_un_fallo_del_motor_se_convierte_en_aviso_hablado():
    """Nada de trazas: un mensaje en castellano que se pueda decir."""

    def motor_roto():
        raise dictado.ErrorDictado("No encuentro el modelo de voz en español.")

    eventos = []
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: eventos.append((t, d)),
        ajustes={"activado": True},
        fabrica_motor=motor_roto,
        fabrica_captura=lambda: dictado.CapturaFalsa(),
    )
    servicio.empezar()
    _esperar(servicio)

    errores = [d for t, d in eventos if t == "error"]
    assert errores == ["No encuentro el modelo de voz en español."]
    assert eventos[-1][0] == "fin"      # el ciclo se cierra igualmente


def test_un_fallo_inesperado_no_deja_el_servicio_colgado():
    def motor_explosivo():
        raise ValueError("algo raro")

    eventos = []
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: eventos.append((t, d)),
        ajustes={"activado": True},
        fabrica_motor=motor_explosivo,
        fabrica_captura=lambda: dictado.CapturaFalsa(),
    )
    servicio.empezar()
    _esperar(servicio)

    assert not servicio.activo
    assert any(t == "error" for t, _ in eventos)


def test_se_cierran_los_recursos_aunque_falle():
    captura = dictado.CapturaFalsa()
    motor = dictado.MotorDictadoFalso()
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: None,
        ajustes={"activado": True},
        fabrica_motor=lambda: motor,
        fabrica_captura=lambda: captura,
    )
    servicio.empezar()
    _esperar(servicio)
    assert captura.cerrada
    assert motor.cerrado


def test_se_espera_a_que_la_voz_calle_antes_de_grabar():
    """Si no, el programa graba su propio 'Escuchando' y lo transcribe."""

    class VozSimulada:
        def __init__(self):
            self.esperas = 0

        def esperar_silencio(self, limite=0):
            self.esperas += 1

    voz = VozSimulada()
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: None,
        ajustes={"activado": True},
        fabrica_motor=lambda: dictado.MotorDictadoFalso(),
        fabrica_captura=lambda: dictado.CapturaFalsa(),
        voz=voz,
    )
    servicio.empezar()
    _esperar(servicio)
    assert voz.esperas == 1


# ===========================================================================
# Disponibilidad
# ===========================================================================
def test_desactivado_en_la_configuracion():
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: None, ajustes={"activado": False}
    )
    assert servicio.disponible is False
    assert "desactivado" in servicio.motivo_no_disponible()


def test_el_motivo_es_una_frase_hablable():
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: None, ajustes={"activado": True}
    )
    motivo = servicio.motivo_no_disponible()
    if motivo is not None:
        assert motivo[0].isupper()
        assert motivo.endswith(".")


# ===========================================================================
# Localización del modelo
# ===========================================================================
def test_no_hay_modelo_en_carpeta_vacia(tmp_path):
    assert dictado.localizar_modelo(tmp_path) is None


def test_carpeta_inexistente(tmp_path):
    assert dictado.localizar_modelo(tmp_path / "no_existe") is None


def test_encuentra_un_modelo_por_su_estructura(tmp_path):
    modelo = tmp_path / "vosk-model-small-es"
    (modelo / "am").mkdir(parents=True)
    (modelo / "am" / "final.mdl").write_bytes(b"fingido")
    assert dictado.localizar_modelo(tmp_path) == modelo


def test_ignora_carpetas_que_no_son_modelos(tmp_path):
    (tmp_path / "descargas").mkdir()
    (tmp_path / "descargas" / "algo.txt").write_text("nada")
    assert dictado.localizar_modelo(tmp_path) is None


def test_la_carpeta_de_modelos_es_absoluta():
    assert dictado.carpeta_modelos().is_absolute()


# ===========================================================================
# Vosk: caminos de error sin modelo instalado
# ===========================================================================
def test_vosk_sin_modelo_da_un_mensaje_util(tmp_path, monkeypatch):
    monkeypatch.setattr(dictado, "localizar_modelo", lambda *a, **k: None)
    with pytest.raises(dictado.ErrorDictado) as excepcion:
        dictado.MotorVosk()
    mensaje = str(excepcion.value)
    assert "modelo" in mensaje.lower()
    assert "una vez" in mensaje       # explica que es una sola vez


def test_vosk_con_ruta_inventada(tmp_path):
    with pytest.raises(dictado.ErrorDictado):
        dictado.MotorVosk(tmp_path / "modelo_que_no_existe")


# ===========================================================================
# El modelo: ruta configurada y motor propio
# ===========================================================================
def test_la_ruta_configurada_se_tiene_en_cuenta(tmp_path, monkeypatch):
    """Regresión: al añadir la búsqueda en varios sitios, la ruta puesta a
    mano en el config.json dejó de mirarse."""
    modelo = tmp_path / "mi-modelo"
    (modelo / "am").mkdir(parents=True)
    (modelo / "am" / "final.mdl").write_bytes(b"fingido")

    monkeypatch.setattr(dictado, "carpeta_junto_al_programa", lambda: tmp_path / "no")
    monkeypatch.setattr(dictado, "carpeta_modelos", lambda: tmp_path / "tampoco")

    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: None,
        ajustes={"activado": True, "modelo": str(modelo)},
    )
    assert servicio._modelo() == modelo


def test_con_motor_propio_no_hace_falta_modelo():
    """Si alguien trae su propio reconocedor, exigir el modelo de Vosk
    bloquearía un servicio que funciona."""
    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: None,
        ajustes={"activado": True},
        fabrica_motor=lambda: dictado.MotorDictadoFalso(),
        fabrica_captura=lambda: dictado.CapturaFalsa(),
    )
    assert servicio.motivo_no_disponible() is None
    assert servicio.disponible is True


def test_sin_modelo_y_sin_motor_propio_avisa(tmp_path, monkeypatch):
    monkeypatch.setattr(dictado, "carpeta_junto_al_programa", lambda: tmp_path / "a")
    monkeypatch.setattr(dictado, "carpeta_modelos", lambda: tmp_path / "b")

    servicio = dictado.ServicioDictado(
        notificar=lambda t, d: None, ajustes={"activado": True}
    )
    motivo = servicio.motivo_no_disponible()
    if motivo is not None:      # depende de si vosk está instalado
        assert "modelo" in motivo.lower()
        assert "bat" in motivo.lower()      # dice QUÉ hacer, no solo qué falta


# ===========================================================================
# "Failed to create a model": rutas con tildes
# ===========================================================================
def _modelo_en(carpeta):
    modelo = carpeta / "vosk-model-small-es-0.42"
    (modelo / "am").mkdir(parents=True)
    (modelo / "am" / "final.mdl").write_bytes(b"x" * 1000)
    (modelo / "conf").mkdir()
    (modelo / "conf" / "model.conf").write_text("fingido")
    return modelo


def test_es_ascii():
    assert dictado.es_ascii(r"C:\Users\Public\VozClip") is True
    assert dictado.es_ascii(r"C:\Users\Julián\VozClip") is False
    assert dictado.es_ascii("año") is False


def test_una_ruta_sin_acentos_se_usa_tal_cual(tmp_path):
    modelo = _modelo_en(tmp_path / "sin_acentos")
    usable, motivo = dictado.ruta_segura_para_vosk(modelo)
    assert usable == modelo
    assert "tal cual" in motivo


def test_una_ruta_con_tilde_se_copia_a_un_sitio_ascii(tmp_path, monkeypatch):
    """El caso de Julián. vosk envía la ruta en UTF-8 y la librería en C la
    lee con la página de códigos ANSI: 'Julián' se convierte en 'JuliÃ¡n',
    una carpeta que no existe, y sale 'Failed to create a model'."""
    modelo = _modelo_en(tmp_path / "Julián" / "modelos")
    segura = tmp_path / "Public" / "VozClip" / "modelos"
    monkeypatch.setattr(dictado, "carpetas_seguras", lambda: [segura])
    monkeypatch.setattr(dictado, "_ruta_corta_windows", lambda _r: None)

    usable, motivo = dictado.ruta_segura_para_vosk(modelo)

    assert dictado.es_ascii(str(usable))
    assert dictado.es_modelo_valido(usable)
    assert usable.parent == segura
    assert "copiado" in motivo


def test_la_copia_se_reutiliza(tmp_path, monkeypatch):
    """Son 50 MB: se copian una vez, no en cada dictado."""
    modelo = _modelo_en(tmp_path / "Julián" / "modelos")
    segura = tmp_path / "Public"
    monkeypatch.setattr(dictado, "carpetas_seguras", lambda: [segura])
    monkeypatch.setattr(dictado, "_ruta_corta_windows", lambda _r: None)

    primera, _ = dictado.ruta_segura_para_vosk(modelo)
    marca = primera / "am" / "final.mdl"
    antes = marca.stat().st_mtime_ns

    segunda, motivo = dictado.ruta_segura_para_vosk(modelo)
    assert segunda == primera
    assert marca.stat().st_mtime_ns == antes       # no se ha vuelto a copiar


def test_el_nombre_corto_de_windows_evita_la_copia(tmp_path, monkeypatch):
    """Cuando Windows tiene nombres 8.3, se usan: C:\\Users\\JULIN~1\\...
    apunta a la misma carpeta y es ASCII. No hace falta copiar nada."""
    modelo = _modelo_en(tmp_path / "Julián" / "modelos")
    corta = tmp_path / "JULIN~1" / "modelos" / "vosk-model-small-es-0.42"
    monkeypatch.setattr(dictado, "_ruta_corta_windows", lambda _r: corta)

    copiado = []
    monkeypatch.setattr(dictado, "_copiar_a_carpeta_segura",
                        lambda _m: copiado.append(1))

    usable, motivo = dictado.ruta_segura_para_vosk(modelo)
    assert usable == corta
    assert "nombre corto" in motivo
    assert not copiado


def test_si_nada_funciona_se_devuelve_la_original_y_se_explica(tmp_path, monkeypatch):
    modelo = _modelo_en(tmp_path / "Julián")
    monkeypatch.setattr(dictado, "_ruta_corta_windows", lambda _r: None)
    monkeypatch.setattr(dictado, "carpetas_seguras", lambda: [])

    usable, motivo = dictado.ruta_segura_para_vosk(modelo)
    assert usable == modelo
    assert "no se ha podido" in motivo


def test_las_carpetas_seguras_son_ascii():
    for carpeta in dictado.carpetas_seguras():
        assert dictado.es_ascii(str(carpeta)), carpeta


def test_en_windows_la_carpeta_de_modelos_es_public(monkeypatch):
    """No el perfil del usuario, que puede llevar tilde."""
    monkeypatch.setattr(dictado, "_es_windows", lambda: True)
    monkeypatch.setenv("PUBLIC", r"C:\Users\Public")
    monkeypatch.setenv("APPDATA", r"C:\Users\Julián\AppData\Roaming")
    carpeta = dictado.carpeta_modelos()
    assert str(carpeta).startswith(r"C:\Users\Public")
    assert dictado.es_ascii(str(carpeta))


def test_se_sigue_mirando_en_el_perfil_por_compatibilidad(monkeypatch):
    monkeypatch.setattr(dictado, "_es_windows", lambda: True)
    monkeypatch.setenv("PUBLIC", r"C:\Users\Public")
    monkeypatch.setenv("APPDATA", r"C:\Users\Julián\AppData\Roaming")
    carpetas = [str(c) for c in dictado.carpetas_de_modelos()]
    assert any("Public" in c for c in carpetas)
    assert any("AppData" in c for c in carpetas)


def test_el_error_de_vosk_se_traduce_a_algo_util(tmp_path, monkeypatch):
    """Nada de 'Failed to create a model': una frase que diga qué pasa y
    qué hacer, hablable."""
    pytest.importorskip("vosk")
    modelo = _modelo_en(tmp_path / "Julián")
    monkeypatch.setattr(dictado, "ruta_segura_para_vosk",
                        lambda m: (m, "sin remedio"))

    class ModeloQueFalla:
        def __init__(self, _ruta):
            raise Exception("Failed to create a model")

    import vosk
    monkeypatch.setattr(vosk, "Model", ModeloQueFalla)
    dictado.MotorVosk._modelo_cache = None

    motor = dictado.MotorVosk(modelo)
    with pytest.raises(dictado.ErrorDictado) as info:
        motor._cargar_modelo()

    mensaje = str(info.value)
    assert "Failed" not in mensaje
    assert "tildes" in mensaje
    assert "bat" in mensaje
