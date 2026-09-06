"""Tests de carga y guardado de la configuración."""

import json

from vozclip import config


def test_devuelve_defaults_si_no_existe(tmp_path):
    datos = config.cargar(tmp_path / "no_existe.json")
    assert datos["velocidad"] == 0
    assert "leer_portapapeles" in datos["atajos"]


def test_guardar_y_cargar(tmp_path):
    ruta = tmp_path / "config.json"
    datos = config.cargar(ruta)
    datos["velocidad"] = 4
    datos["voz"] = "Helena"
    config.guardar(datos, ruta)

    recargado = config.cargar(ruta)
    assert recargado["velocidad"] == 4
    assert recargado["voz"] == "Helena"


def test_json_corrupto_no_rompe(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text("{ esto no es json válido", encoding="utf-8")
    datos = config.cargar(ruta)
    assert datos["velocidad"] == 0  # ha caído a los valores por defecto


def test_config_antigua_recibe_claves_nuevas(tmp_path):
    """Si el usuario tiene un config viejo, las opciones nuevas se añaden."""
    ruta = tmp_path / "config.json"
    ruta.write_text(json.dumps({"velocidad": 7}), encoding="utf-8")
    datos = config.cargar(ruta)
    assert datos["velocidad"] == 7          # respeta lo que había
    assert datos["volumen"] == 100          # y añade lo que faltaba
    assert "salir" in datos["atajos"]


def test_atajos_personalizados_se_conservan(tmp_path):
    ruta = tmp_path / "config.json"
    ruta.write_text(
        json.dumps({"atajos": {"parar": "<ctrl>+<alt>+z"}}), encoding="utf-8"
    )
    datos = config.cargar(ruta)
    assert datos["atajos"]["parar"] == "<ctrl>+<alt>+z"
    assert datos["atajos"]["leer_portapapeles"] == "<ctrl>+<alt>+l"


def test_crear_si_no_existe(tmp_path):
    ruta = tmp_path / "sub" / "config.json"
    config.crear_si_no_existe(ruta)
    assert ruta.exists()
    contenido = json.loads(ruta.read_text(encoding="utf-8"))
    assert contenido["volumen"] == 100


def test_carpeta_config_es_absoluta():
    assert config.carpeta_config().is_absolute()
