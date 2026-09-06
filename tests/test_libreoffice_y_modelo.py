"""Tests de las tres piezas de esta fase:

  1. Exportación a LibreOffice (.odt), con las medidas exactas.
  2. El instalador del modelo de voz (instalar_modelos.bat).
  3. La detección del modelo instalado, que es lo que une las dos cosas.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

from vozclip import dictado, exportar_odt, plantillas

RAIZ = Path(__file__).resolve().parent.parent
BAT = RAIZ / "scripts" / "instalar_modelos.bat"

TEXTO = """     Aquella noche no dormí.

  —No me lo creo —dijo Elena—. Nadie escribe así.

     Me encogí de hombros.
"""


# ===========================================================================
# 1. Exportación a LibreOffice
# ===========================================================================
@pytest.fixture
def odt(tmp_path):
    ruta = tmp_path / "novela.odt"
    exportar_odt.exportar(TEXTO, ruta, plantillas.NOVELA, titulo="Capítulo 1")
    return ruta


def test_es_un_zip_valido(odt):
    assert zipfile.is_zipfile(odt)


def test_el_mimetype_va_primero_y_sin_comprimir(odt):
    """Lo exige la norma OpenDocument. Si no se cumple, LibreOffice dice
    que el archivo está dañado y se niega a abrirlo."""
    d = exportar_odt.leer(odt)
    assert d["mimetype"] == exportar_odt.MIMETYPE
    assert d["mimetype_primero"]
    assert d["mimetype_sin_comprimir"]


def test_tiene_las_piezas_obligatorias(odt):
    with zipfile.ZipFile(odt) as z:
        nombres = set(z.namelist())
    assert {"mimetype", "META-INF/manifest.xml", "content.xml", "styles.xml"} <= nombres


def test_los_parrafos_se_clasifican_solos(odt):
    d = exportar_odt.leer(odt)
    estilos = [p["estilo"] for p in d["parrafos"]]
    assert estilos == ["Titulo", "Narrador", "Dialogo", "Narrador"]


def test_el_dialogo_lleva_las_medidas_de_julian(odt):
    props = exportar_odt.leer(odt)["estilos"]["Dialogo"]
    limpio = {k.split("}")[1]: v for k, v in props.items()}
    assert limpio["margin-left"] == "0.63cm"
    assert limpio["text-indent"] == "-0.63cm"        # sangría francesa
    assert limpio["margin-bottom"] == "18pt"
    assert "line-height-at-least" in limpio            # interlineado mínimo


def test_el_narrador_lleva_las_medidas_de_julian(odt):
    props = exportar_odt.leer(odt)["estilos"]["Narrador"]
    limpio = {k.split("}")[1]: v for k, v in props.items()}
    assert limpio["text-indent"] == "1.25cm"
    assert limpio["margin-bottom"] == "18pt"
    assert limpio["text-align"] == "justify"
    assert "margin-left" not in limpio


def test_las_lineas_en_blanco_no_generan_parrafos(odt):
    """La separación la da el margen inferior de 18 pt. Con líneas vacías
    además, sería el doble."""
    textos = [p["texto"] for p in exportar_odt.leer(odt)["parrafos"]]
    assert all(t.strip() for t in textos)
    assert len(textos) == 4


def test_los_caracteres_especiales_se_escapan(tmp_path):
    """Un '<' o un '&' sin escapar rompe el XML y LibreOffice no abre nada."""
    ruta = tmp_path / "raro.odt"
    exportar_odt.exportar("Uno < dos & tres > cuatro", ruta, plantillas.NOVELA)
    textos = [p["texto"] for p in exportar_odt.leer(ruta)["parrafos"]]
    assert textos == ["Uno < dos & tres > cuatro"]


def test_exportar_crea_la_carpeta(tmp_path):
    ruta = tmp_path / "a" / "b" / "novela.odt"
    exportar_odt.exportar(TEXTO, ruta, plantillas.NOVELA)
    assert ruta.exists()


def test_exportar_con_todas_las_plantillas(tmp_path):
    for clave in plantillas.ORDEN:
        ruta = tmp_path / f"{clave}.odt"
        exportar_odt.exportar(TEXTO, ruta, plantillas.obtener(clave))
        assert exportar_odt.leer(ruta)["mimetype_primero"]


def test_odt_y_docx_llevan_las_mismas_medidas(tmp_path):
    """Los dos exportadores parten del mismo FormatoWord: no puede haber
    un valor en Word y otro en LibreOffice."""
    pytest.importorskip("docx")
    from vozclip import exportar_word

    ruta_odt = tmp_path / "n.odt"
    ruta_docx = tmp_path / "n.docx"
    exportar_odt.exportar(TEXTO, ruta_odt, plantillas.NOVELA)
    exportar_word.exportar(TEXTO, ruta_docx, plantillas.NOVELA)

    import docx

    dialogo_docx = next(p for p in docx.Document(str(ruta_docx)).paragraphs
                        if exportar_word.es_dialogo(p.text))
    props = exportar_odt.leer(ruta_odt)["estilos"]["Dialogo"]
    limpio = {k.split("}")[1]: v for k, v in props.items()}

    assert f"{round(dialogo_docx.paragraph_format.left_indent.cm, 2)}cm" == limpio["margin-left"]
    assert f"{round(dialogo_docx.paragraph_format.first_line_indent.cm, 2)}cm" == limpio["text-indent"]


@pytest.mark.skipif(shutil.which("soffice") is None, reason="LibreOffice no instalado")
def test_libreoffice_de_verdad_lo_abre(odt, tmp_path):
    """La prueba definitiva: LibreOffice real convierte el .odt a PDF. Si el
    archivo estuviera mal formado, la conversión fallaría."""
    resultado = subprocess.run(
        ["soffice", "--headless", "--convert-to", "pdf", "--outdir",
         str(tmp_path), str(odt)],
        capture_output=True, text=True, timeout=120,
    )
    pdf = tmp_path / "novela.pdf"
    assert pdf.exists(), resultado.stderr
    assert pdf.stat().st_size > 1000


# ===========================================================================
# 2. El instalador del modelo (.bat)
# ===========================================================================
@pytest.fixture
def bat() -> str:
    return BAT.read_text(encoding="ascii")


def test_el_bat_existe():
    assert BAT.exists()


def test_el_bat_es_ascii_puro():
    """La consola de Windows destroza los acentos si el .bat no está en la
    codificación exacta. Sin acentos no hay nada que destrozar."""
    crudo = BAT.read_bytes()
    assert all(b < 128 for b in crudo), "El .bat tiene caracteres fuera de ASCII"


def test_el_bat_usa_saltos_de_linea_de_windows():
    """Con LF suelto, cmd a veces se pierde con los goto."""
    crudo = BAT.read_bytes()
    assert b"\r\n" in crudo
    assert b"\n" not in crudo.replace(b"\r\n", b"")


def test_el_bat_descarga_el_mismo_modelo_que_el_programa(bat):
    from vozclip import modelo

    url = re.search(r'set "URL=(.*)"', bat).group(1)
    assert url == modelo.URL_MODELO


def test_el_bat_instala_donde_el_programa_busca(bat):
    """`dictado.carpeta_modelos()` devuelve %PUBLIC%\\VozClip\\modelos en
    Windows: una ruta sin acentos, que la librería de Vosk sí puede abrir.
    Si el .bat dejara el modelo en otro sitio, VozClip no lo encontraría."""
    destino = re.search(r'set "DESTINO=(.*)"', bat).group(1)
    assert destino == r"%PUBLIC%\VozClip\modelos"


def test_el_bat_no_instala_en_el_perfil_del_usuario(bat):
    """El perfil puede llamarse 'Julián'. Con tilde, la librería en C falla
    con 'Failed to create a model' aunque el modelo esté perfecto."""
    destino = re.search(r'set "DESTINO=(.*)"', bat).group(1)
    assert "APPDATA" not in destino
    assert "USERPROFILE" not in destino


def test_el_bat_verifica_lo_mismo_que_el_programa(bat):
    """Los dos comprueban am\\final.mdl: la misma definición de 'modelo
    válido' en el .bat y en `localizar_modelo`."""
    assert r"am\final.mdl" in bat
    codigo = (RAIZ / "src" / "vozclip" / "dictado.py").read_text(encoding="utf-8")
    assert "final.mdl" in codigo


