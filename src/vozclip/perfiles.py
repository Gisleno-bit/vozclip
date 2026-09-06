"""Perfiles de configuración: guardar, cargar y compartir los ajustes.

Un perfil es un archivo JSON con todo lo que define cómo se comporta el
programa: voz, velocidad, tema, tamaño de letra, plantilla, atajos. Sirve
para tres cosas:

  * Llevarse los ajustes a otro ordenador.
  * Volver a un estado conocido si algo se descoloca.
  * Arrancar bien configurado la primera vez, sin tener que tocar nada.

Ese tercer punto es el importante. El perfil "Julián" se carga solo en el
primer arranque, así que el programa ya viene ajustado a cómo trabaja él:
alto contraste, letra grande, voz en español y su formato de novela.
"""

from __future__ import annotations

import copy
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import DEFAULTS, _fusionar, carpeta_config
from .fuentes import ErrorFuente

VERSION_PERFIL = 1


# ===========================================================================
# El perfil de Julián
# ===========================================================================
# Solo lleva lo que se aparta de los valores por defecto. Todo lo demás se
# hereda, así que cuando se añada una opción nueva al programa, este perfil
# la recibe sin tener que tocarlo.
PERFIL_JULIAN: dict[str, Any] = {
    "_nombre": "Julián",
    "_descripcion": (
        "Ajustes de trabajo de Julián: alto contraste, letra grande, "
        "voz en español y el formato de novela de su documento de estilo."
    ),
    "_version": VERSION_PERFIL,

    # --- Voz ---
    # La velocidad 2 es algo más rápida que la normal: quien escucha todo el
    # día se acostumbra enseguida y agradece no esperar.
    "velocidad": 2,
    "volumen": 100,
    "anunciar_acciones": True,

    # --- Vista ---
    # Alto contraste y letra de 20 puntos, que es el tamaño en el que la
    # botonera todavía cabe en una fila cómoda.
    "tema": "alto_contraste",
    "tamano_fuente": 20,
    "cursor_parpadea": False,

    # --- Escritura ---
    "plantilla": "novela",
    "modo": "editor",

    # --- Dictado ---
    "dictado": {
        "activado": True,
        "anunciar": True,
    },
}


def perfil_julian() -> dict[str, Any]:
    """Devuelve el perfil de Julián ya fusionado con los valores por defecto."""
    return aplicar(PERFIL_JULIAN)


