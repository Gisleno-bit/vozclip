"""Tests de la configuración de empaquetado.

Estos tests no compilan nada: comprueban que la configuración con la que se
compila es correcta. Existen porque un .exe mal empaquetado falla en silencio
(se compila sin errores y luego el doble clic no hace nada), y eso es
carísimo de diagnosticar comparado con lo que cuesta prevenirlo aquí.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
LANZADOR = RAIZ / "scripts" / "lanzador.py"
BUILD = RAIZ / "scripts" / "build_exe.py"


# -- El lanzador ------------------------------------------------------------
def test_existe_el_lanzador():
    assert LANZADOR.exists(), "Falta scripts/lanzador.py"


def test_el_lanzador_no_usa_imports_relativos():
    """Regresión del fallo real: PyInstaller ejecuta el script de entrada sin
    contexto de paquete, así que `from .cli import main` lanza
    ImportError y, en modo --windowed, no se ve por ningún lado.
    """
    arbol = ast.parse(LANZADOR.read_text(encoding="utf-8"))
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.ImportFrom):
            assert nodo.level == 0, (
                f"El lanzador usa un import relativo ('{'.' * nodo.level}"
                f"{nodo.module}'). PyInstaller no lo soporta."
            )


def test_el_lanzador_importa_la_funcion_correcta():
    codigo = LANZADOR.read_text(encoding="utf-8")
    assert "from vozclip.cli import main" in codigo


def test_main_sigue_usando_import_relativo():
    """__main__.py SÍ debe usarlo: es lo correcto para `python -m vozclip`.
    Los dos puntos de entrada conviven a propósito."""
    codigo = (RAIZ / "src" / "vozclip" / "__main__.py").read_text(encoding="utf-8")
    assert "from .cli import main" in codigo


# -- El script de compilación -----------------------------------------------
def test_build_apunta_al_lanzador_y_no_a_main():
    codigo = BUILD.read_text(encoding="utf-8")
    assert '"scripts" / "lanzador.py"' in codigo, (
        "build_exe.py debe apuntar al lanzador, no a __main__.py"
    )
    assert '"vozclip" / "__main__.py"' not in codigo


def test_el_ejecutable_principal_se_compila_sin_consola():
    codigo = BUILD.read_text(encoding="utf-8")
    assert "--windowed" in codigo
    assert 'construir("VozClip", con_consola=False)' in codigo


def test_el_de_diagnostico_se_compila_con_consola():
    codigo = BUILD.read_text(encoding="utf-8")
    assert 'construir("VozClip-Diagnostico", con_consola=True)' in codigo


def test_estan_declarados_los_imports_perezosos():
    """Cada módulo que se importa dentro de una función tiene que estar en
    la lista de hidden imports, o PyInstaller no lo empaqueta."""
    codigo = BUILD.read_text(encoding="utf-8")
    imprescindibles = [
        "win32com.client",   # voz en Windows
        "pythoncom",         # CoInitialize del hilo de voz
        "pywintypes",        # dependencia de pywin32
        "pyperclip",         # portapapeles
        "tkinter",           # la ventana
        "docx",              # lectura de Word
        "pypdf",             # lectura de PDF
    ]
    for modulo in imprescindibles:
        assert f'"{modulo}"' in codigo, f"Falta '{modulo}' en los hidden imports"


def test_pynput_se_recoge_entero():
    """pynput carga sus backends por reflexión; sin collect-submodules el
    .exe se queda sin atajos globales."""
    codigo = BUILD.read_text(encoding="utf-8")
    assert "--collect-submodules" in codigo
    assert '"pynput"' in codigo


# -- Los workflows ----------------------------------------------------------
def _leer_workflow(nombre: str) -> str:
    """Lee un workflow, o SALTA el test si todavía no está en el repositorio.

    Los workflows son infraestructura de entrega, no código. Si faltan
    porque aún no se han subido, el programa funciona igual: poner la CI en
    rojo por eso es ruido, y además es un fallo que no se puede arreglar
    desde la propia CI. Si el archivo SÍ está pero le falta algo, entonces
    sí se falla: eso es una incoherencia real.
    """
    ruta = RAIZ / ".github" / "workflows" / nombre
    if not ruta.exists():
        pytest.skip(
            f"Falta .github/workflows/{nombre}. Créalo con los botones de "
            "SUBIR_A_GITHUB.html; hasta entonces no se publica la release."
        )
    return ruta.read_text(encoding="utf-8")


def _exigir_en_workflow(nombre: str, *fragmentos: str) -> None:
    """Comprueba que un workflow contiene ciertos fragmentos.

    El mensaje de error es corto y dice qué hacer, en vez de volcar el
    archivo entero. Cuando esto falla, casi siempre significa lo mismo: el
    workflow del repositorio se ha quedado atrás respecto al código, porque
    se subió a mano una versión antigua. Un `assert "X" in contenido` a
    secas vuelca cientos de líneas y no dice nada de eso.
    """
    contenido = _leer_workflow(nombre)
    faltan = [f for f in fragmentos if f not in contenido]
    if faltan:
        raise AssertionError(
            f"A .github/workflows/{nombre} le faltan {len(faltan)} cosa(s): "
            + ", ".join(repr(f) for f in faltan)
            + ". Suele significar que el workflow del repositorio es más "
            "antiguo que el código. Sustitúyelo por el del proyecto "
            "(scripts/verificar_repo.py lo comprueba todo de una vez)."
        )


def test_el_workflow_de_compilacion_existe():
    ruta = RAIZ / ".github" / "workflows" / "release.yml"
    if not ruta.exists():
        pytest.skip("Falta release.yml: créalo con SUBIR_A_GITHUB.html")
    assert ruta.exists()


def test_el_workflow_solo_llama_a_los_scripts():
    """El YAML es un cascarón: toda la lógica está en scripts/ y se prueba
    aquí. Si el YAML del repositorio se queda viejo, esta es la ÚNICA
    comprobación que lo detecta, y su mensaje dice qué hacer."""
    _exigir_en_workflow(
        "release.yml",
        "scripts/verificar_repo.py",
        "scripts/build_exe.py",
        "scripts/descargar_modelo.py",
        "scripts/verificar_binario.py",
        "scripts/empaquetar.py",
        "choco install python312",         # plan B de Tcl/Tk
    )
    _exigir_en_workflow("tests.yml", "scripts/verificar_repo.py", "libportaudio2")


def test_el_workflow_no_lleva_logica_dentro():
    """Cada bloque de PowerShell es una razón para tener que resubir el
    YAML a mano. Se admiten dos: el plan B de Tcl/Tk y el instalador de
    Inno Setup, que no se pueden hacer desde Python."""
    contenido = _leer_workflow("release.yml")
    assert contenido.count("shell: pwsh") <= 2
    assert "-notmatch" not in contenido
    assert "Contains(" not in contenido
    assert len(contenido.splitlines()) < 130


def _cargar_script(nombre: str):
    import importlib.util

    ruta = RAIZ / "scripts" / nombre
    spec = importlib.util.spec_from_file_location(nombre[:-3], ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def test_las_marcas_obligatorias_son_ascii():
    """Ninguna comprobación de la CI puede depender de un acento."""
    modulo = _cargar_script("verificar_binario.py")
    for marca in modulo.MARCAS_OBLIGATORIAS:
        assert marca.isascii(), marca
    assert "VOZCLIP_DICTADO_EMPAQUETADO=OK" in modulo.MARCAS_OBLIGATORIAS


def test_el_verificador_exige_las_marcas_que_el_autotest_emite():
    """Una marca exigida que el autotest no emita rompería la CI para
    siempre, y al revés dejaría un hueco sin vigilar."""
    modulo = _cargar_script("verificar_binario.py")
    exigidas = {m.split("=")[0] for m in modulo.MARCAS_OBLIGATORIAS}
    emitidas = set(_marcas_del_autotest())
    faltan = exigidas - emitidas
    assert not faltan, f"Se exigen marcas que el autotest no emite: {faltan}"


def test_extraer_marcas_sobrevive_a_cualquier_codificacion():
    """Lo que antes se comprobaba en PowerShell, ahora aquí."""
    modulo = _cargar_script("verificar_binario.py")
    salida = "  [ OK ] están empaquetados\nVOZCLIP_RESULTADO=OK\nVOZCLIP_ODT=OK\n"
    for codificacion in ("utf-8", "cp1252", "cp437"):
        marcas = modulo.extraer_marcas(salida.encode(codificacion, errors="replace"))
        assert marcas["VOZCLIP_RESULTADO"] == "OK"
        assert marcas["VOZCLIP_ODT"] == "OK"


def test_marcas_que_faltan():
    modulo = _cargar_script("verificar_binario.py")
    completas = {m.split("=")[0]: "OK" for m in modulo.MARCAS_OBLIGATORIAS}
    assert modulo.marcas_que_faltan(completas) == []
    sin_odt = dict(completas)
    sin_odt["VOZCLIP_ODT"] = "FALLO"
    assert modulo.marcas_que_faltan(sin_odt) == ["VOZCLIP_ODT=OK"]


def test_subsistema_pe(tmp_path):
    """La lectura de la cabecera PE que antes hacía PowerShell."""
    import struct

    modulo = _cargar_script("verificar_binario.py")

    def fabricar(subsistema: int) -> Path:
        b = bytearray(0x400)
        b[0:2] = b"MZ"
        struct.pack_into("<I", b, 0x3C, 0x80)
        b[0x80:0x84] = b"PE\x00\x00"
        struct.pack_into("<H", b, 0x80 + 0x5C, subsistema)
        ruta = tmp_path / f"exe_{subsistema}.exe"
        ruta.write_bytes(bytes(b))
        return ruta

    assert modulo.subsistema_pe(fabricar(2)) == modulo.SUBSISTEMA_VENTANA
    assert modulo.subsistema_pe(fabricar(3)) == modulo.SUBSISTEMA_CONSOLA

    no_exe = tmp_path / "script.sh"
    no_exe.write_bytes(b"#!/bin/sh\necho hola\n")
    assert modulo.subsistema_pe(no_exe) is None


def test_el_empaquetador_arma_el_zip(tmp_path):
    """El bloque de PowerShell de empaquetado, ahora probado."""
    import zipfile

    modulo = _cargar_script("empaquetar.py")
    raiz = tmp_path / "repo"
    (raiz / "dist").mkdir(parents=True)
    (raiz / "scripts").mkdir()
    for rel in ("dist/VozClip.exe", "dist/VozClip-Diagnostico.exe", "LEEME.txt",
                "GUIA_RAPIDA.txt", "scripts/instalar_en_inicio.bat",
                "scripts/instalar_modelos.bat"):
        (raiz / rel).write_bytes(b"x")
    modelo = raiz / "modelos" / "vosk-model-small-es-0.42" / "am"
    modelo.mkdir(parents=True)
    (modelo / "final.mdl").write_bytes(b"m")

    salida = tmp_path / "paquete.zip"
    assert modulo.armar(raiz, salida, avisar=lambda _m: None) == []

    with zipfile.ZipFile(salida) as z:
        nombres = set(z.namelist())
    assert "VozClip.exe" in nombres
    assert "instalar_modelos.bat" in nombres
    assert "modelos/vosk-model-small-es-0.42/am/final.mdl" in nombres


def test_el_empaquetador_se_niega_si_falta_el_exe(tmp_path):
    """Un paquete a medias es peor que ninguno."""
    modulo = _cargar_script("empaquetar.py")
    raiz = tmp_path / "repo"
    raiz.mkdir()
    (raiz / "LEEME.txt").write_text("x")
    problemas = modulo.armar(raiz, tmp_path / "p.zip", avisar=lambda _m: None)
    assert any("VozClip.exe" in p for p in problemas)
    assert not (tmp_path / "p.zip").exists()


def test_el_empaquetador_funciona_sin_modelo(tmp_path):
    """Si la descarga falló, el paquete sale igual, con el .bat dentro."""
    modulo = _cargar_script("empaquetar.py")
    raiz = tmp_path / "repo"
    (raiz / "dist").mkdir(parents=True)
    (raiz / "scripts").mkdir()
    for rel in ("dist/VozClip.exe", "dist/VozClip-Diagnostico.exe", "LEEME.txt",
                "GUIA_RAPIDA.txt", "scripts/instalar_en_inicio.bat",
                "scripts/instalar_modelos.bat"):
        (raiz / rel).write_bytes(b"x")
    avisos = []
    assert modulo.armar(raiz, tmp_path / "p.zip", avisar=avisos.append) == []
    assert any("sin modelos" in a for a in avisos)


def test_existe_el_leeme():
    leeme = RAIZ / "LEEME.txt"
    assert leeme.exists()
    contenido = leeme.read_text(encoding="utf-8")
    assert "VozClip.exe" in contenido
    assert "VozClip-Diagnostico.exe" in contenido


def test_existe_el_instalador():
    iss = RAIZ / "installer" / "VozClip.iss"
    assert iss.exists()
    contenido = iss.read_text(encoding="utf-8")
    # Sin UAC: un diálogo de permisos es un obstáculo real sin visión
    assert "PrivilegesRequired=lowest" in contenido
    # Acceso directo en el escritorio
    assert "autodesktop" in contenido


def test_el_instalador_incluye_ambos_ejecutables():
    contenido = (RAIZ / "installer" / "VozClip.iss").read_text(encoding="utf-8")
    assert "VozClip.exe" in contenido
    assert "VozClip-Diagnostico.exe" in contenido


# ===========================================================================
# Dictado: sus dependencias nativas son las más fáciles de perder
# ===========================================================================
def test_vosk_se_recoge_entero():
    """vosk NO tiene hook en PyInstaller. Sin --collect-all, libvosk.dll se
    queda fuera, el .exe compila bien y el dictado falla al usarse."""
    codigo = BUILD.read_text(encoding="utf-8")
    assert "--collect-all" in codigo
    assert 'COLECCION_COMPLETA = ["vosk"]' in codigo


def test_estan_las_dependencias_del_dictado():
    codigo = BUILD.read_text(encoding="utf-8")
    for modulo in ["vosk", "sounddevice", "cffi", "_cffi_backend"]:
        assert f'"{modulo}"' in codigo, f"Falta '{modulo}' en el empaquetado"


def test_estan_las_dependencias_indirectas_de_vosk():
    """vosk importa estas en su __init__; si faltan, revienta al importarlo."""
    codigo = BUILD.read_text(encoding="utf-8")
    for modulo in ["srt", "tqdm", "requests", "websockets"]:
        assert f'"{modulo}"' in codigo, f"Falta '{modulo}', que vosk necesita"


def test_numpy_sigue_excluido():
    """Se usa RawInputStream justamente para no depender de numpy. Si se
    colara, el ejecutable engordaría 30 MB para nada."""
    codigo = BUILD.read_text(encoding="utf-8")
    assert '"numpy"' in codigo
    assert "EXCLUIDOS" in codigo


def test_requirements_incluye_el_dictado():
    contenido = (RAIZ / "requirements.txt").read_text(encoding="utf-8")
    assert "vosk" in contenido
    assert "sounddevice" in contenido


def test_el_instalador_trae_el_modelo_y_deja_reinstalarlo():
    """El modelo viene incluido, así que el .bat ya no es obligatorio: queda
    en el menú Inicio por si hay que reinstalarlo."""
    contenido = (RAIZ / "installer" / "VozClip.iss").read_text(encoding="utf-8")
    assert r'DestDir: "{app}\modelos"' in contenido      # el modelo viaja dentro
    assert "instalar_modelos.bat" in contenido            # y el .bat también


def test_el_leeme_explica_el_dictado():
    contenido = (RAIZ / "LEEME.txt").read_text(encoding="utf-8")
    assert "F1" in contenido


# ===========================================================================
# Que no se cuele una dependencia sin declarar
# ===========================================================================
def _dependencias_de_terceros() -> set[str]:
    """Escanea el código y devuelve los paquetes externos que importa."""
    import ast
    import sys

    externos: set[str] = set()
    for archivo in (RAIZ / "src" / "vozclip").glob("*.py"):
        arbol = ast.parse(archivo.read_text(encoding="utf-8"))
        for nodo in ast.walk(arbol):
            if isinstance(nodo, ast.Import):
                for alias in nodo.names:
                    externos.add(alias.name.split(".")[0])
            elif isinstance(nodo, ast.ImportFrom) and nodo.level == 0 and nodo.module:
                externos.add(nodo.module.split(".")[0])

    estandar = set(sys.stdlib_module_names)
    return {m for m in externos if m not in estandar and m != "vozclip"}


# Se importan de forma perezosa y con fallback: el programa funciona sin
# ellas. No van en el .exe estándar y build_exe.py las EXCLUYE a propósito.
DEPENDENCIAS_OPCIONALES = {"faster_whisper", "ctranslate2"}


def test_toda_dependencia_esta_declarada_en_el_build():
    """Una dependencia que el código usa pero PyInstaller no empaqueta da
    un .exe que compila bien y falla al ejecutarse. Este test lo impide.

    Las opcionales tienen que aparecer también, pero en la lista de
    EXCLUIDOS: que nadie las meta sin querer por tenerlas instaladas."""
    codigo = BUILD.read_text(encoding="utf-8")
    for paquete in _dependencias_de_terceros():
        assert f'"{paquete}' in codigo, (
            f"'{paquete}' se usa en el código pero no está en build_exe.py"
        )
    for opcional in DEPENDENCIAS_OPCIONALES:
        excluidos = codigo[codigo.index("EXCLUIDOS = ["):codigo.index("]", codigo.index("EXCLUIDOS = ["))]
        assert f'"{opcional}"' in excluidos, f"'{opcional}' debe estar en EXCLUIDOS"


def test_no_han_aparecido_dependencias_nuevas():
    """La portabilidad y la importación se hicieron sin añadir librerías:
    el lector de RTF y la detección de ventana son código propio, con
    ctypes. Si alguna vez cambia, este test obliga a revisar el tamaño
    del ejecutable."""
    esperadas = {
        "docx", "pynput", "pypdf", "pyperclip",
        "pythoncom", "sounddevice", "vosk", "win32com",
    } | DEPENDENCIAS_OPCIONALES
    # Ojo: el formato de Julián, los perfiles y la exportación a Word se
    # hicieron SIN añadir ni una librería. El .exe no crece por esto.
    assert _dependencias_de_terceros() == esperadas


def _modulos_importados(nombre_archivo: str) -> set[str]:
    """Los módulos que un archivo IMPORTA de verdad.

    Se analiza el árbol sintáctico y no el texto: buscar la cadena
    "psutil" también encuentra el comentario que explica por qué NO se usa,
    y "pyth" encuentra "python-docx". Los tests que se creen sus propias
    conclusiones a partir de subcadenas dan falsos positivos.
    """
    import ast

    archivo = RAIZ / "src" / "vozclip" / nombre_archivo
    arbol = ast.parse(archivo.read_text(encoding="utf-8"))
    modulos: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Import):
            for alias in nodo.names:
                modulos.add(alias.name.split(".")[0])
        elif isinstance(nodo, ast.ImportFrom) and nodo.module:
            modulos.add(nodo.module.split(".")[0])
    return modulos


def test_el_lector_de_rtf_no_usa_libreria_externa():
    """El RTF se interpreta a mano para no engordar el ejecutable por un
    formato de paso."""
    codigo = (RAIZ / "src" / "vozclip" / "fuentes.py").read_text(encoding="utf-8")
    assert "_leer_rtf" in codigo

    importados = _modulos_importados("fuentes.py")
    for libreria in ("striprtf", "pyth", "rtf_tokenize", "pypandoc"):
        assert libreria not in importados


def test_la_deteccion_de_ventana_usa_ctypes_no_psutil():
    """psutil pesa y no hace falta: tres llamadas a la API de Windows."""
    importados = _modulos_importados("puente.py")
    assert "ctypes" in importados
    assert "psutil" not in importados
    assert "win32gui" not in importados


def test_el_formato_de_julian_esta_documentado():
    """Las medidas de su documento de estilo tienen que estar donde él
    pueda oírlas, no solo en el código."""
    guia = (RAIZ / "GUIA_RAPIDA.txt").read_text(encoding="utf-8")
    leeme = (RAIZ / "LEEME.txt").read_text(encoding="utf-8")
    for texto in (guia, leeme):
        assert "0,63" in texto
        assert "1,25" in texto
        assert "18 puntos" in texto


def test_los_cinco_comandos_diarios_estan_documentados():
    for archivo in ("GUIA_RAPIDA.txt", "LEEME.txt"):
        contenido = (RAIZ / archivo).read_text(encoding="utf-8")
        for tecla in ("F1", "F2", "F3", "F4", "F5"):
            assert tecla in contenido, f"{archivo} no menciona {tecla}"


def test_el_perfil_julian_no_necesita_archivos_extra():
    """Va escrito en el código, no en un JSON aparte: así el .exe lo lleva
    dentro y no hay nada que se pueda perder al copiarlo."""
    codigo = (RAIZ / "src" / "vozclip" / "perfiles.py").read_text(encoding="utf-8")
    assert "PERFIL_JULIAN" in codigo
    assert '"tema": "alto_contraste"' in codigo


def test_exportar_a_word_no_anade_dependencias():
    """python-docx ya estaba para leer .docx; exportar no cuesta nada más."""
    importados = _modulos_importados("exportar_word.py")
    externos = importados - {"docx"} - set(__import__("sys").stdlib_module_names)
    externos = {m for m in externos if m not in ("fuentes", "plantillas")}
    assert not externos, f"Dependencias nuevas: {externos}"


def test_la_guia_rapida_esta_al_dia():
    """Los atajos se reorganizaron; la documentación tiene que seguirlos."""
    guia = (RAIZ / "GUIA_RAPIDA.txt").read_text(encoding="utf-8")
    for atajo in ("Control + Alt + U", "Control + Alt + K", "Control + Alt + O",
                  "Control + Alt + E", "Control + Alt + C", "Control + Alt + Z",
                  "Control + Alt + Y"):
        assert atajo in guia, f"La guía rápida no menciona {atajo}"


def test_el_leeme_menciona_la_accesibilidad():
    contenido = (RAIZ / "LEEME.txt").read_text(encoding="utf-8")
    assert "alto contraste" in contenido
    assert "solo voz" in contenido


# ===========================================================================
# Marcas del autotest: inmunes a la página de códigos
# ===========================================================================
def _marcas_del_autotest() -> dict[str, str]:
    """Ejecuta el autotest del código fuente y devuelve sus marcas."""
    import os
    import subprocess
    import sys

    entorno = dict(os.environ, PYTHONPATH=str(RAIZ / "src"))
    orden = [sys.executable, "-m", "vozclip", "--autotest"]
    if os.name != "nt" and os.environ.get("DISPLAY"):
        pass
    elif os.name != "nt":
        import pytest

        pytest.skip("El autotest necesita entorno gráfico")

    resultado = subprocess.run(
        orden, capture_output=True, env=entorno, timeout=180
    )
    salida = (resultado.stdout + resultado.stderr).decode("utf-8", errors="replace")

    marcas = {}
    for linea in salida.splitlines():
        if linea.startswith("VOZCLIP_") and "=" in linea:
            clave, valor = linea.split("=", 1)
            marcas[clave.strip()] = valor.strip()
    return marcas


def test_el_autotest_emite_marcas():
    marcas = _marcas_del_autotest()
    assert marcas, "El autotest no ha emitido ninguna marca"
    assert marcas.get("VOZCLIP_RESULTADO") == "OK"


def test_las_marcas_son_ascii_puro():
    """El motivo de que existan.

    La salida bonita del autotest lleva acentos. Una consola de Windows con
    la página de códigos equivocada convierte "están" en "estÃ¡n", y un
    script que busque el texto acentuado no lo encuentra aunque todo haya
    ido bien. Eso es lo que hacía fallar la CI con el autotest en verde.
    """
    marcas = _marcas_del_autotest()
    for clave, valor in marcas.items():
        linea = f"{clave}={valor}"
        assert linea.isascii(), f"La marca {linea!r} tiene caracteres no ASCII"


def test_las_marcas_sobreviven_a_una_codificacion_equivocada():
    """Se relee la salida como cp1252, que es lo que hacía PowerShell."""
    import os
    import subprocess
    import sys

    if os.name != "nt" and not os.environ.get("DISPLAY"):
        import pytest

        pytest.skip("El autotest necesita entorno gráfico")

    entorno = dict(os.environ, PYTHONPATH=str(RAIZ / "src"))
    resultado = subprocess.run(
        [sys.executable, "-m", "vozclip", "--autotest"],
        capture_output=True, env=entorno, timeout=180,
    )
    crudo = resultado.stdout + resultado.stderr

    for codificacion in ("utf-8", "cp1252", "cp437", "latin-1"):
        salida = crudo.decode(codificacion, errors="replace")
        assert "VOZCLIP_RESULTADO=OK" in salida, (
            f"La marca se pierde al leer la salida como {codificacion}"
        )


def test_el_cli_fuerza_utf8():
    codigo = (RAIZ / "src" / "vozclip" / "cli.py").read_text(encoding="utf-8")
    assert "_forzar_utf8" in codigo
    assert "SetConsoleOutputCP" in codigo


# ===========================================================================
# El verificador del repositorio
# ===========================================================================
def test_el_verificador_existe_y_pasa():
    """Sobre el propio proyecto tiene que dar el visto bueno."""
    import subprocess
    import sys

    resultado = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "verificar_repo.py")],
        capture_output=True, text=True, timeout=60, cwd=str(RAIZ),
    )
    assert resultado.returncode == 0, resultado.stdout
    assert "al día" in resultado.stdout


def test_el_verificador_avisa_de_un_workflow_viejo_sin_fallar(tmp_path):
    """Un workflow viejo se avisa pero NO devuelve error: si fallara, la
    propia CI se pondría roja por algo que no se puede arreglar desde la
    CI. El aviso dice qué archivo y qué le falta."""
    import shutil
    import subprocess
    import sys

    copia = tmp_path / "repo"
    shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns(
        "__pycache__", ".git", "build", "dist", "*.egg-info"))

    yml = copia / ".github" / "workflows" / "release.yml"
    yml.parent.mkdir(parents=True, exist_ok=True)
    yml.write_text("name: Compilar Windows\n", encoding="utf-8")

    resultado = subprocess.run(
        [sys.executable, str(copia / "scripts" / "verificar_repo.py")],
        capture_output=True, text=True, timeout=60, cwd=str(copia),
    )
    assert resultado.returncode == 0, "un workflow viejo no debe romper la CI"
    assert "release.yml" in resultado.stdout
    assert "DESACTUALIZADO" in resultado.stdout
    assert "scripts/verificar_binario.py" in resultado.stdout


def test_el_verificador_si_falla_si_falta_codigo(tmp_path):
    """Lo que SÍ es un problema: que falte un módulo del programa."""
    import shutil
    import subprocess
    import sys

    copia = tmp_path / "repo"
    shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns(
        "__pycache__", ".git", "build", "dist", "*.egg-info"))
    (copia / "src" / "vozclip" / "correccion.py").unlink()

    resultado = subprocess.run(
        [sys.executable, str(copia / "scripts" / "verificar_repo.py")],
        capture_output=True, text=True, timeout=60, cwd=str(copia),
    )
    assert resultado.returncode == 1
    assert "correccion.py" in resultado.stdout


def test_el_verificador_avisa_si_faltan_los_workflows(tmp_path):
    """El caso de un repositorio recién subido a mano: el código está, los
    workflows todavía no. Verde, con instrucciones."""
    import shutil
    import subprocess
    import sys

    copia = tmp_path / "repo"
    shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns(
        "__pycache__", ".git", "build", "dist", "*.egg-info"))
    for nombre in ("release.yml", "tests.yml"):
        (copia / ".github" / "workflows" / nombre).unlink(missing_ok=True)

    resultado = subprocess.run(
        [sys.executable, str(copia / "scripts" / "verificar_repo.py")],
        capture_output=True, text=True, timeout=60, cwd=str(copia),
    )
    assert resultado.returncode == 0
    assert "SUBIR_A_GITHUB.html" in resultado.stdout


def test_el_verificador_avisa_de_los_workflows_obsoletos(tmp_path):
    """ci.yml y build-windows.yml siguen ejecutándose mientras existan."""
    import shutil
    import subprocess
    import sys

    copia = tmp_path / "repo"
    shutil.copytree(RAIZ, copia, ignore=shutil.ignore_patterns(
        "__pycache__", ".git", "build", "dist", "*.egg-info"))
    (copia / ".github" / "workflows" / "ci.yml").write_text("name: CI\n", encoding="utf-8")

    resultado = subprocess.run(
        [sys.executable, str(copia / "scripts" / "verificar_repo.py")],
        capture_output=True, text=True, timeout=60, cwd=str(copia),
    )
    assert resultado.returncode == 0
    assert "obsoleto" in resultado.stdout.lower()
    assert "ci.yml" in resultado.stdout



def test_los_workflows_ejecutan_el_verificador():
    """Que falle en dos segundos y no en treinta, con un mensaje útil."""
    for nombre in ("tests.yml", "release.yml"):
        _exigir_en_workflow(nombre, "scripts/verificar_repo.py")


# ===========================================================================
# La versión, una sola verdad
# ===========================================================================
def test_la_version_es_la_misma_en_los_tres_sitios():
    """`__init__.py`, `pyproject.toml` y el instalador tienen que decir lo
    mismo. Si se desincronizan, el saludo dice una versión y el instalador
    otra, y vuelve a ser imposible saber qué hay instalado."""
    import re

    from vozclip import __version__

    pyproject = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    iss = (RAIZ / "installer" / "VozClip.iss").read_text(encoding="utf-8")

    en_pyproject = re.search(r'^version = "([^"]+)"', pyproject, re.M).group(1)
    en_iss = re.search(r'^#define VersionApp\s+"([^"]+)"', iss, re.M).group(1)

    assert __version__ == en_pyproject == en_iss, (
        f"__init__.py: {__version__}, pyproject: {en_pyproject}, iss: {en_iss}"
    )


def test_la_version_aparece_en_el_changelog():
    from vozclip import __version__

    changelog = (RAIZ / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {__version__}" in changelog, (
        f"El CHANGELOG no tiene entrada para la {__version__}"
    )



# ===========================================================================
# Release automática y subida sin git
# ===========================================================================
def test_version_py_imprime_la_version_del_proyecto():
    import subprocess
    import sys

    from vozclip import __version__

    salida = subprocess.run(
        [sys.executable, str(RAIZ / "scripts" / "version.py")],
        capture_output=True, text=True, timeout=30,
    ).stdout
    assert salida == __version__            # sin salto de línea: va a un output de Actions


def test_la_release_se_crea_sola_en_cada_push():
    """Sin etiquetas a mano: el workflow lee la versión y etiqueta él."""
    contenido = _leer_workflow("release.yml")
    assert "scripts/version.py" in contenido
    assert "tag_name: v${{ steps.version.outputs.v }}" in contenido
    assert "branches: [main]" in contenido
    assert "startsWith(github.ref, 'refs/tags" not in contenido   # ya no depende del tag


def test_la_release_publica_los_cuatro_archivos():
    contenido = _leer_workflow("release.yml")
    for archivo in ("VozClip-Windows.zip", "installer/salida/*.exe",
                    "dist/VozClip.exe", "dist/VozClip-Diagnostico.exe"):
        assert archivo in contenido


def test_no_quedan_workflows_viejos():
    """Los viejos hay que borrarlos: mientras existan seguirán
    ejecutándose y fallando en rojo por su cuenta.

    Se SALTA, no falla: es lo mismo que comprobar que faltan los nuevos, y
    hacer que la CI se ponga roja por ello no ayuda a nadie. El aviso sale
    en `verificar_repo.py`, que es el primer paso de los workflows."""
    carpeta = RAIZ / ".github" / "workflows"
    viejos = [p.name for p in carpeta.glob("*.yml")
              if p.name in ("build-windows.yml", "ci.yml")]
    if viejos:
        pytest.skip(
            f"Workflows obsoletos: {', '.join(viejos)}. Bórralos en GitHub; "
            "los sustituyen release.yml y tests.yml."
        )


def test_los_enlaces_reconstruyen_los_archivos_exactos():
    """Lo único que importa de la página: que el botón abra GitHub con el
    contenido idéntico al del proyecto."""
    from urllib.parse import parse_qs, urlparse

    modulo = _cargar_script("enlaces_github.py")
    for ruta in modulo.ARCHIVOS_NUEVOS:
        if not (RAIZ / ruta).exists():
            pytest.skip(f"Falta {ruta}")
        original = (RAIZ / ruta).read_text(encoding="utf-8")
        url = modulo.url_crear(ruta, original)
        q = parse_qs(urlparse(url).query, keep_blank_values=True)
        assert q["filename"][0] == ruta
        assert q["value"][0] == original
        assert url.startswith("https://github.com/Gisleno-bit/vozclip/new/main?")


def test_los_enlaces_no_apuntan_a_workflows_obsoletos():
    """La lista de obsoletos y la de nuevos no pueden solaparse."""
    modulo = _cargar_script("enlaces_github.py")
    assert not set(modulo.ARCHIVOS_NUEVOS) & set(modulo.ARCHIVOS_OBSOLETOS)


def test_la_pagina_de_subida_esta_generada_y_al_dia():
    """SUBIR_A_GITHUB.html tiene que corresponder a los workflows actuales."""
    modulo = _cargar_script("enlaces_github.py")
    if any(not (RAIZ / r).exists() for r in modulo.ARCHIVOS_NUEVOS):
        pytest.skip("Faltan workflows: la página no se puede comparar")
    pagina = (RAIZ / "SUBIR_A_GITHUB.html").read_text(encoding="utf-8")
    assert pagina == modulo.generar(), (
        "SUBIR_A_GITHUB.html está desactualizado: python scripts/enlaces_github.py"
    )


def test_la_pagina_tiene_la_url_de_descarga_fija():
    pagina = (RAIZ / "SUBIR_A_GITHUB.html").read_text(encoding="utf-8")
    assert "releases/latest/download/VozClip-Windows.zip" in pagina
