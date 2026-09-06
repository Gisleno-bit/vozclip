"""Descarga e instalación del modelo de voz para el dictado.

El modelo pequeño de español de Vosk ocupa unos 39 MB. No se puede meter en
el repositorio ni en el .exe (multiplicaría su tamaño), así que se descarga
una sola vez, la primera. A partir de ahí, el dictado funciona sin internet
para siempre.
"""

from __future__ import annotations

import shutil
import tempfile
import urllib.request
import zipfile
from pathlib import Path
from typing import Callable

from .dictado import ErrorDictado, carpeta_modelos, es_ascii, localizar_modelo

# Modelo pequeño de español. Hay uno grande (1,4 GB) mucho más preciso, pero
# para dictar guion el pequeño va sobrado y arranca en un segundo.
URL_MODELO = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
TAMANO_APROXIMADO_MB = 39


def esta_instalado() -> bool:
    return localizar_modelo() is not None


def instalar(
    url: str = URL_MODELO,
    destino: Path | None = None,
    progreso: Callable[[str], None] | None = None,
) -> Path:
    """Descarga y descomprime el modelo. Devuelve la carpeta resultante.

    `progreso` recibe frases en castellano, pensadas para decirse en voz
    alta mientras se espera: una descarga de 39 MB en silencio, sin poder
    ver una barra de progreso, es desconcertante.
    """
    avisar = progreso or (lambda _m: None)
    destino = destino or carpeta_modelos()
    if not es_ascii(str(destino)):
        # Una ruta con tildes no la puede abrir la librería en C. Mejor
        # avisarlo aquí que descubrirlo al pulsar F1.
        avisar(
            "Aviso: la carpeta de destino tiene tildes o eñes. VozClip "
            "usará una copia en una carpeta sin acentos."
        )
    destino.mkdir(parents=True, exist_ok=True)

    existente = localizar_modelo(destino)
    if existente is not None:
        avisar("El modelo de voz ya estaba instalado.")
        return existente

    avisar(
        f"Descargando el modelo de voz, unos {TAMANO_APROXIMADO_MB} megas. "
        "Solo hay que hacerlo una vez."
    )

    with tempfile.TemporaryDirectory() as temporal:
        archivo = Path(temporal) / "modelo.zip"
        try:
            _descargar(url, archivo, avisar)
        except Exception as e:
            raise ErrorDictado(
                "No se ha podido descargar el modelo de voz. "
                "Comprueba la conexión a internet e inténtalo de nuevo."
            ) from e

        avisar("Descarga terminada. Descomprimiendo.")
        try:
            with zipfile.ZipFile(archivo) as z:
                z.extractall(temporal)
        except zipfile.BadZipFile as e:
            raise ErrorDictado("El archivo descargado está dañado.") from e

        origen = _buscar_modelo_extraido(Path(temporal))
        if origen is None:
            raise ErrorDictado("El archivo descargado no contiene un modelo válido.")

        final = destino / origen.name
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        shutil.move(str(origen), str(final))

    avisar("Modelo de voz instalado. Ya puedes dictar con efe uno.")
    return final


def _descargar(url: str, destino: Path, avisar: Callable[[str], None]) -> None:
    """Descarga avisando cada 25 %, para que se pueda seguir de oído."""
    ultimo_aviso = [0]

    def informar(bloques: int, tamano_bloque: int, total: int) -> None:
        if total <= 0:
            return
        porcentaje = min(100, int(bloques * tamano_bloque * 100 / total))
        if porcentaje >= ultimo_aviso[0] + 25:
            ultimo_aviso[0] = porcentaje - (porcentaje % 25)
            avisar(f"{ultimo_aviso[0]} por ciento.")

    urllib.request.urlretrieve(url, destino, reporthook=informar)


def _buscar_modelo_extraido(carpeta: Path) -> Path | None:
    """Los zip de Vosk traen el modelo dentro de una carpeta con su nombre."""
    for candidato in sorted(carpeta.iterdir()):
        if not candidato.is_dir():
            continue
        if (candidato / "am").is_dir() or (candidato / "conf").is_dir():
            return candidato
    return None
