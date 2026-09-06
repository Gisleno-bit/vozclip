"""Atajos de teclado globales.

"Globales" = funcionan aunque la ventana activa sea Word, el navegador o
cualquier otra cosa.

=============================================================================
REGLA DE ORO DE ESTE MÓDULO
=============================================================================
El escuchador de pynput corre en SU PROPIO HILO. Desde ese hilo NO se puede:
  * tocar un widget de tkinter  -> cuelga o corrompe la ventana
  * tocar el objeto COM de SAPI -> excepción silenciosa (el bug de la v1)

Por eso aquí no se ejecuta ninguna acción: solo se mete el NOMBRE de la
acción en una cola. El HUD, desde el hilo principal, la saca y la ejecuta.
=============================================================================

Se usa `pynput` en vez de `keyboard` porque no exige ejecutar como
administrador, cosa que complicaría mucho el arranque automático.
"""

from __future__ import annotations

import threading
from typing import Any, Callable


def normalizar(combinacion: str) -> str:
    """Deja la combinación en el formato que espera pynput.

    Acepta tanto "<ctrl>+<alt>+l" como "ctrl+alt+l" y devuelve la primera
    forma, que es la única válida. Así, si tu amigo edita el config.json a
    mano y escribe la versión corta, sigue funcionando en vez de fallar en
    silencio.
    """
    especiales = {
        "ctrl", "control", "alt", "shift", "cmd", "super",
        "up", "down", "left", "right", "enter", "return", "space",
        "tab", "esc", "escape", "home", "end", "insert", "delete",
        "page_up", "page_down", "backspace",
    }
    equivalencias = {"control": "ctrl", "return": "enter", "escape": "esc",
                     "super": "cmd"}

    # pynput no tiene nombres para el más y el menos: hay que darle el
    # carácter literal. Se aceptan igualmente "<plus>" y "<minus>" porque
    # es lo legible cuando alguien edita el config.json a mano.
    literales = {"plus": "+", "add": "+", "mas": "+",
                 "minus": "-", "subtract": "-", "menos": "-"}

    piezas = []
    for pieza in combinacion.split("+"):
        limpia = pieza.strip().strip("<>").lower()
        if not limpia:
            continue
        limpia = equivalencias.get(limpia, limpia)
        if limpia in literales:
            piezas.append(literales[limpia])
            continue
        if limpia in especiales or limpia.startswith("f") and limpia[1:].isdigit():
            piezas.append(f"<{limpia}>")
        else:
            piezas.append(limpia)
    return "+".join(piezas)


def construir_mapa(
    atajos: dict[str, str],
    encolar: Callable[[str], None],
    acciones_validas: set[str] | None = None,
) -> dict[str, Callable[[], None]]:
    """Crea el diccionario {combinación: función} que consume pynput.

    Cada función se limita a llamar a `encolar(nombre_accion)`.
    """
    mapa: dict[str, Callable[[], None]] = {}

    for nombre, combinacion in (atajos or {}).items():
        if not combinacion:
            continue
        if acciones_validas is not None and nombre not in acciones_validas:
            continue
        mapa[normalizar(combinacion)] = _fabricar(nombre, encolar)

    return mapa


def _fabricar(nombre: str, encolar: Callable[[str], None]) -> Callable[[], None]:
    """Cierre que captura el nombre. Hace falta una función aparte: si se
    usara un lambda dentro del bucle, todas capturarían la última variable."""

    def disparar() -> None:
        try:
            encolar(nombre)
        except Exception:
            pass  # nunca dejamos morir el hilo del teclado

    return disparar


class EscuchadorAtajos:
    """Envuelve `pynput.keyboard.GlobalHotKeys` con arranque y parada limpios."""

    def __init__(self, mapa: dict[str, Callable[[], None]]) -> None:
        self._mapa = mapa
        self._escuchador: Any = None
        self._parar = threading.Event()
        self.error: Exception | None = None

    @property
    def activo(self) -> bool:
        return self._escuchador is not None

    def arrancar(self) -> bool:
        """Devuelve True si los atajos globales quedaron registrados.

        Si falla (por ejemplo, en un servidor sin entorno gráfico, o si otra
        aplicación ya se quedó con el hook), NO se lanza excepción: el
        programa sigue funcionando con los atajos locales de la ventana.
        Perder los globales es una degradación, no una catástrofe.
        """
        try:
            from pynput import keyboard

            self._escuchador = keyboard.GlobalHotKeys(self._mapa)
            self._escuchador.daemon = True
            self._escuchador.start()
            return True
        except Exception as e:
            self.error = e
            self._escuchador = None
            return False

    def esperar(self) -> None:
        self._parar.wait()

    def parar(self) -> None:
        self._parar.set()
        if self._escuchador is not None:
            try:
                self._escuchador.stop()
            except Exception:
                pass
            self._escuchador = None
