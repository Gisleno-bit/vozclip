"""Exportación a LibreOffice Writer en formato OpenDocument (.odt).

=============================================================================
POR QUÉ ODT Y POR QUÉ SIN LIBRERÍAS
=============================================================================
LibreOffice abre .docx, pero .odt es SU formato: no hay conversión por medio
y las medidas llegan exactas. Y un .odt es, por dentro, un zip con unos
pocos XML. Generarlo a mano con `zipfile` y cadenas de texto son ochenta
líneas, y evita meter odfpy (y sus dependencias) en el ejecutable por un
solo formato.

El formato se aplica igual que en la exportación a Word: cada párrafo se
clasifica solo (raya al principio = diálogo, si no = narrador) y recibe el
estilo de la plantilla con las medidas del documento de estilo de Julián.
=============================================================================

Estructura mínima de un .odt válido:

    mimetype               "application/vnd.oasis.opendocument.text",
                           SIN comprimir y el PRIMERO del zip (lo exige
                           la norma; si no, LibreOffice dice que el
                           archivo está dañado)
    META-INF/manifest.xml  lista de lo que hay dentro
    styles.xml             estilos de párrafo con sus medidas
    content.xml            los párrafos, cada uno apuntando a su estilo
"""

from __future__ import annotations

import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from .exportar_word import es_dialogo
from .fuentes import ErrorFuente
from .plantillas import FormatoWord, Plantilla

MIMETYPE = "application/vnd.oasis.opendocument.text"

_NS = (
    'xmlns:office="urn:oasis:names:tc:opendocument:xmlns:office:1.0" '
    'xmlns:style="urn:oasis:names:tc:opendocument:xmlns:style:1.0" '
    'xmlns:text="urn:oasis:names:tc:opendocument:xmlns:text:1.0" '
    'xmlns:fo="urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0" '
    'office:version="1.2"'
)


def exportar(
    texto: str,
    ruta: str | Path,
    plantilla: Plantilla,
    titulo: str | None = None,
) -> Path:
    """Escribe el documento en .odt con el formato de la plantilla."""
    ruta = Path(ruta).expanduser()
    ruta.parent.mkdir(parents=True, exist_ok=True)

    narrador = plantilla.formato_parrafo or FormatoWord()
    dialogo = plantilla.formato_diálogo or narrador

    estilos = _styles_xml(narrador, dialogo)
    contenido = _content_xml(texto, titulo)

    try:
        with zipfile.ZipFile(ruta, "w") as z:
            # El mimetype va primero y sin comprimir. Es obligatorio.
            z.writestr(
                zipfile.ZipInfo("mimetype"), MIMETYPE,
                compress_type=zipfile.ZIP_STORED,
            )
            z.writestr("META-INF/manifest.xml", _manifest_xml(),
                       compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("styles.xml", estilos, compress_type=zipfile.ZIP_DEFLATED)
            z.writestr("content.xml", contenido, compress_type=zipfile.ZIP_DEFLATED)
    except OSError as e:
        raise ErrorFuente(
            f"No he podido guardar {ruta.name}: {e.strerror or 'error de disco'}"
        ) from e

    return ruta


# ---------------------------------------------------------------------------
# Las piezas del zip
# ---------------------------------------------------------------------------
def _manifest_xml() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<manifest:manifest '
        'xmlns:manifest="urn:oasis:names:tc:opendocument:xmlns:manifest:1.0" '
        'manifest:version="1.2">\n'
        f' <manifest:file-entry manifest:full-path="/" manifest:media-type="{MIMETYPE}"/>\n'
        ' <manifest:file-entry manifest:full-path="content.xml" manifest:media-type="text/xml"/>\n'
        ' <manifest:file-entry manifest:full-path="styles.xml" manifest:media-type="text/xml"/>\n'
        '</manifest:manifest>\n'
    )


def _propiedades(formato: FormatoWord) -> str:
    """Traduce un FormatoWord a atributos fo:* de OpenDocument."""
    atributos = []

    if formato.sangria_izquierda_cm:
        atributos.append(f'fo:margin-left="{formato.sangria_izquierda_cm}cm"')

    # Sangría francesa = primera línea negativa, igual que en Word: la raya
    # sale al margen y el resto del diálogo queda alineado debajo.
    if formato.sangria_francesa_cm:
        atributos.append(f'fo:text-indent="-{formato.sangria_francesa_cm}cm"')
    elif formato.primera_linea_cm:
        atributos.append(f'fo:text-indent="{formato.primera_linea_cm}cm"')

    if formato.espacio_posterior_pt:
        atributos.append(f'fo:margin-bottom="{formato.espacio_posterior_pt}pt"')

    # "Mínimo" en LibreOffice es style:line-height-at-least. Con
    # fo:line-height fijo se recortarían las tildes.
    if formato.interlineado == "minimo":
        atributos.append('style:line-height-at-least="0.5cm"')

    if formato.alineacion == "justificada":
        atributos.append('fo:text-align="justify"')

    return " ".join(atributos)


