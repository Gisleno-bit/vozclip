"""Punto de entrada para PyInstaller.

=============================================================================
POR QUÉ EXISTE ESTE ARCHIVO
=============================================================================
`src/vozclip/__main__.py` usa un import relativo (`from .cli import main`),
que es lo correcto dentro de un paquete y funciona perfectamente con
`python -m vozclip`.

Pero PyInstaller ejecuta el script de entrada como si fuera un programa
suelto, sin contexto de paquete. El import relativo revienta con:

    ImportError: attempted relative import with no known parent package

Y como el .exe se compila con --windowed, ese error no se ve por ninguna
parte: el usuario hace doble clic y no ocurre absolutamente nada.

La solución es este lanzador, que usa un import ABSOLUTO. PyInstaller apunta
aquí; `python -m vozclip` sigue usando __main__.py.
=============================================================================
"""

import sys

from vozclip.cli import main

if __name__ == "__main__":
    sys.exit(main())