def test_el_bat_no_pide_nada_al_usuario(bat):
    """Doble clic y ya. Solo el 'pause' final para que se pueda leer."""
    assert "set /p" not in bat
    assert "choice" not in bat
    assert bat.count("\npause") == 2     # uno por final: bien y mal


def test_el_bat_habla_y_pita(bat):
    """Quien lo ejecuta puede no ver la ventana."""
    assert "SpeechSynthesizer" in bat
    assert "console]::beep" in bat
    assert ":pitido_bien" in bat and ":pitido_mal" in bat


def test_el_bat_detecta_el_modelo_ya_instalado(bat):
    assert re.search(r'if exist "%DESTINO%\\%NOMBRE_MODELO%\\am\\final\.mdl"', bat)


def test_el_bat_rechaza_una_descarga_diminuta(bat):
    """Un zip de menos de un mega es una página de error, no el modelo."""
    assert "LSS 1000000" in bat


def test_todos_los_saltos_del_bat_tienen_destino(bat):
    etiquetas = set(re.findall(r"^:(\w+)", bat, re.M))
    saltos = set(re.findall(r"(?:goto|call) :(\w+)", bat))
    assert saltos - etiquetas - {"eof"} == set()


def test_el_bat_esta_en_el_instalador_y_en_el_zip():
    """Si no está en los dos, el usuario no recibe el .bat y no puede
    instalar el dictado. El ZIP lo arma scripts/empaquetar.py."""
    faltan = []
    for ruta in (RAIZ / "installer" / "VozClip.iss",
                 RAIZ / "scripts" / "empaquetar.py"):
        if "instalar_modelos.bat" not in ruta.read_text(encoding="utf-8"):
            faltan.append(ruta.relative_to(RAIZ).as_posix())
    assert not faltan, f"'instalar_modelos.bat' no aparece en: {', '.join(faltan)}"

