"""Plantillas de guion y diálogo.

Cada plantilla es texto con marcas `|` donde el escritor debe escribir. Al
insertarla, las marcas se quitan y se guardan sus posiciones: el cursor va a
la primera, y con `Ctrl+Alt+T` se salta a la siguiente.

Las sangrías siguen las convenciones reales de cada formato:

  * Teatro: personaje en mayúsculas al margen, acotaciones entre paréntesis
    y el diálogo con sangría.
  * Cine (formato americano estándar): encabezado de escena al margen,
    nombre del personaje muy sangrado, acotación algo menos, diálogo en el
    centro. Es lo que esperan las productoras.
  * Narrativo: diálogo con raya y verbo dicendi, según la norma española.
"""

from __future__ import annotations

from dataclasses import dataclass, field

MARCA = "|"

# ===========================================================================
# EL FORMATO REAL DE JULIÁN
# ===========================================================================
# Estas medidas vienen de su documento de estilo, y son medidas de WORD:
#
#   Diálogos con raya:  sangría izquierda 0,63 cm con sangría francesa 0,63,
#                       espacio posterior 18 pt, interlineado mínimo.
#   Narrador:           primera línea 1,25 cm, espacio posterior 18 pt,
#                       justificado.
#
# El texto plano NO puede guardar nada de esto: no tiene centímetros, ni
# puntos de espaciado, ni justificación. Por eso hay dos representaciones:
#
#   1. En el editor de VozClip, las sangrías se aproximan con espacios, para
#      que al oír "línea 5" el texto esté donde toca y no se descuadre.
#   2. Al exportar a Word (Ctrl+Alt+W), se aplican las medidas EXACTAS. Ahí
#      es donde el formato de Julián existe de verdad.
#
# Un carácter de fuente monoespaciada de 12 puntos mide una décima de
# pulgada, o sea 0,254 cm. Con eso se traducen los centímetros a espacios.
CM_POR_CARACTER = 0.254


def cm_a_caracteres(centimetros: float) -> int:
    """Traduce una sangría de Word a espacios de texto plano."""
    return max(0, round(centimetros / CM_POR_CARACTER))


@dataclass(frozen=True)
class FormatoWord:
    """Formato de párrafo de Word, para exportar con las medidas exactas."""

    sangria_izquierda_cm: float = 0.0
    sangria_francesa_cm: float = 0.0     # sangría francesa (negativa en Word)
    primera_linea_cm: float = 0.0
    espacio_posterior_pt: float = 0.0
    interlineado: str = "sencillo"       # "sencillo" o "minimo"
    alineacion: str = "izquierda"        # "izquierda" o "justificada"


@dataclass(frozen=True)
class Plantilla:
    clave: str
    nombre: str            # nombre que se dice en voz alta
    descripcion: str
    cuerpo: str            # texto con marcas |
    sangria_parrafo: str = "    "   # lo que inserta "aplicar sangría"

    # Formato de Word para el cuerpo del texto y para los diálogos. Se usa
    # al exportar a .docx; en el editor se aproxima con espacios.
    formato_parrafo: FormatoWord | None = None
    formato_diálogo: FormatoWord | None = None

    # Cómo empieza un diálogo nuevo en esta plantilla
    marca_dialogo: str = "—"      # lo que se escribe antes de hablar
    sangria_dialogo: str = ""     # espacios ANTES de la marca (0,63 cm = 2)


@dataclass
class Insercion:
    """Resultado de preparar una plantilla para pegarla."""

    texto: str                          # ya sin marcas
    posiciones: list[int] = field(default_factory=list)  # dónde estaban


# ---------------------------------------------------------------------------
# Catálogo
# ---------------------------------------------------------------------------

# --- Los dos formatos del documento de estilo de Julián -------------------
FORMATO_DIALOGO_JULIAN = FormatoWord(
    sangria_izquierda_cm=0.63,
    sangria_francesa_cm=0.63,     # la raya queda al margen, el resto sangrado
    espacio_posterior_pt=18,
    interlineado="minimo",
    alineacion="izquierda",
)

FORMATO_NARRADOR_JULIAN = FormatoWord(
    primera_linea_cm=1.25,        # sangría de primera línea, sin raya
    espacio_posterior_pt=18,
    interlineado="minimo",
    alineacion="justificada",
)

