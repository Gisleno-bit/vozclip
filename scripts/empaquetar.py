"""Arma el paquete de entrega: el ZIP que descarga el usuario.

Antes era un bloque de PowerShell dentro de `build-windows.yml`. Aquí va
con el código: se prueba con pytest y el YAML solo lo llama.

    python scripts/empaquetar.py                 -> VozClip-Windows.zip
    python scripts/empaquetar.py --salida X.zip

Contenido:
    VozClip.exe                 el programa (sin consola)
    VozClip-Diagnostico.exe     con consola, para cuando algo falla
    LEEME.txt, GUIA_RAPIDA.txt
    instalar_en_inicio.bat      arrancar con Windows
    instalar_modelos.bat        reinstalar el modelo de voz
    modelos/                    el modelo de voz, si la compilación lo bajó

Devuelve 1 si falta algo obligatorio: un paquete a medias es peor que
ninguno, porque el usuario lo descarga confiado.
"""

from __future__ import annotations

import argparse
import shutil
import sys
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# (origen relativo a la raíz, nombre dentro del paquete, obligatorio)
CONTENIDO = [
    ("dist/VozClip.exe", "VozClip.exe", True),
    ("dist/VozClip-Diagnostico.exe", "VozClip-Diagnostico.exe", True),
    ("LEEME.txt", "LEEME.txt", True),
    ("GUIA_RAPIDA.txt", "GUIA_RAPIDA.txt", True),
    ("scripts/instalar_en_inicio.bat", "instalar_en_inicio.bat", True),
    ("scripts/instalar_modelos.bat", "instalar_modelos.bat", True),
]

CARPETA_MODELOS = "modelos"


def armar(raiz: Path, salida: Path, avisar=print) -> list[str]:
    """Construye el ZIP. Devuelve la lista de problemas (vacía si todo bien)."""
    problemas: list[str] = []
    paquete = raiz / "paquete"
    if paquete.exists():
        shutil.rmtree(paquete)
    paquete.mkdir()

    for origen_rel, nombre, obligatorio in CONTENIDO:
        origen = raiz / origen_rel
        if origen.exists():
            shutil.copy2(origen, paquete / nombre)
            avisar(f"[ OK ] {nombre}")
        elif obligatorio:
            problemas.append(f"falta {origen_rel}")
            avisar(f"[FALTA] {origen_rel}")
        else:
            avisar(f"[ -- ] {nombre} (opcional, no está)")

    modelos = raiz / CARPETA_MODELOS
    if modelos.exists() and any(modelos.rglob("final.mdl")):
        shutil.copytree(modelos, paquete / CARPETA_MODELOS)
        megas = sum(f.stat().st_size for f in modelos.rglob("*") if f.is_file()) / 1024 / 1024
        avisar(f"[ OK ] modelos/ incluido ({megas:.1f} MB): el dictado funciona nada más descomprimir")
    else:
        avisar("[AVISO] sin modelos/: el usuario tendrá que ejecutar instalar_modelos.bat")

    if problemas:
        return problemas

    if salida.exists():
        salida.unlink()
    with zipfile.ZipFile(salida, "w", zipfile.ZIP_DEFLATED) as z:
        for archivo in sorted(paquete.rglob("*")):
            if archivo.is_file():
                z.write(archivo, archivo.relative_to(paquete))

    megas = salida.stat().st_size / 1024 / 1024
    avisar(f"\nPaquete: {salida} ({megas:.1f} MB)")
    return []


def main() -> int:
    parser = argparse.ArgumentParser(description="Arma el ZIP de entrega.")
    parser.add_argument("--salida", default="VozClip-Windows.zip")
    parser.add_argument("--raiz", default=str(RAIZ))
    args = parser.parse_args()

    raiz = Path(args.raiz)
    salida = Path(args.salida)
    if not salida.is_absolute():
        salida = raiz / salida

    print("VozClip · paquete de entrega")
    print("=" * 60)
    problemas = armar(raiz, salida)
    print("=" * 60)

    if problemas:
        print("NO SE HA CREADO EL PAQUETE:")
        for p in problemas:
            print(f"  · {p}")
        return 1
    print("Paquete listo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
