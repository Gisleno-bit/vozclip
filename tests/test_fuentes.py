"""Tests de la lectura de archivos."""

import pytest

from vozclip import fuentes


def test_lee_txt_utf8(tmp_path):
    f = tmp_path / "carta.txt"
    f.write_text("Estimado señor: le escribo con acentuación.", encoding="utf-8")
    assert "acentuación" in fuentes.leer_fichero(f)


def test_lee_txt_windows_1252(tmp_path):
    f = tmp_path / "viejo.txt"
    f.write_bytes("Año de gestión".encode("cp1252"))
    assert "Año" in fuentes.leer_fichero(f)


def test_archivo_inexistente(tmp_path):
    with pytest.raises(fuentes.ErrorFuente, match="No encuentro"):
        fuentes.leer_fichero(tmp_path / "fantasma.txt")


def test_extension_no_soportada(tmp_path):
    f = tmp_path / "foto.jpg"
    f.write_bytes(b"\xff\xd8\xff")
    with pytest.raises(fuentes.ErrorFuente, match="No sé abrir"):
        fuentes.leer_fichero(f)


def test_archivo_vacio(tmp_path):
    f = tmp_path / "vacio.txt"
    f.write_text("   ", encoding="utf-8")
    with pytest.raises(fuentes.ErrorFuente, match="no contiene texto"):
        fuentes.leer_fichero(f)


def test_corta_por_el_limite(tmp_path):
    f = tmp_path / "enorme.txt"
    f.write_text("a" * 5000, encoding="utf-8")
    salida = fuentes.leer_fichero(f, max_caracteres=100)
    assert "El archivo continúa" in salida
    assert len(salida) < 500


def test_directorio_no_vale(tmp_path):
    with pytest.raises(fuentes.ErrorFuente, match="no es un archivo"):
        fuentes.leer_fichero(tmp_path)


def test_lee_docx(tmp_path):
    docx = pytest.importorskip("docx", reason="python-docx no instalado")
    ruta = tmp_path / "informe.docx"
    documento = docx.Document()
    documento.add_paragraph("Primer párrafo del informe.")
    documento.add_paragraph("Segundo párrafo.")
    documento.save(str(ruta))

    salida = fuentes.leer_fichero(ruta)
    assert "Primer párrafo del informe." in salida
    assert "Segundo párrafo." in salida