def test_el_bat_esta_documentado():
    leeme = (RAIZ / "LEEME.txt").read_text(encoding="utf-8")
    guia = (RAIZ / "GUIA_RAPIDA.txt").read_text(encoding="utf-8")
    assert "instalar_modelos.bat" in leeme
    assert "instalar_modelos.bat" in guia


# ===========================================================================
# 3. Detección del modelo instalado
# ===========================================================================
def _modelo_falso(carpeta: Path, nombre: str = "vosk-model-small-es-0.42") -> Path:
    """Reproduce la estructura que deja el .bat."""
    modelo = carpeta / nombre
    (modelo / "am").mkdir(parents=True)
    (modelo / "am" / "final.mdl").write_bytes(b"fingido")
    (modelo / "conf").mkdir()
    return modelo


def test_se_detecta_el_modelo_que_deja_el_bat(tmp_path):
    esperado = _modelo_falso(tmp_path)
    assert dictado.localizar_modelo(tmp_path) == esperado


def test_no_se_detecta_nada_en_una_carpeta_vacia(tmp_path):
    assert dictado.localizar_modelo(tmp_path) is None


def test_una_descarga_a_medias_no_cuenta(tmp_path):
    """Si el .bat se cortó a mitad, queda una carpeta sin am\\final.mdl."""
    (tmp_path / "vosk-model-small-es-0.42").mkdir()
    (tmp_path / "vosk-model-small-es-0.42" / "README").write_text("a medias")
    assert dictado.localizar_modelo(tmp_path) is None


