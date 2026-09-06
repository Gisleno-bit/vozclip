"""Corrección de palabras dictadas, por voz.

=============================================================================
LA IDEA
=============================================================================
Cuando el reconocimiento se equivoca en una palabra, repetir todo el párrafo
es lento y corregirlo a mano sin ver la pantalla es casi imposible. Aquí se
corrige DICIENDO EL CAMBIO:

    "cambia casa por cosa"          -> sustituye casa por cosa
    "cambia no me lo creo por no lo creo"   -> frases enteras también
    "borra además"                  -> quita una palabra
    "léelo"                         -> lee el párrafo numerando las palabras,
                                       para cuando la palabra mal reconocida
                                       es irreconocible
    "la tres por cosa"              -> cambia la palabra número tres
    "de la dos a la cuatro por ..." -> un rango
    "cancela"                       -> deja todo como estaba

Este módulo no sabe nada de ventanas ni de micrófonos: recibe texto y
devuelve texto. Por eso se puede probar entero sin abrir nada.
=============================================================================
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

# ---------------------------------------------------------------------------
# Palabras
# ---------------------------------------------------------------------------
# Una palabra es un tramo de letras o cifras, con apóstrofos o guiones
# interiores. La puntuación pegada NO forma parte de la palabra: así, al
# cambiar "casa" en "casa," se conserva la coma.
_PALABRA = re.compile(r"[\w]+(?:['’\-][\w]+)*", re.UNICODE)


@dataclass(frozen=True)
class Palabra:
    indice: int      # empezando en 1, que es como se dice
    texto: str
    inicio: int      # posición en el texto original
    fin: int


def tokenizar(texto: str) -> list[Palabra]:
    return [
        Palabra(i + 1, m.group(), m.start(), m.end())
        for i, m in enumerate(_PALABRA.finditer(texto))
    ]


def enumerar(texto: str, maximo: int = 60) -> str:
    """Frase para leer el párrafo con cada palabra numerada.

    Se dice "uno, casa. dos, azul." y no "palabra uno: casa": la mitad de
    sílabas, y el número siempre delante, que es lo que hay que retener.
    """
    palabras = tokenizar(texto)
    if not palabras:
        return "No hay palabras."
    trozos = [f"{p.indice}, {p.texto}" for p in palabras[:maximo]]
    frase = ". ".join(trozos) + "."
    if len(palabras) > maximo:
        frase += f" Y {len(palabras) - maximo} más."
    return frase


# ---------------------------------------------------------------------------
# Números dichos en castellano
# ---------------------------------------------------------------------------
_UNIDADES = {
    "cero": 0, "uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "diecisiete": 17, "dieciocho": 18, "diecinueve": 19,
    "veinte": 20, "veintiuno": 21, "veintiuna": 21, "veintidos": 22,
    "veintitres": 23, "veinticuatro": 24, "veinticinco": 25, "veintiseis": 26,
    "veintisiete": 27, "veintiocho": 28, "veintinueve": 29,
}
_DECENAS = {
    "treinta": 30, "cuarenta": 40, "cincuenta": 50, "sesenta": 60,
    "setenta": 70, "ochenta": 80, "noventa": 90,
}


def _sin_acentos(texto: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFD", texto)
        if unicodedata.category(c) != "Mn"
    )


def numero(palabras: list[str]) -> int | None:
    """Convierte ["treinta", "y", "dos"] o ["32"] en 32. None si no lo es."""
    limpias = [_sin_acentos(p.lower()) for p in palabras if p.lower() != "y"]
    if not limpias:
        return None
    if len(limpias) == 1 and limpias[0].isdigit():
        return int(limpias[0])
    total = 0
    for pieza in limpias:
        if pieza in _DECENAS:
            total += _DECENAS[pieza]
        elif pieza in _UNIDADES:
            total += _UNIDADES[pieza]
        elif pieza.isdigit():
            total += int(pieza)
        else:
            return None
    return total


def _numeros_en(frase: str) -> list[int]:
    """Todos los números que aparecen en una frase, en orden."""
    encontrados: list[int] = []
    tokens = _sin_acentos(frase.lower()).split()
    i = 0
    while i < len(tokens):
        # Intento de número compuesto: "treinta y dos"
        if tokens[i] in _DECENAS and i + 2 < len(tokens) and tokens[i + 1] == "y":
            n = numero(tokens[i : i + 3])
            if n is not None:
                encontrados.append(n)
                i += 3
                continue
        n = numero([tokens[i]])
        if n is not None:
            encontrados.append(n)
        i += 1
    return encontrados


# ---------------------------------------------------------------------------
# Órdenes
# ---------------------------------------------------------------------------
@dataclass
class Orden:
    tipo: str                       # cambiar, borrar, numerar, cancelar, deshacer, desconocida
    buscar: str = ""                # palabra o frase a localizar
    poner: str = ""                 # por qué sustituirla
    indices: list[int] = field(default_factory=list)   # o qué números
    con_verbo: bool = False         # ¿empezaba por "cambia", "borra"...?

    # Con verbo, la orden es inequívoca y se puede aceptar en mitad de un
    # dictado normal. Sin verbo ("casa por cosa") solo vale dentro de F9:
    # en prosa, "fue por pan" parecería una orden si "fue" está en el texto.


_PALABRAS_CAMBIAR = ("cambia", "cambiar", "sustituye", "sustituir", "reemplaza",
                     "reemplazar", "pon", "poner", "corrige", "corregir")
_PALABRAS_BORRAR = ("borra", "borrar", "quita", "quitar", "elimina", "eliminar")
_PALABRAS_NUMERAR = ("leelo", "lee", "numera", "enumera", "numerar", "enumerar",
                     "leer", "repite", "repitelo")
_PALABRAS_CANCELAR = ("cancela", "cancelar", "nada", "dejalo", "olvidalo")
_PALABRAS_DESHACER = ("deshacer", "deshaz", "deshacelo", "atras")

_RANGO = re.compile(
    r"^(?:de\s+)?(?:la\s+|el\s+)?(?:palabra\s+)?(?P<a>[\w\s]+?)\s+(?:a|hasta)\s+"
    r"(?:la\s+|el\s+)?(?:palabra\s+)?(?P<b>[\w\s]+?)$",
    re.UNICODE,
)


def _limpiar(texto: str) -> str:
    return re.sub(r"[.,;:!?¿¡]+$", "", texto.strip()).strip()


def _quitar_prefijo(texto: str, prefijos: tuple[str, ...]) -> str | None:
    """Si el texto empieza por alguna de las palabras, la quita y devuelve
    el resto. Si no, None."""
    tokens = texto.split(maxsplit=1)
    if not tokens:
        return None
    primera = _sin_acentos(tokens[0].lower())
    if primera in prefijos:
        return tokens[1] if len(tokens) > 1 else ""
    return None


def _interpretar_objetivo(texto: str) -> tuple[str, list[int]]:
    """Distingue 'casa' (palabra) de 'la tres' o 'de la dos a la cuatro'
    (números). Devuelve (palabra_a_buscar, índices)."""
    limpio = _limpiar(texto)
    sin = _sin_acentos(limpio.lower())

    m = _RANGO.match(sin)
    if m:
        a = numero(m.group("a").split())
        b = numero(m.group("b").split())
        if a is not None and b is not None and a <= b:
            return "", list(range(a, b + 1))

    # "la tres", "la palabra tres", "la uno y la tres", "tres"
    recortado = re.sub(r"\b(la|el|las|los|palabra|palabras|numero)\b", " ", sin)
    numeros = _numeros_en(recortado)
    resto = re.sub(r"\b(y|e)\b", " ", recortado)
    solo_numeros = all(
        numero([t]) is not None for t in resto.split()
    ) and bool(resto.split())
    if numeros and solo_numeros:
        return "", numeros

    return limpio, []


def interpretar_orden(dicho: str) -> Orden:
    """Convierte lo que se ha dicho en una orden.

    Es tolerante: acepta "cambia casa por cosa", "casa por cosa",
    "sustituye la tres por cosa", "borra además", "léelo", "cancela"...
    """
    texto = _limpiar(dicho)
    if not texto:
        return Orden("desconocida")

    primera = _sin_acentos(texto.split()[0].lower())
    entero = _sin_acentos(texto.lower())

    # "no" solo cancela si es TODO lo dicho: "no sé" o "no dormí" no son
    # una cancelación.
    if primera in _PALABRAS_CANCELAR or entero == "no":
        return Orden("cancelar")

    # "borrar" a secas: en el flujo guiado significa borrar lo elegido
    if entero in _PALABRAS_BORRAR:
        return Orden("borrar")
    if primera in _PALABRAS_DESHACER:
        return Orden("deshacer")
    if primera in _PALABRAS_NUMERAR:
        return Orden("numerar")

    resto = _quitar_prefijo(texto, _PALABRAS_BORRAR)
    if resto is not None:
        buscar, indices = _interpretar_objetivo(resto)
        if buscar or indices:
            return Orden("borrar", buscar=buscar, indices=indices, con_verbo=True)
        return Orden("desconocida")

    con_verbo = True
    resto = _quitar_prefijo(texto, _PALABRAS_CAMBIAR)
    if resto is None:
        resto = texto        # "casa por cosa", sin verbo
        con_verbo = False

    # El separador es " por ". Se toma el ÚLTIMO, para que "cambia por
    # favor por por fin" no se rompa: lo de después es lo nuevo.
    partes = re.split(r"\s+por\s+", resto)
    if len(partes) >= 2:
        objetivo = " por ".join(partes[:-1]).strip()
        nuevo = partes[-1].strip()
        buscar, indices = _interpretar_objetivo(objetivo)
        if (buscar or indices) and nuevo:
            return Orden("cambiar", buscar=buscar, poner=nuevo, indices=indices,
                         con_verbo=con_verbo)

    return Orden("desconocida")


# ---------------------------------------------------------------------------
# Localizar y sustituir
# ---------------------------------------------------------------------------
@dataclass
class Coincidencia:
    inicio: int
    fin: int
    texto: str
    contexto: str        # unas palabras alrededor, para decirlas


def _comparable(texto: str) -> str:
    return _sin_acentos(texto.lower())


def localizar(texto: str, buscar: str, ambito: tuple[int, int] | None = None) -> list[Coincidencia]:
    """Dónde aparece una palabra o una secuencia de palabras.

    Sin distinguir mayúsculas ni acentos: el reconocedor no siempre los
    pone, y Julián no los va a dictar.
    """
    ini, fin = ambito if ambito else (0, len(texto))
    palabras = [p for p in tokenizar(texto) if p.inicio >= ini and p.fin <= fin]
    objetivo = [_comparable(p.texto) for p in tokenizar(buscar)]
    if not objetivo:
        return []

    encontradas: list[Coincidencia] = []
    n = len(objetivo)
    for i in range(len(palabras) - n + 1):
        ventana = palabras[i : i + n]
        if [_comparable(p.texto) for p in ventana] == objetivo:
            a, b = ventana[0].inicio, ventana[-1].fin
            encontradas.append(Coincidencia(a, b, texto[a:b], _contexto(texto, palabras, i, n)))
    return encontradas


def por_indices(texto: str, indices: list[int], ambito: tuple[int, int] | None = None) -> list[Coincidencia]:
    """Las palabras con esos números dentro del ámbito."""
    ini, fin = ambito if ambito else (0, len(texto))
    palabras = [p for p in tokenizar(texto) if p.inicio >= ini and p.fin <= fin]
    # Se renumeran dentro del ámbito: la palabra "3" es la tercera del párrafo
    resultado = []
    for k in sorted(set(indices)):
        if 1 <= k <= len(palabras):
            p = palabras[k - 1]
            resultado.append(Coincidencia(p.inicio, p.fin, p.texto,
                                          _contexto(texto, palabras, k - 1, 1)))
    return resultado


def _contexto(texto: str, palabras: list[Palabra], i: int, n: int, margen: int = 2) -> str:
    a = max(0, i - margen)
    b = min(len(palabras), i + n + margen)
    return " ".join(p.texto for p in palabras[a:b])


def _adaptar_mayusculas(original: str, nuevo: str) -> str:
    """Si lo que había empezaba en mayúscula, lo nuevo también."""
    if original[:1].isupper() and nuevo[:1].islower():
        return nuevo[0].upper() + nuevo[1:]
    return nuevo


def sustituir(texto: str, coincidencias: list[Coincidencia], nuevo: str) -> str:
    """Sustituye SOLO los tramos indicados. Todo lo demás queda intacto:
    sangrías, saltos, puntuación pegada. Se va de atrás adelante para que
    los índices anteriores no se muevan."""
    resultado = texto
    for c in sorted(coincidencias, key=lambda c: c.inicio, reverse=True):
        reemplazo = _adaptar_mayusculas(c.texto, nuevo) if nuevo else ""
        resultado = resultado[: c.inicio] + reemplazo + resultado[c.fin :]
        if not nuevo:
            resultado = _cerrar_hueco(resultado, c.inicio)
    return resultado


def _cerrar_hueco(texto: str, pos: int) -> str:
    """Tras borrar una palabra quedan dos espacios seguidos, o un espacio
    antes de una coma. Se cierra el hueco sin tocar nada más."""
    izquierda = texto[:pos]
    derecha = texto[pos:]
    if izquierda.endswith(" ") and (derecha.startswith(" ") or derecha[:1] in ",.;:!?)"):
        izquierda = izquierda[:-1]
    elif izquierda.endswith(" ") and derecha == "":
        izquierda = izquierda[:-1]
    return izquierda + derecha


# ---------------------------------------------------------------------------
# El ámbito: el párrafo donde se corrige
# ---------------------------------------------------------------------------
def ambito_parrafo(texto: str, cursor: int) -> tuple[int, int]:
    """El párrafo del cursor, o el último si el cursor está en blanco."""
    from .documento import rango_parrafo, ultimo_parrafo

    ini, fin = rango_parrafo(texto, cursor)
    if texto[ini:fin].strip():
        return ini, fin
    ultimo = ultimo_parrafo(texto)
    if not ultimo:
        return 0, len(texto)
    pos = texto.rfind(ultimo)
    return pos, pos + len(ultimo)


# ---------------------------------------------------------------------------
# Corregir en mitad de un dictado normal
# ---------------------------------------------------------------------------
def orden_durante_dictado(dicho: str, texto: str, ambito: tuple[int, int]) -> Orden | None:
    """Si lo dictado con F1 es una corrección inequívoca, devuelve la orden.

    Esto existe porque es lo que hace la gente: acaba de dictar, oye una
    palabra mal, y vuelve a pulsar la misma tecla para decir "cambia
    alpiste por rueda". Pedirle que cambie a otra tecla es un paso de más.

    Se exigen DOS cosas para no confundir prosa con órdenes:
      1. Que empiece por un verbo de corrección: cambia, sustituye,
         corrige, borra, quita... Sin verbo, "alpiste por rueda" se escribe
         tal cual, porque "fue por pan" también sería una orden.
      2. Que lo que se quiere cambiar ESTÉ en el párrafo (o que se dé por
         número). "Cambia de opinión y se va" es prosa: "de opinión y se
         va" no está en el texto.
    """
    orden = interpretar_orden(dicho)
    if orden.tipo not in ("cambiar", "borrar") or not orden.con_verbo:
        return None
    if orden.indices:
        return orden if por_indices(texto, orden.indices, ambito) else None
    return orden if localizar(texto, orden.buscar, ambito) else None


# ---------------------------------------------------------------------------
# Todo junto: aplicar una orden a un texto
# ---------------------------------------------------------------------------
@dataclass
class Resultado:
    texto: str                       # el texto tras aplicar (igual si no se aplicó)
    mensaje: str                     # qué decir en voz alta
    aplicado: bool = False
    opciones: list[Coincidencia] = field(default_factory=list)   # si hay que elegir
    cursor: int | None = None        # dónde dejar el cursor


def aplicar(texto: str, orden: Orden, ambito: tuple[int, int], eleccion: int | None = None) -> Resultado:
    """Aplica una orden. Si la palabra aparece varias veces, devuelve las
    opciones para preguntar; con `eleccion` se resuelve."""
    if orden.tipo == "numerar":
        return Resultado(texto, enumerar(texto[ambito[0]:ambito[1]]))
    if orden.tipo == "cancelar":
        return Resultado(texto, "Corrección cancelada.")
    if orden.tipo == "deshacer":
        return Resultado(texto, "deshacer")
    if orden.tipo == "desconocida":
        return Resultado(
            texto,
            "No he entendido el cambio. Di, por ejemplo: cambia casa por cosa. "
            "O di léelo para oír el párrafo numerado.",
        )

    if orden.indices:
        coincidencias = por_indices(texto, orden.indices, ambito)
        if not coincidencias:
            return Resultado(texto, f"El párrafo no tiene tantas palabras: solo hay "
                                    f"{len(por_indices(texto, list(range(1, 200)), ambito))}.")
        # Un rango ("de la tres a la cinco") es UN tramo, no tres palabras
        # sueltas: se sustituye entero por lo nuevo. Los números salteados
        # ("la uno y la tres") sí son tramos independientes.
        ordenados = sorted(set(orden.indices))
        consecutivos = ordenados == list(range(ordenados[0], ordenados[-1] + 1))
        if len(coincidencias) > 1 and consecutivos:
            primera, ultima = coincidencias[0], coincidencias[-1]
            coincidencias = [Coincidencia(
                primera.inicio, ultima.fin, texto[primera.inicio:ultima.fin],
                primera.contexto,
            )]
    else:
        coincidencias = localizar(texto, orden.buscar, ambito)
        if not coincidencias:
            return Resultado(
                texto,
                f"No encuentro {orden.buscar} en el párrafo. Di léelo para oírlo "
                f"numerado, o repite el cambio.",
            )
        if len(coincidencias) > 1 and eleccion is None:
            listado = ". ".join(f"{i + 1}, {c.contexto}" for i, c in enumerate(coincidencias))
            return Resultado(
                texto,
                f"{orden.buscar} aparece {len(coincidencias)} veces. {listado}. ¿Cuál? Di el número.",
                opciones=coincidencias,
            )
        if len(coincidencias) > 1:
            if not 1 <= eleccion <= len(coincidencias):
                return Resultado(texto, f"Solo hay {len(coincidencias)} opciones.", opciones=coincidencias)
            coincidencias = [coincidencias[eleccion - 1]]

    quitado = " y ".join(c.texto for c in coincidencias)
    if orden.tipo == "borrar":
        nuevo = sustituir(texto, coincidencias, "")
        return Resultado(nuevo, f"He borrado {quitado}.", aplicado=True,
                         cursor=min(c.inicio for c in coincidencias))

    nuevo = sustituir(texto, coincidencias, orden.poner)
    primera = min(coincidencias, key=lambda c: c.inicio)
    return Resultado(
        nuevo,
        f"He cambiado {quitado} por {orden.poner}.",
        aplicado=True,
        cursor=primera.inicio + len(orden.poner),
    )
