"""Descarga el modelo de voz en español y lo deja listo para usar.

Lo usa la compilación para meter el modelo DENTRO del paquete, de modo que
quien descargue VozClip lo tenga todo y no tenga que instalar nada:
descomprimir, doble clic, y a dictar.

También se puede ejecutar a mano:

    python scripts/descargar_modelo.py                  -> junto al programa
    python scripts/descargar_modelo.py --destino RUTA   -> donde se diga
    python scripts/descargar_modelo.py --usuario        -> a %APPDATA%

Devuelve 0 si el modelo queda instalado y 1 si algo falla. Si ya estaba,
no descarga nada y devuelve 0.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "src"))

URL_POR_DEFECTO = "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
TAMANO_MINIMO = 1_000_000   # menos de un mega es una página de error, no el modelo


def es_modelo_valido(carpeta: Path) -> bool:
    """Misma comprobación que hace el programa: `am/final.mdl`."""
    return (carpeta / "am" / "final.mdl").exists()


def buscar_modelo(carpeta: Path) -> Path | None:
    if not carpeta.exists():
        return None
    if es_modelo_valido(carpeta):
        return carpeta
    for sub in sorted(p for p in carpeta.iterdir() if p.is_dir()):
        if es_modelo_valido(sub):
            return sub
    return None


def descargar(url: str, destino: Path, avisar=print) -> Path:
    """Descarga y descomprime el modelo en `destino`. Devuelve su carpeta."""
    destino.mkdir(parents=True, exist_ok=True)

    ya_esta = buscar_modelo(destino)
    if ya_esta is not None:
        avisar(f"[ OK ] El modelo ya estaba en {ya_esta}")
        return ya_esta

    avisar(f"[ .. ] Descargando {url}")

    with tempfile.TemporaryDirectory() as temporal:
        temporal = Path(temporal)
        archivo = temporal / "modelo.zip"

        ultimo = [0]

        def progreso(bloques: int, tam: int, total: int) -> None:
            if total <= 0:
                return
            pct = min(100, int(bloques * tam * 100 / total))
            if pct >= ultimo[0] + 25:
                ultimo[0] = pct - (pct % 25)
                avisar(f"       {ultimo[0]}%")

        urllib.request.urlretrieve(url, archivo, reporthook=progreso)

        tamano = archivo.stat().st_size
        if tamano < TAMANO_MINIMO:
            raise RuntimeError(
                f"El archivo descargado solo ocupa {tamano} bytes: no es el "
                "modelo, probablemente sea una página de error."
            )
        avisar(f"[ OK ] Descargado: {tamano / 1024 / 1024:.1f} MB")

        avisar("[ .. ] Descomprimiendo")
        with zipfile.ZipFile(archivo) as z:
            z.extractall(temporal / "extraido")

        origen = buscar_modelo(temporal / "extraido")
        if origen is None:
            raise RuntimeError("El archivo descargado no contiene un modelo válido.")

        final = destino / origen.name
        if final.exists():
            shutil.rmtree(final, ignore_errors=True)
        shutil.move(str(origen), str(final))

    if not es_modelo_valido(final):
        raise RuntimeError("El modelo se ha copiado pero le falta am/final.mdl.")

    megas = sum(f.stat().st_size for f in final.rglob("*") if f.is_file())
    avisar(f"[ OK ] Modelo instalado en {final} ({megas / 1024 / 1024:.1f} MB)")
    return final


def main() -> int:
    parser = argparse.ArgumentParser(description="Descarga el modelo de voz en español.")
    parser.add_argument("--destino", help="Carpeta donde dejarlo.")
    parser.add_argument(
        "--usuario", action="store_true",
        help="Instalarlo en la carpeta de datos del usuario (%%APPDATA%%).",
    )
    parser.add_argument("--url", default=URL_POR_DEFECTO)
    args = parser.parse_args()

    if args.destino:
        destino = Path(args.destino).expanduser()
    elif args.usuario:
        from vozclip.dictado import carpeta_modelos

        destino = carpeta_modelos()
    else:
        destino = RAIZ / "modelos"

    print("VozClip · descarga del modelo de voz")
    print("=" * 56)
    print(f"Destino: {destino}")
    print("-" * 56)

    try:
        descargar(args.url, destino)
    except Exception as e:
        print(f"[FALLA] {e}", file=sys.stderr)
        print(
            "\nComprueba la conexión a internet. Si el problema persiste, la\n"
            "dirección del modelo puede haber cambiado: mírala en\n"
            "https://alphacephei.com/vosk/models",
            file=sys.stderr,
        )
        return 1

    print("=" * 56)
    print("Listo. VozClip encontrará este modelo al arrancar.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