def test_el_servicio_sabe_decir_que_falta_el_modelo(tmp_path, monkeypatch):
    monkeypatch.setattr(dictado, "localizar_modelo", lambda *a, **k: None)
    servicio = dictado.ServicioDictado(notificar=lambda t, d: None,
                                       ajustes={"activado": True})
    motivo = servicio.motivo_no_disponible()
    if motivo is not None:          # depende de si vosk está instalado
        assert "modelo" in motivo.lower()


def test_el_motor_encuentra_el_modelo_del_bat(tmp_path, monkeypatch):
    """Con el modelo donde lo deja el .bat, MotorVosk ya no protesta al
    construirse: solo fallaría al cargar, si el contenido es falso."""
    esperado = _modelo_falso(tmp_path)
    monkeypatch.setattr(dictado, "carpeta_modelos", lambda: tmp_path)

    try:
        motor = dictado.MotorVosk()
    except dictado.ErrorDictado:
        pytest.fail("MotorVosk no encontró un modelo con la estructura correcta")
    assert motor.ruta_modelo == esperado


# ===========================================================================
# El modelo incluido en la descarga
# ===========================================================================
def test_se_busca_junto_al_programa_y_en_el_usuario():
    """Dos sitios, dos formas de tenerlo: incluido en la descarga, o
    instalado después con el .bat."""
    carpetas = dictado.carpetas_de_modelos()
    assert dictado.carpeta_junto_al_programa() in carpetas
    assert dictado.carpeta_modelos() in carpetas


def test_la_ruta_configurada_manda():
    carpetas = dictado.carpetas_de_modelos("/opt/vosk/es")
    assert carpetas[0] == Path("/opt/vosk/es")


def test_no_se_repiten_carpetas():
    carpetas = dictado.carpetas_de_modelos()
    assert len(carpetas) == len(set(carpetas))


def test_se_encuentra_el_modelo_que_viene_incluido(tmp_path, monkeypatch):
    """El caso que fallaba: el modelo viaja junto al .exe y el programa
    decía que faltaba, porque solo miraba en la carpeta del usuario."""
    junto = tmp_path / "junto_al_exe" / "modelos"
    _modelo_falso(junto)
    vacia = tmp_path / "usuario"

    monkeypatch.setattr(dictado, "carpeta_junto_al_programa", lambda: junto)
    monkeypatch.setattr(dictado, "carpeta_modelos", lambda: vacia)

    encontrado = dictado.localizar_modelo()
    assert encontrado is not None
    assert junto in encontrado.parents


def test_gana_el_incluido_sobre_el_del_usuario(tmp_path, monkeypatch):
    junto = tmp_path / "junto" / "modelos"
    usuario = tmp_path / "usuario" / "modelos"
    _modelo_falso(junto, "modelo-incluido")
    _modelo_falso(usuario, "modelo-del-usuario")

    monkeypatch.setattr(dictado, "carpeta_junto_al_programa", lambda: junto)
    monkeypatch.setattr(dictado, "carpeta_modelos", lambda: usuario)

    assert dictado.localizar_modelo().name == "modelo-incluido"


def test_la_carpeta_puede_ser_el_modelo_mismo(tmp_path):
    """Vale tanto `modelos/vosk-.../` como apuntar directamente al modelo."""
    modelo = _modelo_falso(tmp_path)
    assert dictado.localizar_modelo(modelo) == modelo
    assert dictado.localizar_modelo(tmp_path) == modelo


def test_un_modelo_a_medias_no_cuenta(tmp_path):
    incompleto = tmp_path / "vosk-model-small-es-0.42"
    (incompleto / "am").mkdir(parents=True)     # sin final.mdl
    assert dictado.es_modelo_valido(incompleto) is False
    assert dictado.localizar_modelo(tmp_path) is None


