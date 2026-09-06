"""Verifica un ejecutable de VozClip ya compilado.

=============================================================================
POR QUÉ ESTO ES UN SCRIPT Y NO UN BLOQUE DE POWERSHELL EN EL WORKFLOW
=============================================================================
Esta lógica vivía dentro de `build-windows.yml`. Cada vez que cambiaba (una
marca nueva, una codificación, un caso más) había que volver a subir el
YAML, y como `.github/` es una carpeta oculta que las subidas a mano se
saltan, el repositorio se quedaba con la versión vieja y la CI fallaba con
un mensaje que no explicaba nada.

Aquí, la lógica va con el código: se sube con el resto, se prueba con
pytest, y el YAML se limita a una línea:

    python scripts/verificar_binario.py dist/VozClip-Diagnostico.exe dist/VozClip.exe

Comprueba tres cosas:
  1. El autotest del ejecutable devuelve 0.
  2. Imprime todas las marcas obligatorias (VOZCLIP_*=OK). Se leen en
     ASCII puro, así que da igual la página de códigos de la consola.
  3. El ejecutable principal, si se indica, es de tipo ventana (subsistema
     PE = 2) y no de consola (= 3).
=============================================================================
"""

from __future__ import annotations

import struct
import subprocess
import sys
from pathlib import Path

# Las marcas que el autotest DEBE emitir. Añadir una aquí es todo lo que
# hace falta para que la CI la exija: no se toca el YAML.
MARCAS_OBLIGATORIAS = [
    "VOZCLIP_RESULTADO=OK",            # veredicto global
    "VOZCLIP_TKINTER=OK",              # Tcl/Tk viaja dentro del .exe
    "VOZCLIP_VOZ=OK",                  # el hilo de voz arranca
    "VOZCLIP_HUD=OK",                  # la ventana se construye
    "VOZCLIP_BOTONES=OK",
    "VOZCLIP_TEMAS=OK",                # los tres temas se aplican
    "VOZCLIP_IMPORTAR=OK",             # importar respeta las sangrías
    "VOZCLIP_ODT=OK",                  # exportar a LibreOffice
    "VOZCLIP_GUARDADO=OK",
    "VOZCLIP_DICTADO_EMPAQUETADO=OK",  # libvosk y PortAudio dentro
    "VOZCLIP_CORRECCION=OK",           # corregir por voz
]

SUBSISTEMA_VENTANA = 2
SUBSISTEMA_CONSOLA = 3


# ---------------------------------------------------------------------------
# Piezas, cada una probable por separado
# ---------------------------------------------------------------------------
def extraer_marcas(salida: bytes) -> dict[str, str]:
    """Saca las líneas VOZCLIP_X=Y de la salida cruda del autotest.

    Se decodifica con `errors="replace"`: los acentos de la salida bonita
    pueden llegar destrozados según la consola, pero las marcas son ASCII y
    sobreviven a cualquier codificación.
    """
    texto = salida.decode("utf-8", errors="replace")
    marcas: dict[str, str] = {}
    for linea in texto.splitlines():
        linea = linea.strip()
        if linea.startswith("VOZCLIP_") and "=" in linea:
            clave, valor = linea.split("=", 1)
            marcas[clave] = valor.strip()
    return marcas


def marcas_que_faltan(marcas: dict[str, str]) -> list[str]:
    faltan = []
    for obligatoria in MARCAS_OBLIGATORIAS:
        clave, valor = obligatoria.split("=", 1)
        if marcas.get(clave) != valor:
            faltan.append(obligatoria)
    return faltan


def subsistema_pe(ruta: Path) -> int | None:
    """Lee el subsistema de la cabecera PE. None si no es un .exe de Windows.

    El campo está en el OptionalHeader, a 0x5C bytes del inicio de la
    cabecera PE, cuya posición la da el DWORD en 0x3C del archivo.
    """
    try:
        with open(ruta, "rb") as f:
            cabecera = f.read(0x400)
        if cabecera[:2] != b"MZ":
            return None
        desplazamiento_pe = struct.unpack_from("<I", cabecera, 0x3C)[0]
        if cabecera[desplazamiento_pe : desplazamiento_pe + 4] != b"PE\x00\x00":
            return None
        return struct.unpack_from("<H", cabecera, desplazamiento_pe + 0x5C)[0]
    except (OSError, struct.error):
        return None


def ejecutar_autotest(ejecutable: Path, limite: int = 300) -> tuple[int, bytes]:
    """Lanza el autotest y devuelve (código, salida cruda en bytes)."""
    resultado = subprocess.run(
        [str(ejecutable), "--autotest"],
        capture_output=True, timeout=limite,
    )
    return resultado.returncode, resultado.stdout + resultado.stderr


# ---------------------------------------------------------------------------
# Programa
# ---------------------------------------------------------------------------
def verificar(diagnostico: Path, principal: Path | None = None) -> int:
    print("VozClip · verificación del ejecutable")
    print("=" * 60)
    problemas: list[str] = []

    # 1. El autotest
    if not diagnostico.exists():
        print(f"[FALLA] No existe {diagnostico}")
        return 1

    print(f"Ejecutando: {diagnostico.name} --autotest")
    codigo, salida = ejecutar_autotest(diagnostico)
    print(salida.decode("utf-8", errors="replace"))
    print("-" * 60)

    if codigo != 0:
        problemas.append(f"el autotest ha devuelto el código {codigo}")

    # 2. Las marcas
    marcas = extraer_marcas(salida)
    faltan = marcas_que_faltan(marcas)
    if faltan:
        problemas.append("faltan marcas: " + ", ".join(faltan))
    else:
        print(f"[ OK ] las {len(MARCAS_OBLIGATORIAS)} marcas obligatorias están")

    # 3. El principal no abre consola
    if principal is not None:
        if not principal.exists():
            problemas.append(f"no existe {principal}")
        else:
            subsistema = subsistema_pe(principal)
            if subsistema is None:
                print(f"[ -- ] {principal.name} no es un ejecutable de Windows; "
                      "no se comprueba el subsistema")
            elif subsistema == SUBSISTEMA_VENTANA:
                print(f"[ OK ] {principal.name} arranca sin consola (subsistema 2)")
            else:
                problemas.append(
                    f"{principal.name} abriría una consola (subsistema {subsistema}); "
                    "revisa --windowed en build_exe.py"
                )

    print("=" * 60)
    if problemas:
        print("VERIFICACIÓN FALLIDA:")
        for p in problemas:
            print(f"  · {p}")
        return 1

    print("VERIFICACIÓN CORRECTA: el ejecutable arranca, habla y responde.")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        print("uso: verificar_binario.py <VozClip-Diagnostico.exe> [<VozClip.exe>]")
        return 2
    diagnostico = Path(argv[0])
    principal = Path(argv[1]) if len(argv) > 1 else None
    return verificar(diagnostico, principal)


if __name__ == "__main__":
    sys.exit(main())
