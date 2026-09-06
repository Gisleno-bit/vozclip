"""Configuración de VozClip.

Guarda los ajustes en un JSON sencillo dentro de la carpeta de datos del
usuario (en Windows: %APPDATA%\\VozClip\\config.json).

Todo se puede editar a mano con el Bloc de notas: es un fichero de texto
plano, así que tu amigo puede cambiar la velocidad o los atajos sin
necesidad de tocar código.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Valores por defecto
# ---------------------------------------------------------------------------
# Los atajos usan la sintaxis de pynput: <ctrl>, <alt>, <shift>, <cmd>,
# <up>, <down>, <space>, <f1>... y letras sueltas.
#
# IMPORTANTE: se han elegido combinaciones con Ctrl+Alt porque NVDA y JAWS
# reservan Insert y Bloq Mayús como "tecla del lector". Así no chocan.
DEFAULTS: dict[str, Any] = {
    "voz": None,          # None = voz por defecto del sistema. Ej: "Helena"
    "velocidad": 0,       # SAPI5: de -10 (muy lenta) a 10 (muy rápida)
    "volumen": 100,       # 0 a 100
    "anunciar_acciones": True,   # confirma por voz cada acción
    "eco_teclado": False,        # decir cada palabra al terminar de escribirla
    "max_caracteres": 200000,    # tope de seguridad al leer ficheros
    "plantilla": "novela",       # el formato propio de Julián
    "modo": "editor",            # "editor" (interno) o "externo" (otra app)
    "carpeta_guiones": "",       # vacío = Documentos/VozClip
    "dictado": {
        "activado": True,
        # "vosk" (incluido), "whisper" (en el mismo proceso) o
        # "whisper-servidor" (proceso aparte con el modelo cargado; ver README)
        "motor": "vosk",
        "whisper_modelo": "auto",        # auto = large-v3 con GPU, small en CPU
        "whisper_dispositivo": "auto",   # auto = cuda si hay, si no cpu
        "whisper_calculo": "auto",       # auto = float16 en GPU, int8 en CPU
        "whisper_url": "http://127.0.0.1:8765",
        "modelo": "",          # vacío = buscar en la carpeta de modelos
        "dispositivo": None,   # None = micrófono por defecto del sistema
        "anunciar": True,      # decir "Escuchando" además del pitido
        # Segundos de silencio tras lo dicho para terminar el dictado solo.
        # Cero = manual (F1 otra vez). Quien escribe hace pausas para pensar;
        # si se prefiere que pare solo, 2 o 3 segundos van bien.
        "parar_tras_silencio": 0,
    },
    "correccion": {
        "recordatorio": True,      # tras dictar, recordar que existe efe nueve
        # "directo": F9, "cambia casa por cosa", F9. Una escucha.
        # "numerado": F9 numera el párrafo, pide el número y luego la nueva.
        "modo": "directo",
        # Tras decir la orden, segundos de silencio para aplicarla sola.
        # Cero = hay que volver a pulsar F9.
        "parar_tras_silencio": 1.5,
    },
    # --- Aspecto y accesibilidad ---------------------------------------
    "tema": "oscuro",          # "oscuro", "alto_contraste" o "claro"
    "fuente": "Consolas",      # monoespaciada: las sangrías quedan alineadas
    "tamano_fuente": 16,       # se ajusta con Ctrl+Alt+más y Ctrl+Alt+menos
    "solo_voz": False,         # ventana mínima, todo por teclado y voz
    "cursor_parpadea": False,  # un cursor que parpadea cansa la vista
    "atajos": {
        # --- Dictado ---
        "dictar": "<f1>",
        # --- Los cinco comandos de todos los días, en F1 a F5 ---
        # Una sola tecla, sin modificadores: son los que más se usan y
        # tienen que poder pulsarse sin pensar.
        "nuevo_parrafo": "<f2>",
        "nuevo_dialogo": "<f3>",
        "leer_ultimo_parrafo": "<f4>",
        "leer_texto_entero": "<f5>",
        "corregir": "<f9>",
        "cancelar_correccion": "<esc>",
        # --- Escritura ---
        "insertar_plantilla": "<ctrl>+<alt>+g",
        "cambiar_plantilla": "<ctrl>+<alt>+n",
        "aplicar_sangria": "<ctrl>+<alt>+i",
        "quitar_sangria": "<ctrl>+<alt>+<shift>+i",
        "siguiente_linea": "<ctrl>+<alt>+<enter>",
        "siguiente_marca": "<ctrl>+<alt>+t",
        # --- Archivos ---
        "importar": "<ctrl>+<alt>+o",
        "exportar": "<ctrl>+<alt>+e",
        "guardar": "<ctrl>+<alt>+d",
        "guardar_como": "<ctrl>+<alt>+s",
        "exportar_word": "<ctrl>+<alt>+<shift>+e",
        "exportar_libreoffice": "<ctrl>+<alt>+<shift>+l",
        # --- Configuración ---
        "importar_config": "<ctrl>+<alt>+u",
        "exportar_config": "<ctrl>+<alt>+y",
        "perfil_julian": "<ctrl>+<alt>+<shift>+j",
        # --- Lectura (jota, ka, ele y a, juntas en el teclado) ---
        "leer_linea": "<ctrl>+<alt>+j",
        "leer_seleccion": "<ctrl>+<alt>+k",
        "leer_portapapeles": "<ctrl>+<alt>+l",
        "leer_todo": "<ctrl>+<alt>+a",
        "pausar_reanudar": "<ctrl>+<alt>+p",
        "parar": "<ctrl>+<alt>+x",
        # --- Vista y accesibilidad ---
        "alto_contraste": "<ctrl>+<alt>+c",
        "letra_mas_grande": "<ctrl>+<alt>+<plus>",
        "letra_mas_pequena": "<ctrl>+<alt>+<minus>",
        "modo_solo_voz": "<ctrl>+<alt>+z",
        # --- Voz y navegación ---
        "mas_rapido": "<ctrl>+<alt>+<up>",
        "mas_lento": "<ctrl>+<alt>+<down>",
        "siguiente_voz": "<ctrl>+<alt>+v",
        "cambiar_modo": "<ctrl>+<alt>+m",
        "donde_estoy": "<ctrl>+<alt>+w",
        "ayuda": "<ctrl>+<alt>+h",
        "salir": "<ctrl>+<alt>+q",
    },
}


def carpeta_config() -> Path:
    """Devuelve la carpeta donde vive la configuración, según el sistema."""
    if os.name == "nt":  # Windows
        base = os.environ.get("APPDATA") or str(Path.home())
        return Path(base) / "VozClip"
    # Linux / macOS
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "vozclip"


def ruta_config() -> Path:
    return carpeta_config() / "config.json"


def _fusionar(base: dict, encima: dict) -> dict:
    """Mezcla dos diccionarios en profundidad, sin perder claves nuevas.

    Así, cuando en el futuro añadas una opción a DEFAULTS, los usuarios que
    ya tengan un config.json antiguo la reciben automáticamente.
    """
    resultado = copy.deepcopy(base)
    for clave, valor in encima.items():
        if isinstance(valor, dict) and isinstance(resultado.get(clave), dict):
            resultado[clave] = _fusionar(resultado[clave], valor)
        else:
            resultado[clave] = valor
    return resultado


def cargar(ruta: Path | None = None) -> dict[str, Any]:
    """Carga la configuración. Si no existe o está corrupta, usa los valores
    por defecto (nunca lanza excepción: para un usuario ciego, que el programa
    arranque siempre es más importante que avisar de un JSON mal escrito)."""
    ruta = ruta or ruta_config()
    if not ruta.exists():
        return copy.deepcopy(DEFAULTS)
    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
        if not isinstance(datos, dict):
            return copy.deepcopy(DEFAULTS)
        return _fusionar(DEFAULTS, datos)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return copy.deepcopy(DEFAULTS)


def guardar(datos: dict[str, Any], ruta: Path | None = None) -> Path:
    """Escribe la configuración en disco, creando la carpeta si hace falta."""
    ruta = ruta or ruta_config()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    # Escritura atómica: primero a un temporal, luego se renombra.
    temporal = ruta.with_suffix(".tmp")
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(datos, f, indent=2, ensure_ascii=False)
    temporal.replace(ruta)
    return ruta


def crear_si_no_existe(ruta: Path | None = None) -> Path:
    """Crea el config.json la primera vez, con el perfil de Julián.

    Arrancar con los valores desnudos significaría letra pequeña, tema
    oscuro y velocidad neutra: usable, pero no lo que él necesita. Con el
    perfil cargado de salida, el programa ya viene bien ajustado y no hay
    que configurar nada a ciegas.
    """
    ruta = ruta or ruta_config()
    if ruta.exists():
        return ruta

    try:
        from .perfiles import perfil_julian

        guardar(perfil_julian(), ruta)
    except Exception:
        # Si el perfil fallara por lo que sea, arrancar con los valores por
        # defecto es infinitamente mejor que no arrancar.
        guardar(copy.deepcopy(DEFAULTS), ruta)
    return ruta


def carpeta_guiones(ajustes: dict[str, Any] | None = None) -> Path:
    """Carpeta donde se guardan los guiones. Por defecto, Documentos/VozClip."""
    if ajustes and ajustes.get("carpeta_guiones"):
        destino = Path(ajustes["carpeta_guiones"]).expanduser()
    else:
        documentos = Path.home() / "Documents"
        if not documentos.exists():
            documentos = Path.home() / "Documentos"
        if not documentos.exists():
            documentos = Path.home()
        destino = documentos / "VozClip"
    destino.mkdir(parents=True, exist_ok=True)
    return destino