# ===========================================================================
# El script de descarga que usa la compilación
# ===========================================================================
DESCARGADOR = RAIZ / "scripts" / "descargar_modelo.py"


def _zip_de_modelo(carpeta: Path) -> Path:
    """Un zip con la estructura real de un modelo de Vosk."""
    modelo = carpeta / "vosk-model-small-es-0.42"
    (modelo / "am").mkdir(parents=True)
    (modelo / "am" / "final.mdl").write_bytes(b"x" * 2_000_000)
    (modelo / "conf").mkdir()
    (modelo / "conf" / "model.conf").write_text("fingido")

    destino = carpeta / "modelo.zip"
    with zipfile.ZipFile(destino, "w") as z:
        for f in modelo.rglob("*"):
            if f.is_file():
                z.write(f, f.relative_to(carpeta))
    shutil.rmtree(modelo)
    return destino


def test_el_descargador_existe():
    assert DESCARGADOR.exists()


def test_el_descargador_instala_y_el_programa_lo_encuentra(tmp_path):
    """Ciclo completo sin internet: se sirve el zip desde el disco."""
    import sys

    origen = _zip_de_modelo(tmp_path)
    destino = tmp_path / "paquete" / "modelos"

    resultado = subprocess.run(
        [sys.executable, str(DESCARGADOR),
         "--url", origen.as_uri(), "--destino", str(destino)],
        capture_output=True, text=True, timeout=120, cwd=str(RAIZ),
    )
    assert resultado.returncode == 0, resultado.stdout + resultado.stderr
    assert dictado.localizar_modelo(destino) is not None


def test_el_descargador_no_repite_si_ya_esta(tmp_path):
    import sys

    origen = _zip_de_modelo(tmp_path)
    destino = tmp_path / "modelos"
    orden = [sys.executable, str(DESCARGADOR),
             "--url", origen.as_uri(), "--destino", str(destino)]

    subprocess.run(orden, capture_output=True, timeout=120, cwd=str(RAIZ))
    segunda = subprocess.run(orden, capture_output=True, text=True,
                             timeout=120, cwd=str(RAIZ))
    assert segunda.returncode == 0
    assert "ya estaba" in segunda.stdout


def test_el_descargador_rechaza_una_descarga_diminuta(tmp_path):
    """Menos de un mega es una página de error, no el modelo."""
    import sys

    falso = tmp_path / "error.zip"
    falso.write_bytes(b"404 Not Found")

    resultado = subprocess.run(
        [sys.executable, str(DESCARGADOR),
         "--url", falso.as_uri(), "--destino", str(tmp_path / "m")],
        capture_output=True, text=True, timeout=60, cwd=str(RAIZ),
    )
    assert resultado.returncode == 1
    assert "no es el" in resultado.stderr or "bytes" in resultado.stderr


def test_el_descargador_usa_la_misma_url_que_el_resto():
    from vozclip import modelo as modmodelo

    codigo = DESCARGADOR.read_text(encoding="utf-8")
    assert modmodelo.URL_MODELO in codigo


# ===========================================================================
# El modelo en el paquete y en el instalador
# ===========================================================================
def _workflow_o_saltar(nombre: str) -> str:
    ruta = RAIZ / ".github" / "workflows" / nombre
    if not ruta.exists():
        pytest.skip(f"Falta {nombre}: créalo con SUBIR_A_GITHUB.html")
    return ruta.read_text(encoding="utf-8")


def test_la_compilacion_descarga_el_modelo():
    yml = _workflow_o_saltar("release.yml")
    assert "scripts/descargar_modelo.py" in yml
    codigo = (RAIZ / "scripts" / "empaquetar.py").read_text(encoding="utf-8")
    assert "final.mdl" in codigo          # el paquete incluye el modelo si está