def _styles_xml(narrador: FormatoWord, dialogo: FormatoWord) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<office:document-styles {_NS}>\n'
        ' <office:styles>\n'
        '  <style:style style:name="Narrador" style:family="paragraph" '
        'style:display-name="Narrador">\n'
        f'   <style:paragraph-properties {_propiedades(narrador)}/>\n'
        '  </style:style>\n'
        '  <style:style style:name="Dialogo" style:family="paragraph" '
        'style:display-name="Diálogo">\n'
        f'   <style:paragraph-properties {_propiedades(dialogo)}/>\n'
        '  </style:style>\n'
        '  <style:style style:name="Titulo" style:family="paragraph" '
        'style:display-name="Título">\n'
        '   <style:paragraph-properties fo:text-align="center" fo:margin-bottom="24pt"/>\n'
        '   <style:text-properties fo:font-weight="bold" fo:font-size="16pt"/>\n'
        '  </style:style>\n'
        ' </office:styles>\n'
        '</office:document-styles>\n'
    )


def _content_xml(texto: str, titulo: str | None) -> str:
    parrafos = []
    if titulo:
        parrafos.append(f'   <text:p text:style-name="Titulo">{escape(titulo)}</text:p>')

    for linea in _partir_en_parrafos(texto):
        estilo = "Dialogo" if es_dialogo(linea) else "Narrador"
        parrafos.append(
            f'   <text:p text:style-name="{estilo}">{escape(linea.strip())}</text:p>'
        )

    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<office:document-content {_NS}>\n'
        ' <office:body>\n'
        '  <office:text>\n'
        + "\n".join(parrafos) + "\n"
        '  </office:text>\n'
        ' </office:body>\n'
        '</office:document-content>\n'
    )


def _partir_en_parrafos(texto: str) -> list[str]:
    """Cada línea no vacía es un párrafo; las vacías se descartan porque la
    separación la da el margen inferior, no una línea en blanco."""
    return [ln for ln in texto.replace("\r\n", "\n").split("\n") if ln.strip()]


# ---------------------------------------------------------------------------
# Lectura, para poder comprobar lo que se ha escrito
# ---------------------------------------------------------------------------
def leer(ruta: str | Path) -> dict:
    """Abre un .odt y devuelve sus párrafos y estilos. Sirve para los tests
    y para verificar de oído qué se ha exportado."""
    import xml.etree.ElementTree as ET

    ns = {
        "office": "urn:oasis:names:tc:opendocument:xmlns:office:1.0",
        "style": "urn:oasis:names:tc:opendocument:xmlns:style:1.0",
        "text": "urn:oasis:names:tc:opendocument:xmlns:text:1.0",
        "fo": "urn:oasis:names:tc:opendocument:xmlns:xsl-fo-compatible:1.0",
    }
    with zipfile.ZipFile(ruta) as z:
        primero = z.infolist()[0]
        mimetype = z.read("mimetype").decode()
        contenido = ET.fromstring(z.read("content.xml"))
        estilos = ET.fromstring(z.read("styles.xml"))

    parrafos = [
        {
            "estilo": p.get(f"{{{ns['text']}}}style-name"),
            "texto": "".join(p.itertext()),
        }
        for p in contenido.iter(f"{{{ns['text']}}}p")
    ]

    propiedades = {}
    for estilo in estilos.iter(f"{{{ns['style']}}}style"):
        nombre = estilo.get(f"{{{ns['style']}}}name")
        props = estilo.find(f"{{{ns['style']}}}paragraph-properties")
        propiedades[nombre] = dict(props.attrib) if props is not None else {}

    return {
        "mimetype": mimetype,
        "mimetype_primero": primero.filename == "mimetype",
        "mimetype_sin_comprimir": primero.compress_type == zipfile.ZIP_STORED,
        "parrafos": parrafos,
        "estilos": propiedades,
    }