# ===========================================================================
# Aplicar, exportar e importar
# ===========================================================================
def aplicar(perfil: dict[str, Any], base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Combina un perfil con una configuración base.

    Las claves que empiezan por guion bajo son metadatos del perfil (nombre,
    descripción, versión) y no son ajustes: se descartan al aplicarlo.
    """
    base = copy.deepcopy(base if base is not None else DEFAULTS)
    limpio = {k: v for k, v in perfil.items() if not k.startswith("_")}
    return _fusionar(base, limpio)


def carpeta_perfiles() -> Path:
    destino = carpeta_config() / "perfiles"
    destino.mkdir(parents=True, exist_ok=True)
    return destino


def exportar(
    ajustes: dict[str, Any],
    ruta: str | Path | None = None,
    nombre: str = "",
) -> Path:
    """Guarda los ajustes actuales como perfil.

    Sin ruta, inventa un nombre con la fecha dentro de la carpeta de
    perfiles: quien no ve la pantalla no debería tener que pelearse con un
    diálogo de guardar archivo para algo tan sencillo.
    """
    if ruta is None:
        marca = datetime.now().strftime("%Y-%m-%d_%H%M")
        ruta = carpeta_perfiles() / f"perfil_{marca}.json"

    ruta = Path(ruta).expanduser()
    ruta.parent.mkdir(parents=True, exist_ok=True)

    contenido = copy.deepcopy(ajustes)
    contenido["_nombre"] = nombre or f"Perfil del {datetime.now():%d/%m/%Y}"
    contenido["_version"] = VERSION_PERFIL

    temporal = ruta.with_suffix(".tmp")
    try:
        with open(temporal, "w", encoding="utf-8") as f:
            json.dump(contenido, f, indent=2, ensure_ascii=False)
        temporal.replace(ruta)
    except OSError as e:
        raise ErrorFuente(
            f"No he podido guardar el perfil: {e.strerror or 'error de disco'}"
        ) from e

    return ruta


def importar(ruta: str | Path, base: dict[str, Any] | None = None) -> dict[str, Any]:
    """Lee un perfil y lo devuelve ya combinado, listo para usar.

    Se valida antes de aplicarlo: un JSON con basura dentro no debe dejar el
    programa en un estado raro del que el usuario no pueda salir sin ver la
    pantalla.
    """
    ruta = Path(ruta).expanduser()

    if not ruta.exists():
        raise ErrorFuente(f"No encuentro el perfil {ruta.name}.")

    try:
        with open(ruta, encoding="utf-8") as f:
            datos = json.load(f)
    except json.JSONDecodeError as e:
        raise ErrorFuente(
            f"El archivo {ruta.name} no es un perfil válido: está mal escrito."
        ) from e
    except (OSError, UnicodeDecodeError) as e:
        raise ErrorFuente(f"No he podido leer {ruta.name}.") from e

    if not isinstance(datos, dict):
        raise ErrorFuente(f"{ruta.name} no contiene un perfil.")

    problemas = validar(datos)
    if problemas:
        raise ErrorFuente(f"El perfil tiene errores: {problemas[0]}")

    return aplicar(datos, base)


def validar(perfil: dict[str, Any]) -> list[str]:
    """Comprueba que los valores tienen sentido. Devuelve los problemas.

    Solo se revisan las claves presentes: un perfil parcial es válido, y de
    hecho es lo normal.
    """
    from .hud import TAMANO_MAXIMO, TAMANO_MINIMO, TEMAS
    from .plantillas import CATALOGO

    problemas: list[str] = []

    tema = perfil.get("tema")
    if tema is not None and tema not in TEMAS:
        problemas.append(f"el tema '{tema}' no existe")

    plantilla = perfil.get("plantilla")
    if plantilla is not None and plantilla not in CATALOGO:
        problemas.append(f"la plantilla '{plantilla}' no existe")

    modo = perfil.get("modo")
    if modo is not None and modo not in ("editor", "externo"):
        problemas.append(f"el modo '{modo}' no existe")

    tamano = perfil.get("tamano_fuente")
    if tamano is not None:
        if not isinstance(tamano, int) or not TAMANO_MINIMO <= tamano <= TAMANO_MAXIMO:
            problemas.append(
                f"el tamaño de letra debe estar entre {TAMANO_MINIMO} y {TAMANO_MAXIMO}"
            )

    velocidad = perfil.get("velocidad")
    if velocidad is not None:
        if not isinstance(velocidad, int) or not -10 <= velocidad <= 10:
            problemas.append("la velocidad debe estar entre menos diez y diez")

    volumen = perfil.get("volumen")
    if volumen is not None:
        if not isinstance(volumen, int) or not 0 <= volumen <= 100:
            problemas.append("el volumen debe estar entre cero y cien")

    atajos = perfil.get("atajos")
    if atajos is not None and not isinstance(atajos, dict):
        problemas.append("los atajos deben ser una lista de pares nombre y tecla")

    return problemas


def nombre_de(ruta: str | Path) -> str:
    """Lee solo el nombre de un archivo de perfil.

    Hace falta porque `aplicar` descarta los metadatos: el nombre no es un
    ajuste y no debe acabar en el config.json. Pero sí queremos decirlo en
    voz alta al cargarlo, así que se lee aparte.
    """
    try:
        with open(Path(ruta).expanduser(), encoding="utf-8") as f:
            datos = json.load(f)
        if isinstance(datos, dict):
            return str(datos.get("_nombre", "")) or "sin nombre"
    except Exception:
        pass
    return "sin nombre"


def describir(perfil: dict[str, Any], nombre: str = "") -> str:
    """Frase para decir en voz alta al cargar un perfil."""
    nombre = nombre or perfil.get("_nombre", "sin nombre")
    tema = perfil.get("tema", "el de siempre")
    plantilla = perfil.get("plantilla", "la de siempre")
    return (
        f"Perfil {nombre}. Tema {tema.replace('_', ' ')}, "
        f"plantilla {plantilla}, velocidad {perfil.get('velocidad', 0)}."
    )
