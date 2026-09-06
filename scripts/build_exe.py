"""Genera los ejecutables de Windows con PyInstaller.

Produce DOS archivos, y hay una razón para cada uno:

  * VozClip.exe             --windowed. Es el que usa el escritor. No abre
                            ninguna ventana de consola: solo el HUD.
  * VozClip-Diagnostico.exe --console. Se ejecuta cuando algo falla: dice
                            qué dependencia falta y emite voz de prueba.
                            También admite --autotest, que es lo que
                            verifica el binario en la CI.

Uso, en Windows y con el entorno virtual activado:

    python scripts/build_exe.py
    python scripts/build_exe.py --solo-principal    (más rápido al iterar)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
# OJO: se apunta al lanzador, NO a __main__.py. Ver scripts/lanzador.py:
# PyInstaller no soporta imports relativos en el script de entrada.
ENTRADA = RAIZ / "scripts" / "lanzador.py"

# Módulos que PyInstaller no detecta solo, porque se importan de forma
# perezosa dentro de funciones (a propósito: así el programa no revienta en
# Linux, donde pywin32 no existe). Si falta uno, el .exe compila bien pero
# falla al ejecutarse, que es el peor de los mundos.
OCULTOS = [
    # Voz en Windows
    "win32com",
    "win32com.client",
    "pythoncom",
    "pywintypes",
    # Teclado y portapapeles
    "pynput.keyboard._win32",
    "pynput.mouse._win32",
    "pyperclip",
    # Interfaz
    "tkinter",
    "tkinter.ttk",
    "tkinter.filedialog",
    "tkinter.messagebox",
    # Lectura de documentos
    "docx",
    "pypdf",
    # Dictado por voz
    "vosk",
    "sounddevice",
    "cffi",
    "_cffi_backend",
    # Dependencias que vosk importa en su __init__
    "srt",
    "tqdm",
    "requests",
    "websockets",
]

# vosk NO tiene hook en PyInstaller, así que `libvosk.dll` (25 MB) se
# quedaría fuera y el .exe fallaría al dictar con un error de librería no
# encontrada. `--collect-all` arrastra el paquete entero: código, datos y
# binarios. sounddevice sí tiene hook oficial, que ya trae PortAudio.
COLECCION_COMPLETA = ["vosk"]

# pynput carga sus backends por reflexión, así que hay que arrastrar el
# paquete entero o el .exe se queda sin atajos globales.
SUBMODULOS = ["pynput"]

# Cosas que no usamos y que abultan mucho. Excluirlas baja el ejecutable
# de unos 40 MB a unos 15.
EXCLUIDOS = [
    "numpy", "pandas", "matplotlib", "scipy", "PIL", "PyQt5", "PyQt6",
    "PySide2", "PySide6", "IPython", "jupyter", "pytest", "setuptools",
    # faster-whisper es OPCIONAL: 81 MB de librerías más el modelo. Si el
    # que compila lo tiene instalado, PyInstaller lo arrastraría al .exe.
    # Se excluye a propósito; se activa instalándolo aparte (ver README).
    "faster_whisper", "ctranslate2", "onnxruntime", "tokenizers",
    "huggingface_hub", "av",
]


def construir(nombre: str, con_consola: bool) -> int:
    orden = [
        sys.executable, "-m", "PyInstaller",
        "--onefile",
        "--console" if con_consola else "--windowed",
        "--name", nombre,
        "--paths", str(RAIZ / "src"),
        "--clean",
        "--noconfirm",
        "--log-level", "WARN",
    ]

    for modulo in OCULTOS:
        orden += ["--hidden-import", modulo]
    for paquete in SUBMODULOS:
        orden += ["--collect-submodules", paquete]
    for paquete in COLECCION_COMPLETA:
        orden += ["--collect-all", paquete]
    for modulo in EXCLUIDOS:
        orden += ["--exclude-module", modulo]

    icono = RAIZ / "assets" / "vozclip.ico"
    if icono.exists():
        orden += ["--icon", str(icono)]

    orden.append(str(ENTRADA))

    print(f"\n=== Compilando {nombre} ({'con' if con_consola else 'sin'} consola) ===")
    resultado = subprocess.run(orden, cwd=RAIZ)
    return resultado.returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Compila los ejecutables.")
    parser.add_argument(
        "--solo-principal",
        action="store_true",
        help="Compila solo VozClip.exe, sin el de diagnóstico.",
    )
    args = parser.parse_args()

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller no está instalado. Ejecuta: pip install pyinstaller")
        return 1

    # Aviso temprano: si Tcl/Tk está roto en este Python, el .exe heredará
    # el problema y no abrirá ninguna ventana. Mejor enterarse ahora.
    try:
        import tkinter

        prueba = tkinter.Tk()
        prueba.withdraw()
        print(f"Tcl/Tk detectado: {prueba.tk.call('info', 'patchlevel')}")
        prueba.destroy()
    except Exception as e:
        print(f"AVISO: tkinter no funciona en este Python ({e}).")
        print("       El ejecutable resultante NO abriría ninguna ventana.")
        print("       Reinstala Python marcando la opción 'tcl/tk and IDLE'.")
        return 1

    if construir("VozClip", con_consola=False):
        return 1
    if not args.solo_principal and construir("VozClip-Diagnostico", con_consola=True):
        return 1

    print("\nListo. En la carpeta dist:")
    for nombre in ("VozClip.exe", "VozClip-Diagnostico.exe"):
        ruta = RAIZ / "dist" / nombre
        if ruta.exists():
            print(f"  {nombre}  ({ruta.stat().st_size / (1024 * 1024):.1f} MB)")

    print("\nSiguiente paso, verificar el binario:")
    print("  dist\\VozClip-Diagnostico.exe --autotest")
    return 0


if __name__ == "__main__":
    sys.exit(main())
