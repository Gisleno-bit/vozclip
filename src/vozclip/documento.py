"""Operaciones sobre el documento, escritas como funciones puras.

Ninguna de estas funciones toca tkinter ni el motor de voz: reciben el texto
y la posición del cursor, y devuelven texto nuevo y posición nueva. Gracias a
eso se pueden probar enteras con tests automáticos, sin abrir una ventana.

El HUD traduce entre el índice de tkinter ("línea.columna") y el
desplazamiento en caracteres que usan estas funciones.
"""

from __future__ import annotations


def rango_linea(texto: str, cursor: int) -> tuple[int, int]:
    """Devuelve (inicio, fin) de la línea donde está el cursor.

    El fin no incluye el salto de línea.
    """
    cursor = max(0, min(cursor, len(texto)))
    inicio = texto.rfind("\n", 0, cursor) + 1
    fin = texto.find("\n", cursor)
    if fin == -1:
        fin = len(texto)
    return inicio, fin


def linea_actual(texto: str, cursor: int) -> str:
    inicio, fin = rango_linea(texto, cursor)
    return texto[inicio:fin]


def numero_linea(texto: str, cursor: int) -> int:
    """Número de línea empezando en 1, para anunciarlo en voz alta."""
    cursor = max(0, min(cursor, len(texto)))
    return texto.count("\n", 0, cursor) + 1


def insertar(texto: str, cursor: int, fragmento: str) -> tuple[str, int]:
    """Inserta un fragmento en la posición del cursor."""
    cursor = max(0, min(cursor, len(texto)))
    nuevo = texto[:cursor] + fragmento + texto[cursor:]
    return nuevo, cursor + len(fragmento)


def aplicar_sangria(texto: str, cursor: int, sangria: str) -> tuple[str, int]:
    """Añade la sangría al PRINCIPIO de la línea actual.

    Importante: se inserta al principio de la línea, no donde esté el cursor.
    Si se insertara en el cursor, al escritor le aparecerían espacios en
    mitad de una frase sin poder verlo.
    """
    inicio, _ = rango_linea(texto, cursor)
    nuevo = texto[:inicio] + sangria + texto[inicio:]
    return nuevo, cursor + len(sangria)


def quitar_sangria(texto: str, cursor: int, sangria: str) -> tuple[str, int]:
    """Quita una unidad de sangría del principio de la línea, si la hay."""
    inicio, _ = rango_linea(texto, cursor)
    resto = texto[inicio:]

    if resto.startswith(sangria):
        quitados = len(sangria)
    else:
        # Si no encaja exactamente, quitamos los espacios que haya (hasta el
        # ancho de la sangría). Así funciona aunque el texto venga de fuera.
        quitados = 0
        for caracter in resto[: len(sangria)]:
            if caracter in " \t":
                quitados += 1
            else:
                break
        if quitados == 0:
            return texto, cursor

    nuevo = texto[:inicio] + texto[inicio + quitados :]
    return nuevo, max(inicio, cursor - quitados)


def siguiente_linea(texto: str, cursor: int, sangria: str = "") -> tuple[str, int]:
    """Salta a una línea nueva conservando la sangría indicada.

    Si `sangria` viene vacía, se hereda la sangría de la línea actual: es lo
    que espera cualquiera que esté escribiendo diálogo, que la línea nueva
    quede alineada con la anterior.
    """
    if not sangria:
        sangria = sangria_de_linea(linea_actual(texto, cursor))

    _, fin = rango_linea(texto, cursor)
    nuevo = texto[:fin] + "\n" + sangria + texto[fin:]
    return nuevo, fin + 1 + len(sangria)


def insertar_dictado(
    texto: str, cursor: int, dictado: str, sangria: str = ""
) -> tuple[str, int]:
    """Inserta texto dictado respetando el formato de la plantilla.

    Lo importante aquí son los saltos de línea. Si el escritor dice "punto y
    aparte" estando dentro de un bloque de diálogo sangrado a diez espacios,
    la línea nueva tiene que salir también a diez espacios: si no, el guion
    se descuadra y él no puede verlo para arreglarlo.

    Por eso cada "\\n" del dictado arrastra consigo la sangría vigente.
    """
    cursor = max(0, min(cursor, len(texto)))

    if not dictado:
        return texto, cursor

    # Si no se pasa sangría explícita, se hereda la de la línea actual.
    if not sangria:
        sangria = sangria_de_linea(linea_actual(texto, cursor))

    fragmento = dictado.replace("\n", "\n" + sangria) if sangria else dictado

    nuevo = texto[:cursor] + fragmento + texto[cursor:]
    return nuevo, cursor + len(fragmento)