# Los mismos, traducidos a espacios para el editor de texto plano
SANGRIA_DIALOGO = " " * cm_a_caracteres(0.63)      # 2 espacios
SANGRIA_NARRADOR = " " * cm_a_caracteres(1.25)     # 5 espacios


NOVELA = Plantilla(
    clave="novela",
    nombre="novela con diálogos",
    descripcion=(
        "El formato de Julián: diálogos con raya y sangría francesa, "
        "narrador con primera línea sangrada y justificado."
    ),
    cuerpo=(
        f"{SANGRIA_NARRADOR}|\n"
        "\n"
        f"{SANGRIA_DIALOGO}—|\n"
    ),
    sangria_parrafo=SANGRIA_NARRADOR,
    formato_parrafo=FORMATO_NARRADOR_JULIAN,
    formato_diálogo=FORMATO_DIALOGO_JULIAN,
    marca_dialogo="—",
    sangria_dialogo=SANGRIA_DIALOGO,
)

NARRATIVO = Plantilla(
    clave="narrativo",
    nombre="diálogo narrativo",
    descripcion="Sangría de cero coma sesenta y tres y raya, sin nada más.",
    cuerpo=f"{SANGRIA_DIALOGO}—|",
    sangria_parrafo=SANGRIA_NARRADOR,
    formato_parrafo=FORMATO_NARRADOR_JULIAN,
    formato_diálogo=FORMATO_DIALOGO_JULIAN,
    marca_dialogo="—",
    sangria_dialogo=SANGRIA_DIALOGO,
)

ESCALETA = Plantilla(
    clave="escaleta",
    nombre="escaleta",
    descripcion="Bloque para planificar una secuencia antes de escribirla.",
    cuerpo=(
        "SECUENCIA |\n"
        "  Lugar: |\n"
        "  Personajes: |\n"
        "  Qué ocurre: |\n"
        "  Qué cambia al final: |\n"
        "\n"
    ),
    sangria_parrafo="  ",
    sangria_dialogo=SANGRIA_DIALOGO,
)

CATALOGO: dict[str, Plantilla] = {
    p.clave: p for p in (NOVELA, NARRATIVO, ESCALETA)
}

# La novela va primera porque es el formato propio de Julián.
#
# Las plantillas de teatro y cine se han retirado. Eran las únicas que
# insertaban un nombre de PERSONAJE, y con un config.json antiguo que
# tuviera "teatro" guardado, F3 seguía metiéndolo por mucho que se
# arreglara el formato de diálogo. Al quitarlas, `obtener` devuelve la de
# novela para cualquier clave desconocida, así que los ajustes viejos se
# corrigen solos al arrancar.
ORDEN = ["novela", "narrativo", "escaleta"]


def obtener(clave: str) -> Plantilla:
    """Devuelve una plantilla por su clave; si no existe, la de novela."""
    return CATALOGO.get(clave, NOVELA)


def siguiente_clave(actual: str) -> str:
    """Rota a la siguiente plantilla del catálogo."""
    try:
        i = ORDEN.index(actual)
    except ValueError:
        return ORDEN[0]
    return ORDEN[(i + 1) % len(ORDEN)]


def preparar(plantilla: Plantilla | str) -> Insercion:
    """Quita las marcas `|` y apunta en qué posición estaba cada una.

    Ejemplo:
        preparar("Hola |mundo|")
        -> Insercion(texto="Hola mundo", posiciones=[5, 10])
    """
    if isinstance(plantilla, Plantilla):
        cuerpo = plantilla.cuerpo
    else:
        cuerpo = plantilla

    salida: list[str] = []
    posiciones: list[int] = []
    largo = 0

    for caracter in cuerpo:
        if caracter == MARCA:
            posiciones.append(largo)
        else:
            salida.append(caracter)
            largo += 1

    return Insercion(texto="".join(salida), posiciones=posiciones)


def describir(plantilla: Plantilla) -> str:
    """Frase que se dice en voz alta al cambiar de plantilla."""
    return f"Plantilla: {plantilla.nombre}. {plantilla.descripcion}"