def test_si_falla_la_descarga_el_paquete_se_publica_igual():
    """Mejor un paquete sin modelo que ningún paquete: el .bat sigue ahí."""
    yml = _workflow_o_saltar("release.yml")
    assert "continue-on-error: true" in yml
    codigo = (RAIZ / "scripts" / "empaquetar.py").read_text(encoding="utf-8")
    assert "instalar_modelos.bat" in codigo

def test_el_instalador_copia_el_modelo_junto_al_programa():
    iss = (RAIZ / "installer" / "VozClip.iss").read_text(encoding="utf-8")
    assert r'DestDir: "{app}\modelos"' in iss
    # Y se construye igual aunque no haya modelo
    assert "skipifsourcedoesntexist" in iss


# ===========================================================================
# INSTALAR.bat: un doble clic desde el código fuente
# ===========================================================================
INSTALAR = RAIZ / "INSTALAR.bat"
INICIAR = RAIZ / "Iniciar VozClip.bat"


def test_instalar_bat_existe_en_la_raiz():
    """En la raíz, con mayúsculas: es lo primero que se ve al descomprimir."""
    assert INSTALAR.exists()
    assert INICIAR.exists()


def test_instalar_bat_es_ascii_y_crlf():
    for ruta in (INSTALAR, INICIAR):
        crudo = ruta.read_bytes()
        assert all(b < 128 for b in crudo), ruta.name
        assert b"\n" not in crudo.replace(b"\r\n", b""), ruta.name


def test_instalar_bat_hace_los_cinco_pasos():
    s = INSTALAR.read_text(encoding="ascii")
    for paso in ("winget install", "-m venv .venv", "requirements.txt",
                 "descargar_modelo.py --usuario", "CreateShortcut"):
        assert paso in s, f"Falta el paso: {paso}"


def test_instalar_bat_habla_y_pita():
    s = INSTALAR.read_text(encoding="ascii")
    assert "SpeechSynthesizer" in s
    assert ":pitido_bien" in s and ":pitido_mal" in s


def test_instalar_bat_no_pide_nada():
    s = INSTALAR.read_text(encoding="ascii")
    assert "set /p" not in s
    assert "choice" not in s


def test_instalar_bat_exige_python_moderno():
    """Menos de 3.9 no vale: el código usa sintaxis nueva."""
    s = INSTALAR.read_text(encoding="ascii")
    assert "sys.version_info >= (3,9)" in s


def test_todos_los_saltos_de_instalar_tienen_destino():
    s = INSTALAR.read_text(encoding="ascii")
    etiquetas = set(re.findall(r"^:(\w+)", s, re.M))
    saltos = set(re.findall(r"(?:goto|call) :(\w+)", s))
    assert saltos - etiquetas - {"eof"} == set()


def test_el_lanzador_usa_pythonw():
    """pythonw no abre consola: solo la ventana de VozClip."""
    s = INICIAR.read_text(encoding="ascii")
    assert "pythonw.exe" in s
    assert "-m vozclip" in s


def test_instalar_usa_los_scripts_que_ya_estan_probados():
    """El .bat no duplica lógica: llama a descargar_modelo.py, que tiene
    sus propios tests."""
    s = INSTALAR.read_text(encoding="ascii")
    assert "scripts\\descargar_modelo.py" in s
    assert "Invoke-WebRequest" not in s


def test_gitattributes_protege_los_saltos_de_los_bat():
    """Regresión de un fallo real: Git Bash en Windows viene con
    core.autocrlf=true y al commitear convirtió los .bat a LF. En el
    repositorio quedaron con saltos de Linux, y cmd se pierde con los
    `goto` cuando un .bat tiene LF suelto.

    `.gitattributes` lo fija por archivo y deja de depender de cómo tenga
    cada uno configurado su Git.
    """
    ruta = RAIZ / ".gitattributes"
    assert ruta.exists(), "Falta .gitattributes: los .bat se subirán con LF"
    contenido = ruta.read_text(encoding="utf-8")
    assert "*.bat text eol=crlf" in contenido
    assert "*.py text eol=lf" in contenido