def contexto_antes_del_cursor(texto: str, cursor: int, caracteres: int = 40) -> str:
    """Los últimos caracteres de la línea antes del cursor.

    El dictado los mira para decidir si empieza en mayúscula y si hace falta
    un espacio de separación.
    """
    inicio, _ = rango_linea(texto, cursor)
    cursor = max(0, min(cursor, len(texto)))
    trozo = texto[inicio:cursor]
    return trozo[-caracteres:] if len(trozo) > caracteres else trozo


def siguiente_marca(posiciones: list[int], cursor: int) -> int | None:
    """Devuelve la primera posición mayor que el cursor, o la primera de
    todas si ya se pasaron todas (comportamiento circular)."""
    if not posiciones:
        return None
    for p in sorted(posiciones):
        if p > cursor:
            return p
    return min(posiciones)


def resumen_documento(texto: str) -> str:
    """Frase para anunciar el estado del documento en voz alta."""
    palabras = len(texto.split())
    lineas = texto.count("\n") + 1 if texto else 0

    if palabras == 0:
        return "Documento vacío."
    plural_p = "palabra" if palabras == 1 else "palabras"
    plural_l = "línea" if lineas == 1 else "líneas"
    return f"{palabras} {plural_p} en {lineas} {plural_l}."


def contexto_para_voz(texto: str, cursor: int) -> str:
    """Lo que se dice al moverse: número de línea y su contenido."""
    numero = numero_linea(texto, cursor)
    contenido = linea_actual(texto, cursor).strip()
    if not contenido:
        return f"Línea {numero}, vacía."
    return f"Línea {numero}. {contenido}"


def sangria_de_linea(linea: str) -> str:
    """Devuelve los espacios o tabuladores con los que empieza una línea."""
    contados = 0
    for caracter in linea:
        if caracter in " \t":
            contados += 1
        else:
            break
    return linea[:contados]


# ---------------------------------------------------------------------------
# Párrafos
# ---------------------------------------------------------------------------
def rango_parrafo(texto: str, cursor: int) -> tuple[int, int]:
    """Devuelve (inicio, fin) del párrafo donde está el cursor.

    Un párrafo es un bloque de líneas seguidas sin ninguna en blanco entre
    ellas. Es la unidad natural para "léeme lo último que he escrito": la
    línea sola se queda corta y el documento entero se pasa.
    """
    cursor = max(0, min(cursor, len(texto)))

    inicio = texto.rfind("\n\n", 0, cursor)
    inicio = 0 if inicio == -1 else inicio + 2

    fin = texto.find("\n\n", cursor)
    fin = len(texto) if fin == -1 else fin

    return inicio, fin


def parrafo_actual(texto: str, cursor: int) -> str:
    inicio, fin = rango_parrafo(texto, cursor)
    return texto[inicio:fin].strip()


def ultimo_parrafo(texto: str) -> str:
    """El último párrafo con contenido del documento."""
    bloques = [b.strip() for b in texto.split("\n\n") if b.strip()]
    return bloques[-1] if bloques else ""


def nuevo_parrafo(texto: str, cursor: int, sangria: str) -> tuple[str, int]:
    """Abre un párrafo nuevo con su sangría, al final de la línea actual.

    Se inserta una línea en blanco de separación porque es lo que espera un
    texto en prosa, y porque al exportar a Word esa línea en blanco se
    convierte en el espacio posterior de 18 puntos.
    """
    _, fin = rango_linea(texto, cursor)

    # Si la línea actual está vacía, no hace falta abrir otra: se aprovecha.
    if not linea_actual(texto, cursor).strip():
        inicio, _ = rango_linea(texto, cursor)
        nuevo = texto[:inicio] + sangria + texto[fin:]
        return nuevo, inicio + len(sangria)

    fragmento = "\n\n" + sangria
    nuevo = texto[:fin] + fragmento + texto[fin:]
    return nuevo, fin + len(fragmento)


def nuevo_dialogo(
    texto: str,
    cursor: int,
    marca: str = "—",
    sangria_dialogo: str = "",
) -> tuple[str, int]:
    """Abre una intervención hablada: sangría, raya pegada y cursor detrás.

    Sin espacio tras la raya: en castellano va pegada a la primera palabra,
    "—No me lo creo". Y sin nombre de personaje, que es lo que hacían las
    plantillas de teatro y cine, ya retiradas.
    """
    _, fin = rango_linea(texto, cursor)
    hay_contenido = bool(linea_actual(texto, cursor).strip())
    separador = "\n\n" if hay_contenido else ""
    fragmento = f"{separador}{sangria_dialogo}{marca}"

    if not hay_contenido:
        inicio, _ = rango_linea(texto, cursor)
        nuevo = texto[:inicio] + fragmento + texto[fin:]
        return nuevo, inicio + len(fragmento)

    nuevo = texto[:fin] + fragmento + texto[fin:]
    return nuevo, fin + len(fragmento)
