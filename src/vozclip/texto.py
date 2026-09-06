"""Preparación del texto antes de mandarlo al sintetizador de voz.

Un texto copiado de una web o un PDF viene lleno de basura: saltos de línea
en mitad de las frases, guiones de corte, espacios dobles, viñetas... Si se
lo mandas tal cual a la voz, suena entrecortado y cansa muchísimo.
Estas funciones lo dejan limpio.
"""

from __future__ import annotations

import re

# Guion de corte al final de línea: "conti-\nnuación" -> "continuación"
_GUION_CORTE = re.compile(r"(\w)-\n(\w)")

# Salto de línea suelto dentro de un párrafo (no doble): lo convertimos en espacio
_SALTO_SIMPLE = re.compile(r"(?<!\n)\n(?!\n)")

# Dos o más saltos = párrafo de verdad. Lo marcamos con un punto para que la
# voz haga una pausa clara.
_SALTO_PARRAFO = re.compile(r"\n{2,}")

# Espacios repetidos
_ESPACIOS = re.compile(r"[ \t\u00a0]{2,}")

# Viñetas y símbolos decorativos que la voz leería como ruido
_VINETAS = re.compile(r"^[\s]*[•▪◦·‣⁃*\-–—]+[\s]+", re.MULTILINE)

# Cortamos por final de frase respetando abreviaturas simples
_FIN_FRASE = re.compile(r"(?<=[.!?…])\s+")


def limpiar(texto: str) -> str:
    """Normaliza un texto para que se lea de forma fluida."""
    if not texto:
        return ""

    # Unificamos saltos de línea de Windows/Mac
    t = texto.replace("\r\n", "\n").replace("\r", "\n")

    t = _GUION_CORTE.sub(r"\1\2", t)
    t = _VINETAS.sub("", t)
    t = _SALTO_PARRAFO.sub(". \n", t)   # pausa entre párrafos
    t = _SALTO_SIMPLE.sub(" ", t)        # une líneas partidas
    t = _ESPACIOS.sub(" ", t)

    # Evitamos ".." o ". ." si el párrafo ya acababa en punto
    t = re.sub(r"\.\s*\.", ".", t)
    return t.strip()


def trocear(texto: str, maximo: int = 400) -> list[str]:
    """Parte el texto en trozos de como mucho `maximo` caracteres,
    cortando siempre por final de frase cuando es posible.

    Sirve para dos cosas:
      1. Que el "parar" (Ctrl+Alt+X) reaccione al instante.
      2. Que los motores online (Google, Amazon) no revienten por límite
         de longitud si algún día cambias de backend.
    """
    texto = limpiar(texto)
    if not texto:
        return []

    frases = _FIN_FRASE.split(texto)
    trozos: list[str] = []
    actual = ""

    for frase in frases:
        frase = frase.strip()
        if not frase:
            continue

        # Una sola frase más larga que el máximo: la partimos por palabras.
        if len(frase) > maximo:
            if actual:
                trozos.append(actual)
                actual = ""
            trozos.extend(_partir_por_palabras(frase, maximo))
            continue

        if not actual:
            actual = frase
        elif len(actual) + 1 + len(frase) <= maximo:
            actual = f"{actual} {frase}"
        else:
            trozos.append(actual)
            actual = frase

    if actual:
        trozos.append(actual)
    return trozos


def _partir_por_palabras(frase: str, maximo: int) -> list[str]:
    """Último recurso: cortar una frase kilométrica sin partir palabras."""
    piezas: list[str] = []
    actual = ""
    for palabra in frase.split(" "):
        if not actual:
            actual = palabra
        elif len(actual) + 1 + len(palabra) <= maximo:
            actual = f"{actual} {palabra}"
        else:
            piezas.append(actual)
            actual = palabra
    if actual:
        piezas.append(actual)
    return piezas


def resumen_para_anuncio(texto: str, palabras: int = 6) -> str:
    """Devuelve las primeras palabras de un texto, para anuncios del tipo
    'Leyendo: Estimado cliente, le escribimos...'."""
    trozos = limpiar(texto).split()
    if not trozos:
        return ""
    if len(trozos) <= palabras:
        return " ".join(trozos)
    return " ".join(trozos[:palabras]) + "…"
