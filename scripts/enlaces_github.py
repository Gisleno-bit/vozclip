"""Genera SUBIR_A_GITHUB.html: un botón por archivo oculto, que abre GitHub
con el contenido ya puesto. Solo hay que pulsar "Commit".

=============================================================================
POR QUÉ EXISTE
=============================================================================
Tres veces seguidas, el repositorio se quedó con un workflow antiguo. Los
archivos que empiezan por punto (.github/workflows/*.yml, .gitignore) no
llegan con la subida a mano, y copiar y pegar YAML en el editor de GitHub
es justo el paso que se salta.

GitHub admite abrir el editor de un archivo NUEVO con la ruta y el
contenido ya rellenados, desde un enlace:

    https://github.com/OWNER/REPO/new/main?filename=RUTA&value=CONTENIDO

Así que esto genera una página con un botón por archivo. Cada botón abre
GitHub con todo puesto; el usuario solo pulsa "Commit changes". Cero
copiar y pegar.

Solo funciona con archivos que NO existan aún: por eso los workflows
tienen nombre nuevo (release.yml, tests.yml) y los viejos hay que borrarlos
(un clic en la papelera, que la página también enlaza).

    python scripts/enlaces_github.py            -> escribe SUBIR_A_GITHUB.html
    python scripts/enlaces_github.py --imprimir -> solo imprime las URL
=============================================================================
"""

from __future__ import annotations

import argparse
import html
import sys
from pathlib import Path
from urllib.parse import quote

RAIZ = Path(__file__).resolve().parent.parent
REPO = "Gisleno-bit/vozclip"
RAMA = "main"

# Archivos ocultos que hay que crear, en orden
ARCHIVOS_NUEVOS = [
    ".github/workflows/release.yml",
    ".github/workflows/tests.yml",
]

# Archivos viejos que hay que borrar (un clic en la papelera)
ARCHIVOS_OBSOLETOS = [
    ".github/workflows/build-windows.yml",
    ".github/workflows/ci.yml",
]


def url_crear(ruta: str, contenido: str, repo: str = REPO, rama: str = RAMA) -> str:
    return (
        f"https://github.com/{repo}/new/{rama}"
        f"?filename={quote(ruta, safe='')}&value={quote(contenido, safe='')}"
    )


def url_ver(ruta: str, repo: str = REPO, rama: str = RAMA) -> str:
    return f"https://github.com/{repo}/blob/{rama}/{ruta}"


def generar(repo: str = REPO, rama: str = RAMA) -> str:
    botones = []
    for ruta in ARCHIVOS_NUEVOS:
        contenido = (RAIZ / ruta).read_text(encoding="utf-8")
        botones.append(f"""
      <li>
        <a class="boton crear" href="{html.escape(url_crear(ruta, contenido, repo, rama))}"
           target="_blank" rel="noopener">
          Crear <code>{html.escape(ruta)}</code>
        </a>
        <p>Se abre GitHub con el archivo ya escrito. Baja y pulsa
           <strong>Commit changes</strong>. Nada más.</p>
      </li>""")

    borrar = []
    for ruta in ARCHIVOS_OBSOLETOS:
        borrar.append(f"""
      <li>
        <a class="boton borrar" href="{html.escape(url_ver(ruta, repo, rama))}"
           target="_blank" rel="noopener">
          Borrar <code>{html.escape(ruta)}</code>
        </a>
        <p>Se abre el archivo viejo. Arriba a la derecha, el icono de la
           <strong>papelera</strong>, y <strong>Commit changes</strong>.
           Si dice que no existe, ya está: no hay nada que borrar.</p>
      </li>""")

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Subir VozClip a GitHub</title>
<style>
  body {{ font-family: Segoe UI, sans-serif; max-width: 52em; margin: 2em auto;
         padding: 0 1em; background: #111; color: #eee; font-size: 1.15em; line-height: 1.5; }}
  h1 {{ color: #ffc857; }}
  h2 {{ margin-top: 2em; border-bottom: 2px solid #333; padding-bottom: .3em; }}
  ol {{ padding-left: 1.2em; }}
  li {{ margin: 1.6em 0; }}
  .boton {{ display: inline-block; padding: .8em 1.4em; font-size: 1.1em; font-weight: bold;
            border-radius: .5em; text-decoration: none; color: #fff; border: 3px solid #fff; }}
  .crear {{ background: #1d4ed8; }}
  .borrar {{ background: #b91c1c; }}
  .boton:focus, .boton:hover {{ outline: 4px solid #ffc857; }}
  code {{ background: #222; padding: .1em .4em; border-radius: .3em; font-size: .95em; }}
  p {{ margin: .4em 0 0; color: #bbb; }}
  .nota {{ background: #1c2030; padding: 1em; border-radius: .5em; margin-top: 2em; }}
</style>
</head>
<body>
<h1>Subir VozClip a GitHub, sin copiar ni pegar</h1>

<p>Cada botón abre GitHub con el archivo ya escrito. Tú solo pulsas
<strong>Commit changes</strong>. Hazlo en este orden, con la sesión de
GitHub iniciada.</p>

<h2>1. Sube el código</h2>
<p>En <a href="https://github.com/{html.escape(repo)}" target="_blank" rel="noopener">
el repositorio</a>: <strong>Add file → Upload files</strong>, arrastra el
<em>contenido</em> de la carpeta <code>vozclip</code> (no la carpeta en sí) y
pulsa Commit. Los archivos que empiezan por punto no llegan así: para eso
están los botones de abajo.</p>

<h2>2. Borra los workflows viejos</h2>
<p><strong>Esto primero.</strong> Mientras existan, siguen ejecutándose por su
cuenta y ponen la X roja aunque todo lo demás vaya bien. Si alguno dice que
no existe, ya está borrado: pasa al siguiente.</p>
<ol>{"".join(borrar)}
</ol>

<h2>3. Crea los workflows nuevos</h2>
<ol>{"".join(botones)}
</ol>

<h2>4. Espera y descarga</h2>
<p>Con el paso 1 y 2 hechos, la pestaña <strong>Actions</strong> muestra
<em>Release</em> en marcha. En unos 10 minutos, la descarga queda aquí,
siempre en la misma dirección:</p>
<p><a class="boton crear"
      href="https://github.com/{html.escape(repo)}/releases/latest/download/VozClip-Windows.zip">
   Descargar VozClip-Windows.zip (última versión)</a></p>

<div class="nota">
<strong>Si un botón de crear dice que el archivo ya existe:</strong> es que ya
lo subiste. Abre el archivo en GitHub, pulsa el lápiz, borra todo, pega el
contenido del que está en la carpeta <code>.github/workflows</code> del ZIP,
y Commit.
</div>
</body>
</html>
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Enlaces para subir los archivos ocultos.")
    parser.add_argument("--imprimir", action="store_true", help="Solo imprimir las URL.")
    parser.add_argument("--repo", default=REPO)
    args = parser.parse_args()

    if args.imprimir:
        for ruta in ARCHIVOS_NUEVOS:
            contenido = (RAIZ / ruta).read_text(encoding="utf-8")
            print(f"\n# {ruta}\n{url_crear(ruta, contenido, args.repo)}")
        return 0

    destino = RAIZ / "SUBIR_A_GITHUB.html"
    destino.write_text(generar(args.repo), encoding="utf-8")
    print(f"Escrito {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
