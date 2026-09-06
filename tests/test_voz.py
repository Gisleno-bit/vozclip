"""Tests de los motores de voz y del servicio en hilo propio."""

import time

from vozclip.voz import MotorFalso, ServicioVoz, crear_motor


# -- Motor falso ------------------------------------------------------------
def test_motor_falso_registra_lo_dicho():
    m = MotorFalso()
    m.hablar("hola")
    m.hablar("adiós")
    assert m.dicho == ["hola", "adiós"]


def test_motor_falso_ignora_texto_vacio():
    m = MotorFalso()
    m.hablar("")
    assert m.dicho == []


def test_velocidad_y_volumen_se_recortan():
    m = MotorFalso()
    m.poner_velocidad(99)
    m.poner_volumen(500)
    assert m.velocidad == 10
    assert m.volumen == 100


def test_fabrica_respeta_variable_de_entorno(monkeypatch):
    monkeypatch.setenv("VOZCLIP_MOTOR", "falso")
    assert isinstance(crear_motor(), MotorFalso)


# -- ServicioVoz: el arreglo de fondo ---------------------------------------
def _servicio():
    s = ServicioVoz(motor_forzado="falso")
    s.arrancar()
    return s


def test_el_servicio_arranca_y_expone_las_voces():
    s = _servicio()
    try:
        assert s.voces() == ["Voz de prueba A", "Voz de prueba B"]
    finally:
        s.cerrar()


def test_el_motor_se_crea_dentro_del_hilo_del_servicio():
    """El fallo de la v1 era usar el objeto COM desde otro hilo.

    Aquí comprobamos que el motor pertenece al hilo del servicio y no al
    hilo que construyó el objeto.
    """
    s = ServicioVoz(motor_forzado="falso")
    assert s._motor is None          # todavía no existe: aún no hay hilo
    s.arrancar()
    try:
        assert s._motor is not None  # lo creó el hilo, no nosotros
    finally:
        s.cerrar()


def test_hablar_desde_otro_hilo_llega_al_motor():
    """Simula lo que hace el escuchador de teclado."""
    import threading

    s = _servicio()
    try:
        hilo = threading.Thread(target=lambda: s.hablar("desde otro hilo"))
        hilo.start()
        hilo.join()
        s.esperar_silencio(limite=3)
        assert "desde otro hilo" in s._motor.dicho
    finally:
        s.cerrar()


def test_encolar_no_descarta_lo_anterior():
    s = _servicio()
    try:
        s.hablar("uno")
        s.encolar("dos")
        s.encolar("tres")
        s.esperar_silencio(limite=3)
        assert s._motor.dicho == ["uno", "dos", "tres"]
    finally:
        s.cerrar()


def test_hablar_descarta_la_cola_pendiente():
    """Lo urgente manda: un aviso nuevo no espera detrás de un texto largo."""
    s = _servicio()
    try:
        s.encolar("párrafo largo uno")
        s.encolar("párrafo largo dos")
        s.hablar("URGENTE")
        s.esperar_silencio(limite=3)
        assert "URGENTE" in s._motor.dicho
    finally:
        s.cerrar()


def test_parar_llega_al_motor():
    s = _servicio()
    try:
        s.hablar("algo")
        s.parar()
        s.esperar_silencio(limite=3)
        assert s._motor.paradas >= 1
    finally:
        s.cerrar()


def test_una_orden_que_falla_no_deja_mudo_el_servicio():
    """Regresión: en la v1 un error dejaba el programa callado para siempre."""
    s = _servicio()
    try:
        # Rompemos el motor a propósito
        def explota(_texto):
            raise RuntimeError("motor roto")

        original = s._motor.hablar
        s._motor.hablar = explota
        s.hablar("esto falla")
        time.sleep(0.3)

        # El servicio debe seguir atendiendo la cola
        s._motor.hablar = original
        s.hablar("esto sí suena")
        s.esperar_silencio(limite=3)
        assert "esto sí suena" in s._motor.dicho
    finally:
        s.cerrar()


def test_error_de_arranque_se_propaga_al_arrancar():
    """Si falta pywin32, hay que enterarse en el arranque, no en silencio."""
    import pytest

    from vozclip import voz as modvoz

    def motor_roto(_forzar=None):
        raise RuntimeError("falta pywin32")

    original = modvoz.crear_motor
    modvoz.crear_motor = motor_roto
    try:
        s = ServicioVoz()
        with pytest.raises(RuntimeError, match="pywin32"):
            s.arrancar()
    finally:
        modvoz.crear_motor = original


def test_cerrar_termina_el_hilo():
    s = _servicio()
    s.cerrar()
    time.sleep(0.2)
    assert not s._hilo.is_alive()


# -- Regresión del fallo en la CI de Windows --------------------------------
def test_no_se_toca_com_con_el_motor_falso(monkeypatch):
    """El motor falso no necesita COM.

    Antes se llamaba a CoInitialize en Windows pasara lo que pasara. Con
    doscientos tests creando servicios, ese ir y venir de apartamentos COM
    acababa en 'Windows fatal exception: code 0x80000003' al recolectar
    basura. Ahora COM solo entra en juego si el motor es SAPI5.
    """
    from vozclip import voz as modvoz

    assert modvoz.eleccion_motor("falso") == "falso"
    assert modvoz.eleccion_motor("comando") == "comando"
    assert modvoz.eleccion_motor("sapi5") == "sapi5"


def test_la_eleccion_respeta_la_variable_de_entorno(monkeypatch):
    from vozclip import voz as modvoz

    monkeypatch.setenv("VOZCLIP_MOTOR", "falso")
    assert modvoz.eleccion_motor() == "falso"


def test_la_eleccion_por_defecto_depende_del_sistema(monkeypatch):
    from vozclip import voz as modvoz

    monkeypatch.delenv("VOZCLIP_MOTOR", raising=False)
    monkeypatch.setattr(modvoz.platform, "system", lambda: "Windows")
    assert modvoz.eleccion_motor() == "sapi5"
    monkeypatch.setattr(modvoz.platform, "system", lambda: "Linux")
    assert modvoz.eleccion_motor() == "comando"


def test_un_arranque_fallido_libera_los_recursos():
    """Antes, el `return` tras fallar la creación del motor se saltaba el
    bloque de limpieza y dejaba el apartamento COM colgado."""
    import pytest as _pytest

    from vozclip import voz as modvoz

    original = modvoz.crear_motor
    modvoz.crear_motor = lambda _f=None: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        s = ServicioVoz(motor_forzado="falso")
        with _pytest.raises(RuntimeError, match="boom"):
            s.arrancar()
        time.sleep(0.2)
        assert not s._hilo.is_alive()      # el hilo termina limpiamente
        assert s._inactivo.is_set()        # y nadie se queda esperando
    finally:
        modvoz.crear_motor = original


def test_esperar_silencio_no_se_cuelga_si_el_motor_muere():
    """Si el hilo termina, `esperar_silencio` debe volver, no bloquear."""
    from vozclip import voz as modvoz

    original = modvoz.crear_motor
    modvoz.crear_motor = lambda _f=None: (_ for _ in ()).throw(RuntimeError("boom"))
    try:
        s = ServicioVoz(motor_forzado="falso")
        try:
            s.arrancar()
        except RuntimeError:
            pass
        inicio = time.monotonic()
        s.esperar_silencio(limite=3)
        assert time.monotonic() - inicio < 2.5
    finally:
        modvoz.crear_motor = original
