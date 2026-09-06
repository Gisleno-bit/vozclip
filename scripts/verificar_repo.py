"""Comprueba que el repositorio está completo y al día.

=============================================================================
PARA QUÉ SIRVE
=============================================================================
Cuando los archivos se suben a mano a GitHub, es fácil que alguno se quede
atrás: subes el código nuevo pero no el workflow, o al revés. El resultado
es una CI que falla con un error que no dice nada útil, del tipo
"AssertionError: assert 'OutputEncoding' in 'name: Compilar Windows...'"
seguido de doscientas líneas de YAML.

Esto lo detecta antes, en un segundo, y dice exactamente qué archivo hay que
volver a subir.

    python scripts/verificar_repo.py

Devuelve 0 si todo está bien y 1 si falta algo.
=============================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

# Archivos que TIENEN que existir, y fragmentos que deben contener. Cada
# fragmento corresponde a algo que el código da por hecho: si falta, o la CI
# falla o una función no llega al usuario.
REQUISITOS: dict[str, list[str]] = {
    ".github/workflows/release.yml": [
        # El YAML es un cascarón: solo debe llamar a los scripts.
        "scripts/verificar_repo.py",
        "scripts/build_exe.py",
        "scripts/descargar_modelo.py",
        "scripts/verificar_binario.py",
        "scripts/empaquetar.py",
        "choco install python312",             # plan B si Tcl/Tk está roto
        "VozClip-Windows.zip",
        "scripts/version.py",                  # release automática por versión
        "tag_name: v",
    ],
    "scripts/verificar_binario.py": [
        "VOZCLIP_RESULTADO=OK",
        "VOZCLIP_DICTADO_EMPAQUETADO=OK",
        "VOZCLIP_ODT=OK",
        "SUBSISTEMA_VENTANA",
    ],
    "scripts/empaquetar.py": [
        "instalar_modelos.bat",
        "final.mdl",                           # incluye el modelo si está
    ],
    ".github/workflows/tests.yml": [
        "scripts/verificar_repo.py",
        "libportaudio2",                       # para que import sounddevice funcione
        "xvfb-run",                            # los tests del HUD abren ventana
    ],
    "installer/VozClip.iss": [
        "PrivilegesRequired=lowest",           # sin aviso de UAC
        "autodesktop",                         # acceso directo en el escritorio
        "instalar_modelos.bat",
        "VozClip-Diagnostico.exe",
        "{app}\\modelos",                       # el modelo se instala al lado
    ],
    "scripts/build_exe.py": [
        "scripts\" / \"lanzador.py",           # NO __main__.py: import relativo
        "--windowed",
        "--collect-all",                       # libvosk no tiene hook
    ],
    "scripts/lanzador.py": [
        "from vozclip.cli import main",        # import absoluto
    ],
    "scripts/descargar_modelo.py": [
        "vosk-model-small-es",
        "final.mdl",
    ],
    "scripts/version.py": ['pyproject.toml', 'version = '],
    "scripts/enlaces_github.py": ["new/", "filename=", "release.yml"],
    "scripts/instalar_modelos.bat": [
        "vosk-model-small-es",
        r"%PUBLIC%\VozClip\modelos",       # sin acentos: ver dictado.carpeta_modelos
        r"am\final.mdl",
    ],
    "INSTALAR.bat": ["-m venv .venv", "descargar_modelo.py", "CreateShortcut"],
    "Iniciar VozClip.bat": ["pythonw.exe", "-m vozclip"],
    "LEEME.txt": ["instalar_modelos.bat", "F1", "F5"],
    "GUIA_RAPIDA.txt": ["instalar_modelos.bat", "0,63", "1,25"],
    "requirements.txt": ["vosk", "sounddevice", "pywin32"],
    ".gitattributes": ["*.bat text eol=crlf", "*.py text eol=lf"],
}

# Módulos que el programa necesita para arrancar
# Todos los módulos del paquete. La lista se compara con lo que hay en
# disco, así que un módulo nuevo sin añadir aquí se detecta, y uno
# borrado por error también.
MODULOS = [
    "atajos", "cli", "config", "correccion", "dictado", "documento",
    "exportar_odt", "exportar_word", "fuentes", "hud", "modelo", "perfiles",
    "plantillas", "puente", "texto", "voz",
]


def main() -> int:
    print("VozClip · verificación del repositorio")
    print("=" * 62)

    problemas: list[str] = []
    avisos: list[str] = []

    # --- 1. Módulos del programa -------------------------------------
    print("\n1. Módulos")
    en_disco = {
        p.stem for p in (RAIZ / "src" / "vozclip").glob("*.py")
        if not p.stem.startswith("__")
    }
    sin_declarar = sorted(en_disco - set(MODULOS))
    if sin_declarar:
        avisos.append(
            "Módulos en disco que no están en la lista de verificar_repo.py: "
            + ", ".join(sin_declarar)
        )
    for nombre in MODULOS:
        ruta = RAIZ / "src" / "vozclip" / f"{nombre}.py"
        if ruta.exists():
            print(f"  [ OK ] src/vozclip/{nombre}.py")
        else:
            problemas.append(f"Falta src/vozclip/{nombre}.py")
            print(f"  [FALTA] src/vozclip/{nombre}.py")

    # --- 2. Archivos y su contenido ----------------------------------
    #
    # Los workflows son infraestructura de ENTREGA, no código: si faltan o
    # están viejos, el programa funciona igual. Se avisa, pero no se falla:
    # devolver error haría que la propia CI se pusiera roja por algo que no
    # se puede arreglar desde la CI.
    print("\n2. Archivos de configuración y documentación")
    for relativa, fragmentos in REQUISITOS.items():
        es_workflow = relativa.startswith(".github/")
        ruta = RAIZ / relativa
        if not ruta.exists():
            if es_workflow:
                avisos.append(
                    f"Falta {relativa}: créalo con los botones de "
                    "SUBIR_A_GITHUB.html. Sin él no se publica la release."
                )
                print(f"  [AVISO] {relativa} no está todavía")
            else:
                problemas.append(f"Falta {relativa}")
                print(f"  [FALTA] {relativa}")
            continue

        try:
            contenido = ruta.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            contenido = ruta.read_text(encoding="latin-1")

        ausentes = [f for f in fragmentos if f not in contenido]
        if ausentes:
            destino = avisos if es_workflow else problemas
            destino.append(
                f"{relativa} está DESACTUALIZADO: le falta "
                + ", ".join(repr(a) for a in ausentes)
            )
            print(f"  [VIEJO] {relativa}")
            for a in ausentes:
                print(f"          falta: {a!r}")
        else:
            print(f"  [ OK ] {relativa}")

    # --- 3. Coherencia entre el .bat y el programa -------------------
    print("\n3. El .bat y el programa hablan del mismo modelo")
    try:
        sys.path.insert(0, str(RAIZ / "src"))
        import re

        from vozclip import modelo as modmodelo

        bat = (RAIZ / "scripts" / "instalar_modelos.bat").read_text(encoding="ascii")
        url_bat = re.search(r'set "URL=(.*)"', bat).group(1)
        if url_bat == modmodelo.URL_MODELO:
            print("  [ OK ] el .bat descarga el mismo modelo que el programa")
        else:
            problemas.append("El .bat y modelo.py apuntan a modelos distintos")
            print(f"  [FALLA] .bat: {url_bat}")
            print(f"          programa: {modmodelo.URL_MODELO}")
    except Exception as e:
        problemas.append(f"No se ha podido comparar el .bat con el programa: {e}")
        print(f"  [FALLA] {e}")

    # --- 3b. Avisos que no bloquean -------------------------------------
    print("\n3b. Avisos (no bloquean)")
    for viejo in (".github/workflows/build-windows.yml", ".github/workflows/ci.yml"):
        if (RAIZ / viejo).exists():
            avisos.append(
                f"{viejo} es obsoleto: bórralo. Mientras exista seguirá "
                "ejecutándose por su cuenta y fallando en rojo."
            )
            print(f"  [OBSOLETO] {viejo}")
    gitignore = RAIZ / ".gitignore"
    if not gitignore.exists() or "modelos/" not in gitignore.read_text(encoding="utf-8"):
        avisos.append(
            ".gitignore no excluye modelos/: un `git add .` con el modelo "
            "descargado subiría 46 MB. No afecta a la CI."
        )
        print("  [AVISO] .gitignore no excluye modelos/")

    # --- 4. La versión, una sola verdad -------------------------------
    print("\n4. Versión")
    try:
        import re

        from vozclip import __version__

        pyproject = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
        iss = (RAIZ / "installer" / "VozClip.iss").read_text(encoding="utf-8")
        en_pyproject = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
        en_iss = re.search(r'^#define VersionApp\s+"([^"]+)"', iss, re.M).group(1)
        if __version__ == en_pyproject == en_iss:
            print(f"  [ OK ] {__version__} en __init__.py, pyproject.toml e instalador")
        else:
            problemas.append(
                f"Versión desincronizada: __init__ {__version__}, "
                f"pyproject {en_pyproject}, instalador {en_iss}"
            )
            print("  [FALLA] la versión no coincide en los tres sitios")
    except Exception as e:
        problemas.append(f"No se ha podido comprobar la versión: {e}")

    # --- Veredicto ----------------------------------------------------
    print("\n" + "=" * 62)
    if avisos:
        print(f"{len(avisos)} aviso(s) — no impiden que el programa funcione:\n")
        for a in avisos:
            print(f"  · {a}")
        print()

    if problemas:
        print(f"{len(problemas)} problema(s):\n")
        for p in problemas:
            print(f"  · {p}")
        print(
            "\nSi has subido los archivos a mano a GitHub, vuelve a subir los\n"
            "marcados como VIEJO o FALTA: son los que se han quedado atrás."
        )
        return 1

    if avisos:
        print("El código está completo y al día. Resuelve los avisos para que"
              "\nse publique la release automáticamente.")
    else:
        print("Todo correcto: el repositorio está completo y al día.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
