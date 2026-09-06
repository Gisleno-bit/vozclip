"""Imprime la versión de VozClip. La usa el workflow de release para
etiquetar sin que nadie tenga que crear la etiqueta a mano."""

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent


def version() -> str:
    texto = (RAIZ / "pyproject.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', texto, re.M).group(1)


if __name__ == "__main__":
    sys.stdout.write(version())
    sys.stdout.flush()
