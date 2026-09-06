"""El HUD: la ventana de VozClip Escritor.

=============================================================================
DOS ADVERTENCIAS DE DISEÑO, IMPORTANTES
=============================================================================
1. Tkinter NO se expone bien a NVDA. Tk no implementa UI Automation como es
   debido, así que un lector de pantalla externo lee muy mal esta ventana.
   Por eso VozClip habla por sí mismo TODO: cada acción, cada cambio de modo,
   cada error. La voz no es un adorno, es el interfaz de verdad.

2. La parte visible existe para quien ve (tú, ayudándole a configurarlo) y
   para personas con resto visual. El escritor ciego no necesita mirarla
   nunca: todo se hace con teclado y se confirma por voz.
=============================================================================

Reglas de hilos que hay que respetar sí o sí:
  * Los widgets de tkinter SOLO se tocan desde el hilo principal.
  * El escuchador de teclado corre en otro hilo, así que no llama a los
    widgets: mete una orden en `cola_ordenes`, y el bucle `_atender_cola`
    (que sí vive en el hilo principal) la ejecuta.
  * La voz vive en su propio hilo (`ServicioVoz`) y se le habla por cola.
Con esto, ni el teclado bloquea la voz ni la voz bloquea la ventana.
"""

from __future__ import annotations

import datetime as _dt
import queue
import tkinter as tk
from pathlib import Path
from tkinter import filedialog
from typing import Any, Callable

from . import __version__, correccion, documento, fuentes, plantillas, puente
from . import config as cfg
from . import dictado as moddictado
from . import texto as textoutil
from .fuentes import ErrorFuente, escribir_portapapeles, leer_portapapeles

# ===========================================================================
# TEMAS
# ===========================================================================
# Tres temas, y cada uno responde a una necesidad distinta:
#
#   oscuro         Texto claro sobre fondo muy oscuro. Es el que menos
#                  cansa en sesiones largas, porque emite poca luz.
#   alto_contraste Negro puro y amarillo puro. Es la relación de contraste
#                  máxima que se puede conseguir (21:1), la que necesita
#                  quien tiene resto visual muy bajo. El amarillo se
#                  prefiere al blanco porque se distingue mejor en varios
#                  tipos de baja visión.
#   claro          Fondo claro para quien lo prefiere o trabaja con mucha
#                  luz ambiente.
#
# Ninguno usa colores saturados en grandes superficies ni nada que
# parpadee: eso es lo que provoca fatiga y, en algunos casos, migrañas.
TEMAS: dict[str, dict[str, str]] = {
    "oscuro": {
        "nombre": "oscuro",
        "fondo": "#12141c",
        "panel": "#1c2030",
        "editor": "#0d0f16",
        "texto": "#f2f4f8",
        "acento": "#ffc857",
        "suave": "#98a2b8",
        "seleccion": "#3a4a6d",
        "borde": "#2c3348",
        "destacado": "#1d4ed8",
        "destacado_texto": "#ffffff",
        "guardar": "#15803d",
        "archivo": "#c2410c",
        "libre": "#6d28d9",
        "corregir": "#0f766e",
        "escucha": "#ff5c6c",
        "listo": "#4ade80",
    },
    "alto_contraste": {
        "nombre": "alto contraste",
        "fondo": "#000000",
        "panel": "#000000",
        "editor": "#000000",
        "texto": "#ffffff",
        "acento": "#ffff00",
        "suave": "#ffffff",
        "seleccion": "#0000ff",
        "borde": "#ffff00",
        "destacado": "#0000ff",
        "destacado_texto": "#ffff00",
        "guardar": "#008000",
        "archivo": "#804000",
        "libre": "#8000ff",
        "corregir": "#008080",
        "escucha": "#ff4444",
        "listo": "#00ff00",
    },
    "claro": {
        "nombre": "claro",
        "fondo": "#f4f4f0",
        "panel": "#e6e6df",
        "editor": "#ffffff",
        "texto": "#14161c",
        "acento": "#8a4b00",
        "suave": "#4a4f5c",
        "seleccion": "#b8d0f0",
        "borde": "#9aa0ad",
        "destacado": "#1e40af",
        "destacado_texto": "#ffffff",
        "guardar": "#14532d",
        "archivo": "#7c2d12",
        "libre": "#4c1d95",
        "corregir": "#115e59",
        "escucha": "#b00020",
        "listo": "#106b2a",
    },
}

ORDEN_TEMAS = ["oscuro", "alto_contraste", "claro"]

def version_hablada(version: str | None = None) -> str:
    """'2.10.0' -> 'dos punto diez'. Los puntos se dicen; el último cero
    se calla, que no aporta nada de oído."""
    v = version or __version__
    partes = v.split(".")
    if len(partes) == 3 and partes[2] == "0":
        partes = partes[:2]
    return " punto ".join(partes)


TAMANO_MINIMO = 10
TAMANO_MAXIMO = 42

# Tope para los rótulos de la interfaz (botones, franja de estado, pie).
# El TEXTO del guion sí puede llegar a 42 puntos, porque es lo que se lee.
# Los botones, no: a partir de cierto tamaño ocupan la ventana entera y
# empujan al editor fuera de la pantalla, que es justo lo contrario de lo
# que busca quien ha subido la letra.
TAMANO_UI_MAXIMO = 22

AYUDA_HABLADA = """VozClip Escritor. Lista completa de atajos.

Los cinco de todos los días, en las teclas de función:
Efe uno, grabar: empezar o parar el dictado.
Efe dos, nuevo párrafo.
Efe tres, nuevo diálogo.
Efe cuatro, leer el último párrafo.
Efe cinco, leer el texto entero.
Efe nueve, corregir una palabra: pulsa, di el cambio, y calla. Se
aplica solo al segundo y medio de silencio; o pulsa efe nueve otra vez.
Por ejemplo: cambia casa por cosa. O borra además. O léelo, para oír el
párrafo numerado; entonces di el número, oye la palabra, y dicta la nueva.
Escape cancela. Deshacer, deshace.

Dictar por voz.
Efe uno, empezar o parar el dictado. Habla después del pitido.
Si dice que el modelo no se ha podido cargar, ejecuta instalar modelos
punto bat: lo deja en una carpeta sin acentos, que es lo que hace falta.
Mientras dictas puedes decir: coma, punto, punto y aparte, raya,
abrir interrogación, cerrar interrogación, dos puntos, o nueva línea.

Escribir.
Control alt ge, insertar la plantilla de guion.
Control alt ene, cambiar de plantilla.
Control alt i, aplicar sangría. Control alt u, quitarla.
Control alt intro, siguiente línea.
Control alt te, saltar al siguiente hueco de la plantilla.

Archivos.
Control alt o, importar: abrir un archivo. Admite texto, erre te efe y Word.
Control alt e, exportar todo. En el editor propio lo copia al portapapeles;
en modo externo lo escribe en la aplicación que tengas delante.
Control alt de, guardar. Control alt ese, guardar como.
Control alt mayúsculas e, exportar a Word con el formato de verdad:
sangría francesa en los diálogos y primera línea en el narrador.
Control alt mayúsculas ele, exportar a LibreOffice, con el mismo formato.

Configuración.
Control alt u, importar una configuración guardada.
Control alt y, exportar la configuración actual.
Control alt mayúsculas jota, volver al perfil de Julián: alto contraste,
letra grande, velocidad dos y plantilla de novela.

Corregir mientras dictas.
No hace falta efe nueve. Con efe uno, di: cambia, alpiste, por, rueda.
Si empieza por cambia o por borra, se aplica como corrección y no se
escribe.

Escuchar.
Control alt jota, leer la línea actual.
Control alt ka, leer lo seleccionado.
Control alt ele, leer el portapapeles.
Control alt a, leer el documento entero.
Control alt pe, pausar o reanudar. Control alt equis, parar.

Ver mejor.
Control alt ce, cambiar de tema: oscuro, alto contraste, o claro.
Control alt más, letra más grande. Control alt menos, letra más pequeña.
Control alt zeta, modo solo voz: la ventana se reduce al mínimo
y todo sigue funcionando por teclado.

Moverse.
Tabulador, pasar de un botón al siguiente. Efe seis, saltar entre el
editor y los botones. Alt y un número del uno al ocho, pulsar ese botón.
Las flechas arriba y abajo mueven el cursor y dicen la línea nueva.

Ajustes.
Control alt flecha arriba y abajo, velocidad de la voz.
Control alt uve, cambiar de voz.
Control alt eme, cambiar entre editor propio y aplicación externa.
Control alt doble uve, dónde estoy.
Control alt hache, repetir esta ayuda. Control alt cu, salir."""


class HUD:
    def __init__(
        self,
        voz: Any,
        ajustes: dict[str, Any],
        guardar_ajustes: Callable[[dict[str, Any]], Any] | None = None,
        fabrica_dictado: Callable[[Callable], Any] | None = None,
    ) -> None:
        self.voz = voz
        self._fabrica_dictado = fabrica_dictado
        self.ajustes = ajustes
        self._guardar_ajustes = guardar_ajustes
        self.cola_ordenes: queue.Queue = queue.Queue()

        self.modo = ajustes.get("modo", "editor")
        self.plantilla = plantillas.obtener(ajustes.get("plantilla", "teatro"))
        self.marcas: list[int] = []
        self.ruta_actual: Path | None = None
        self.modificado = False
        self._cerrando = False
        self._tarea_cola = None
        # Corrección por voz: None si no está activa; si no, un dict con
        # el ámbito (párrafo) y, si toca elegir, las opciones pendientes.
        self.correccion: dict | None = None
        # Al cancelar con Escape, el hilo de dictado puede entregar todavía
        # el texto que estaba procesando. Hay que tirarlo, no insertarlo.
        self._descartar_proximo_texto = False
        # Guard de repetición: cada tecla llega por dos rutas (el bind_all
        # de tkinter y el atajo global de pynput), y el filtro por foco es
        # una heurística que en Windows falla con cierta sincronía. Aquí se
        # recuerda cuándo se ejecutó cada acción por última vez, y una
        # repetición dentro de la ventana se descarta venga por donde venga.
        # Nadie pulsa F1 dos veces a propósito en un tercio de segundo.
        self._ultimo_disparo: dict[str, float] = {}

        self._construir_ventana()
        self._preparar_dictado()
        self._construir_atajos_locales()
        if self.ajustes.get("solo_voz", False):
            self._aplicar_solo_voz(True)
        self._refrescar_estado()

        # El identificador se guarda para poder cancelar el bucle al cerrar.
        # Sin guardarlo, `detener_bucle` no podía cancelar esta PRIMERA
        # tarea, y su callback acababa ejecutándose sobre un intérprete Tcl
        # ya destruido.
        self._tarea_cola = self.raiz.after(50, self._atender_cola)

    # ==================================================================
    # Tema y tamaño de letra
    # ==================================================================
    @property
    def tema(self) -> dict[str, str]:
        return TEMAS.get(self.ajustes.get("tema", "oscuro"), TEMAS["oscuro"])

    @property
    def tamano(self) -> int:
        return int(self.ajustes.get("tamano_fuente", 16))

    def _fuente_editor(self) -> tuple:
        return (self.ajustes.get("fuente", "Consolas"), self.tamano)

    def _fuente_ui(self, escala: float = 0.85, negrita: bool = False) -> tuple:
        """Los rótulos de la interfaz siguen el tamaño del editor.

        Si alguien sube la letra porque no ve, no tiene sentido que los
        botones se queden pequeños: se escala todo junto.
        """
        base = min(self.tamano, TAMANO_UI_MAXIMO)
        puntos = max(9, int(base * escala))
        return ("Segoe UI", puntos, "bold" if negrita else "normal")

    # ==================================================================
    # Construcción de la interfaz
    # ==================================================================
    def _construir_ventana(self) -> None:
        self.raiz = tk.Tk()
        self.raiz.title("VozClip Escritor")
        self.raiz.geometry("1100x740")
        self.raiz.minsize(700, 420)
        self.raiz.protocol("WM_DELETE_WINDOW", self.accion_salir)

        # --- Franja de estado ------------------------------------------
        self.cabecera = tk.Frame(self.raiz, padx=18, pady=14)
        self.cabecera.pack(fill="x")

        self.etiqueta_titulo = tk.Label(
            self.cabecera, text="VozClip Escritor", anchor="w"
        )
        self.etiqueta_titulo.pack(fill="x")

        # `wraplength` se recalcula al redimensionar: con letra grande, la
        # línea de estado no cabe en una sola fila y hay que dejar que salte.
        self.etiqueta_estado = tk.Label(
            self.cabecera, text="", anchor="w", justify="left"
        )
        self.etiqueta_estado.pack(fill="x", pady=(6, 0))
        self.raiz.bind("<Configure>", self._al_redimensionar)

        self.etiqueta_archivo = tk.Label(
            self.cabecera, text="Sin guardar", anchor="w"
        )
        self.etiqueta_archivo.pack(fill="x", pady=(4, 0))

        # Indicador de dictado. Grande y de color, porque es el estado que
        # más importa: si estás grabando sin saberlo, el guion se llena de
        # ruido. Quien no ve la pantalla lo sabe por el pitido y la voz.
        self.etiqueta_dictado = tk.Label(self.cabecera, text="", anchor="w")
        self.etiqueta_dictado.pack(fill="x", pady=(6, 0))

        # --- Botonera ---------------------------------------------------
        self.botonera = tk.Frame(self.raiz, padx=14, pady=10)
        self.botonera.pack(fill="x")

        # Cada botón lleva además un número: Alt+1, Alt+2... Es una segunda
        # vía de acceso para quien navegue con el tabulador y se pierda.
        # Dos grupos, con colores distintos a propósito.
        #
        # Los cinco COMANDOS son los que Julián usa a todas horas: van en
        # azul con borde claro, porque con baja visión localizar un bloque
        # de color cuesta mucho menos que leer ocho rótulos iguales.
        #
        # Los de ARCHIVO van aparte: guardar en verde, y en naranja lo que
        # entra y sale del programa. Separarlos por color evita el error
        # caro, que es darle a exportar creyendo que guardas.
        definicion = [
            # (rótulo, atajo, función, grupo)
            ("Grabar", "F1", self.accion_dictar, "comando"),
            ("Nuevo párrafo", "F2", self.accion_nuevo_parrafo, "comando"),
            ("Nuevo diálogo", "F3", self.accion_nuevo_dialogo, "comando"),
            ("Leer último párrafo", "F4", self.accion_leer_ultimo_parrafo, "comando"),
            ("Leer texto entero", "F5", self.accion_leer_todo, "comando"),
            ("Corregir palabra", "F9", self.accion_corregir, "corregir"),
            ("Guardar", "Ctrl+Alt+D", self.accion_guardar, "guardar"),
            ("Importar", "Ctrl+Alt+O", self.accion_importar, "archivo"),
            ("Exportar", "Ctrl+Alt+E", self.accion_exportar, "archivo"),
            ("Exportar a Word", "Ctrl+Alt+Mayús+E", self.accion_exportar_word, "archivo"),
            ("Exportar a LibreOffice", "Ctrl+Alt+Mayús+L", self.accion_exportar_libreoffice, "libre"),
        ]

        self.botones: list[tk.Button] = []
        self.grupos_boton: list[str] = []
        for i, (nombre, atajo, funcion, grupo) in enumerate(definicion):
            boton = tk.Button(
                self.botonera,
                text=f"{i + 1}. {nombre}\n{atajo}",
                command=(lambda f=funcion: self._disparar(self._nombre_de_accion(f), f, "raton")),
                relief="solid",
                borderwidth=3,
                cursor="hand2",
                takefocus=True,
                highlightthickness=3,
                justify="center",
            )
            boton.bind("<FocusIn>", lambda _e, n=nombre, a=atajo: self._foco_boton(n, a))
            boton.bind("<Return>", lambda _e, f=funcion: (f(), "break")[1])
            boton.bind("<space>", lambda _e, f=funcion: (f(), "break")[1])
            # Alt+1 … Alt+9, y Alt+0 para el décimo
            self.raiz.bind_all(f"<Alt-Key-{(i + 1) % 10}>",
                               lambda _e, f=funcion: (f(), "break")[1])
            self.botones.append(boton)
            self.grupos_boton.append(grupo)

        self._disponer_botones()

        # --- Editor -----------------------------------------------------
        self.marco_editor = tk.Frame(self.raiz)
        self.marco_editor.pack(fill="both", expand=True, padx=14, pady=(0, 12))

        self.editor = tk.Text(
            self.marco_editor,
            wrap="word",
            undo=True,                   # Ctrl+Z funciona
            insertwidth=4,               # cursor grueso, visible con resto visual
            padx=16,
            pady=14,
            relief="solid",
            borderwidth=2,
            spacing1=3,                  # aire entre líneas: se lee mejor
            spacing3=5,
            highlightthickness=3,
        )
        # Un cursor que parpadea es un elemento que se mueve todo el rato en
        # la pantalla. Para quien tiene fatiga visual o baja visión, eso
        # cansa y distrae. Se puede reactivar en la configuración.
        if not self.ajustes.get("cursor_parpadea", False):
            self.editor.configure(insertofftime=0)

        # Barra de desplazamiento de tk, no de ttk: la de ttk no se puede
        # colorear, y en modo alto contraste tiene que verse.
        self.barra = tk.Scrollbar(
            self.marco_editor, command=self.editor.yview, width=20,
            relief="solid", borderwidth=1,
        )
        self.editor.configure(yscrollcommand=self.barra.set)
        self.barra.pack(side="right", fill="y")
        self.editor.pack(side="left", fill="both", expand=True)

        self.editor.bind("<<Modified>>", self._marcar_modificado)
        self.editor.focus_set()

        # --- Pie --------------------------------------------------------
        self.pie = tk.Label(
            self.raiz,
            text="Ctrl+Alt+H para escuchar todos los atajos  ·  "
                 "Ctrl+Alt+C cambia el contraste  ·  Ctrl+Alt+Z modo solo voz",
            anchor="w", padx=18, pady=8,
        )
        self.pie.pack(fill="x", side="bottom")

        self._aplicar_tema()

    def columnas_botonera(self) -> int:
        """Cuántos botones caben por fila con el tamaño de letra actual.

        Con letra grande, ocho botones en una fila se recortan y dejan
        rótulos ilegibles como "6. Importa". Justo el caso de quien ha
        subido la letra porque no ve bien: el remedio no puede ser peor
        que la enfermedad. Así que se reparten en dos o cuatro filas.
        """
        # Con el tope de TAMANO_UI_MAXIMO solo hay dos casos posibles:
        # una fila de ocho, o dos filas de cuatro.
        # Once botones, en dos filas de seis: los seis comandos diarios
        # arriba (los cinco de siempre más corregir) y los cinco de archivo
        # abajo. Los rótulos no se recortan porque `wraplength` los parte
        # en dos líneas cuando la letra es grande.
        return 6

    def _disponer_botones(self) -> None:
        """Coloca los botones en la rejilla, con las filas que hagan falta."""
        columnas = self.columnas_botonera()

        for hijo in self.botonera.grid_slaves():
            hijo.grid_forget()
        for i in range(11):
            self.botonera.grid_columnconfigure(i, weight=0, uniform="")

        for indice, boton in enumerate(self.botones):
            fila, columna = divmod(indice, columnas)
            # Sin altura fija: el botón crece con su texto. Con altura fija,
            # un rótulo que ocupaba tres líneas se recortaba por abajo.
            boton.grid(
                row=fila, column=columna,
                sticky="nsew", padx=4, pady=3, ipady=6,
            )
        # Las filas NO llevan weight: la botonera debe ocupar solo lo que
        # necesite. Con weight, crecía hasta empujar el editor fuera de la
        # pantalla en cuanto la letra era grande.

        for columna in range(columnas):
            self.botonera.grid_columnconfigure(columna, weight=1, uniform="botones")

        # El rótulo se ajusta al ancho disponible en vez de recortarse
        # OJO: durante la construcción, winfo_width() devuelve 1 porque la
        # ventana aún no se ha dibujado. Se usa el ancho pedido como
        # respaldo, y `_al_redimensionar` vuelve a llamar aquí con el real.
        ancho_ventana = self.raiz.winfo_width()
        if ancho_ventana <= 1:
            ancho_ventana = 1100
        ancho = max(150, int(ancho_ventana / max(1, columnas)) - 30)
        for boton in self.botones:
            boton.configure(wraplength=ancho)

    def _al_redimensionar(self, evento=None) -> None:
        """Reajusta los rótulos al ancho real de la ventana."""
        if evento is not None and evento.widget is not self.raiz:
            return
        ancho = max(300, self.raiz.winfo_width() - 60)
        try:
            self.etiqueta_estado.configure(wraplength=ancho)
            self.etiqueta_archivo.configure(wraplength=ancho)
            self.etiqueta_dictado.configure(wraplength=ancho)
            self.pie.configure(wraplength=ancho)
            self._ajustar_ancho_botones()
        except tk.TclError:
            pass

    def _ajustar_ancho_botones(self) -> None:
        columnas = self.columnas_botonera()
        ancho_ventana = max(600, self.raiz.winfo_width())
        ancho = max(150, int(ancho_ventana / max(1, columnas)) - 30)
        for boton in self.botones:
            boton.configure(wraplength=ancho)

    def _foco_boton(self, nombre: str, atajo: str) -> None:
        """Al llegar con el tabulador, el botón se presenta solo."""
        self.decir(f"{nombre}, {atajo}")

    def _aplicar_tema(self) -> None:
        """Repinta la ventana entera con el tema y el tamaño actuales.

        Todo pasa por aquí: así, cambiar de tema o de tamaño de letra es
        una sola llamada y no quedan trozos con los colores viejos.
        """
        t = self.tema

        self.raiz.configure(bg=t["fondo"])
        for marco in (self.cabecera, self.botonera, self.marco_editor):
            marco.configure(bg=t["panel"] if marco is self.cabecera else t["fondo"])

        self.etiqueta_titulo.configure(
            bg=t["panel"], fg=t["acento"], font=self._fuente_ui(1.25, True)
        )
        self.etiqueta_estado.configure(
            bg=t["panel"], fg=t["texto"], font=self._fuente_ui(0.82)
        )
        self.etiqueta_archivo.configure(
            bg=t["panel"], fg=t["suave"], font=self._fuente_ui(0.72)
        )
        self.etiqueta_dictado.configure(
            bg=t["panel"], fg=t["escucha"], font=self._fuente_ui(0.95, True)
        )
        self.pie.configure(bg=t["panel"], fg=t["suave"], font=self._fuente_ui(0.66))

        # Cada grupo con su color. El borde claro alrededor del bloque azul
        # es lo que lo hace localizable de un vistazo con baja visión.
        colores_grupo = {
            "comando": (t["destacado"], t["destacado_texto"]),
            "guardar": (t["guardar"], "#ffffff"),
            "archivo": (t["archivo"], "#ffffff"),
            "libre": (t["libre"], "#ffffff"),
            "corregir": (t["corregir"], "#ffffff"),
        }
        for boton, grupo in zip(self.botones, self.grupos_boton):
            fondo, letra = colores_grupo.get(grupo, (t["panel"], t["texto"]))
            boton.configure(
                bg=fondo, fg=letra,
                activebackground=t["acento"], activeforeground=t["fondo"],
                font=self._fuente_ui(0.7, True),
                highlightbackground="#ffffff", highlightcolor=t["acento"],
            )

        self.editor.configure(
            bg=t["editor"], fg=t["texto"],
            insertbackground=t["acento"],
            selectbackground=t["seleccion"], selectforeground=t["texto"],
            font=self._fuente_editor(),
            highlightbackground=t["borde"], highlightcolor=t["acento"],
        )
        self.barra.configure(
            bg=t["panel"], troughcolor=t["fondo"], activebackground=t["acento"],
        )

        self._disponer_botones()

    def _actualizar_titulo_ventana(self) -> None:
        """El título refleja el estado.

        Es la única información que un lector de pantalla externo lee bien
        de una ventana de tkinter, así que se aprovecha: al cambiar de
        ventana, NVDA anuncia el título y con él el archivo y el modo.
        """
        archivo = self.ruta_actual.name if self.ruta_actual else "Sin guardar"
        marca = "*" if self.modificado else ""
        modo = "editor" if self.modo == "editor" else "app externa"
        try:
            self.raiz.title(f"{marca}{archivo} — {modo} — VozClip Escritor {__version__}")
        except tk.TclError:
            pass

    def _construir_atajos_locales(self) -> None:
        """Atajos que funcionan cuando la ventana tiene el foco.

        Se registran además de los globales: si el escritor está dentro de
        VozClip, no dependen del escuchador externo, así que responden aunque
        pynput falle o Windows bloquee el hook.
        """
        enlaces = {
            "<F1>": self.accion_dictar,
            "<F2>": self.accion_nuevo_parrafo,
            "<F3>": self.accion_nuevo_dialogo,
            "<F4>": self.accion_leer_ultimo_parrafo,
            "<F5>": self.accion_leer_todo,
            "<F9>": self.accion_corregir,
            "<Escape>": self.accion_cancelar_correccion,
            "<Control-Alt-y>": self.accion_exportar_config,
            "<Control-Alt-Shift-J>": self.accion_perfil_julian,
            "<Control-Alt-F1>": self.accion_dictar,
            "<Control-Alt-g>": self.accion_insertar_plantilla,
            "<Control-Alt-n>": self.accion_cambiar_plantilla,
            "<Control-Alt-i>": self.accion_aplicar_sangria,
            "<Control-Alt-u>": self.accion_importar_config,
            "<Control-Alt-Shift-I>": self.accion_quitar_sangria,
            "<Control-Alt-o>": self.accion_importar,
            "<Control-Alt-e>": self.accion_exportar,
            "<Control-Alt-Shift-E>": self.accion_exportar_word,
            "<Control-Alt-Shift-L>": self.accion_exportar_libreoffice,
            "<Control-Alt-s>": self.accion_guardar_como,
            "<Control-Alt-c>": self.accion_alto_contraste,
            "<Control-Alt-plus>": self.accion_letra_mas_grande,
            "<Control-Alt-KP_Add>": self.accion_letra_mas_grande,
            "<Control-Alt-minus>": self.accion_letra_mas_pequena,
            "<Control-Alt-KP_Subtract>": self.accion_letra_mas_pequena,
            "<Control-Alt-z>": self.accion_modo_solo_voz,
            "<F6>": self.accion_siguiente_foco,
            "<Control-Alt-Return>": self.accion_siguiente_linea,
            "<Control-Alt-t>": self.accion_siguiente_marca,
            "<Control-Alt-d>": self.accion_guardar,
            "<Control-Alt-j>": self.accion_leer_linea,
            "<Control-Alt-k>": self.accion_leer_seleccion,
            "<Control-Alt-l>": self.accion_leer_portapapeles,
            "<Control-Alt-a>": self.accion_leer_todo,
            "<Control-Alt-p>": self.accion_pausar_reanudar,
            "<Control-Alt-x>": self.accion_parar,
            "<Control-Alt-Up>": self.accion_mas_rapido,
            "<Control-Alt-Down>": self.accion_mas_lento,
            "<Control-Alt-v>": self.accion_siguiente_voz,
            "<Control-Alt-m>": self.accion_cambiar_modo,
            "<Control-Alt-w>": self.accion_donde_estoy,
            "<Control-Alt-h>": self.accion_ayuda,
            "<Control-Alt-q>": self.accion_salir,
            "<Control-s>": self.accion_guardar,
            "<Control-o>": self.accion_importar,
        }
        for combinacion, funcion in enlaces.items():
            self.raiz.bind_all(combinacion, self._envolver_evento(funcion))

        # Al moverse con las flechas, decir la línea nueva. Es lo que hace
        # que se pueda navegar un guion sin ver nada.
        for tecla in ("<Up>", "<Down>"):
            self.editor.bind(tecla, self._anunciar_tras_mover)

    def _envolver_evento(self, funcion: Callable) -> Callable:
        """Envuelve un bind de tkinter para que pase por el guard de
        repetición con el MISMO nombre que usa la ruta global."""
        nombre = self._nombre_de_accion(funcion)

        def manejador(evento=None):
            self._disparar(nombre, funcion, origen="local")
            return "break"   # evita que tkinter procese la tecla dos veces

        return manejador

    def _nombre_de_accion(self, funcion: Callable) -> str:
        """El nombre con el que la ruta global conoce esta misma función."""
        for nombre, f in self.acciones().items():
            if f == funcion:
                return nombre
        return getattr(funcion, "__name__", repr(funcion))

    def _anunciar_tras_mover(self, evento=None):
        # after_idle: primero tkinter mueve el cursor, después leemos.
        self.raiz.after_idle(self.accion_leer_linea)
        return None

    # ==================================================================
    # Cola de órdenes (puente entre el hilo del teclado y este)
    # ==================================================================
    def encolar_orden(self, nombre: str) -> None:
        """Encola una orden que se ejecutará sí o sí (tests, prueba de humo)."""
        self.cola_ordenes.put(("directa", nombre))

    def encolar_orden_global(self, nombre: str) -> None:
        """La llama el escuchador de atajos globales, desde SU hilo.

        Se marca como "global" para que `_atender_cola` pueda descartarla si
        la ventana de VozClip tiene el foco. Motivo: cada tecla tiene DOS
        rutas, el `bind_all` de tkinter (funciona solo con el foco) y el
        atajo global de pynput (funciona siempre). Con la ventana enfocada,
        una sola pulsación de F3 llegaba por las dos y la raya salía doble;
        y F1 arrancaba el dictado y lo paraba 50 milisegundos después.
        """
        self.cola_ordenes.put(("global", nombre))

    VENTANA_REPETICION = 0.4   # segundos

    def _disparar(self, nombre: str, funcion, origen: str = "local") -> bool:
        """Ejecuta una acción salvo que sea una repetición inmediata.

        Devuelve True si se ejecutó. `nombre` es el de la acción (el mismo
        por las dos rutas), así que un F1 que llega por tkinter y 50 ms
        después por pynput cuenta como UNA pulsación.
        """
        import time as _time

        ahora = _time.monotonic()
        anterior = self._ultimo_disparo.get(nombre)
        if anterior is not None and ahora - anterior < self.VENTANA_REPETICION:
            return False
        self._ultimo_disparo[nombre] = ahora
        funcion()
        return True

    def _ventana_tiene_foco(self) -> bool:
        """¿El teclado está ahora mismo en la ventana de VozClip?

        `focus_get` devuelve el widget con foco si la aplicación está
        activa, y None si el foco está en otro programa. Solo se puede
        llamar desde el hilo principal, por eso la decisión se toma al
        atender la cola y no al encolar.
        """
        try:
            return self.raiz.focus_get() is not None
        except (KeyError, tk.TclError):
            return False

    def _atender_cola(self) -> None:
        """Corre en el hilo principal cada 50 ms y ejecuta lo pendiente.

        La primera línea no es paranoia. `after_cancel` no sirve de nada si
        el temporizador ya saltó y el callback está esperando turno en la
        cola de eventos de Tcl: se ejecutará igual, sobre un intérprete que
        puede estar ya destruido. Tcl responde a eso llamando a abort(), y
        el proceso entero se cae con "Fatal Python error: Aborted".
        """
        if self._cerrando:
            return
        try:
            if not self.raiz.winfo_exists():
                return
        except tk.TclError:
            return

        try:
            while True:
                origen, nombre = self.cola_ordenes.get_nowait()

                # Una orden global con la ventana enfocada ya la ha
                # ejecutado el bind_all de tkinter: descartarla evita el
                # doble disparo.
                if origen == "global" and self._ventana_tiene_foco():
                    continue

                funcion = self.acciones().get(nombre)
                if funcion:
                    try:
                        if origen == "directa":
                            # Tests y prueba de humo: no es una tecla física
                            # con dos rutas, así que no pasa por el guard.
                            funcion()
                        else:
                            self._disparar(nombre, funcion, origen=origen)
                    except Exception as e:
                        self.decir(f"Error en {nombre}: {type(e).__name__}")
        except queue.Empty:
            pass
        except tk.TclError:
            return

        # Los avisos del hilo de grabación se procesan aquí, en el hilo
        # principal, que es el único que puede tocar los widgets.
        try:
            self._atender_dictado()
        except tk.TclError:
            return    # la ventana ya no existe

        if not self._cerrando:
            # Se guarda el identificador para poder cancelarlo al cerrar:
            # si no, tkinter se queja de un 'after' huérfano.
            try:
                self._tarea_cola = self.raiz.after(50, self._atender_cola)
            except tk.TclError:
                self._tarea_cola = None

    def acciones(self) -> dict[str, Callable]:
        return {
            "dictar": self.accion_dictar,
            "nuevo_parrafo": self.accion_nuevo_parrafo,
            "nuevo_dialogo": self.accion_nuevo_dialogo,
            "leer_ultimo_parrafo": self.accion_leer_ultimo_parrafo,
            "exportar_word": self.accion_exportar_word,
            "exportar_libreoffice": self.accion_exportar_libreoffice,
            "importar_config": self.accion_importar_config,
            "exportar_config": self.accion_exportar_config,
            "perfil_julian": self.accion_perfil_julian,
            "importar": self.accion_importar,
            "exportar": self.accion_exportar,
            "guardar_como": self.accion_guardar_como,
            "alto_contraste": self.accion_alto_contraste,
            "letra_mas_grande": self.accion_letra_mas_grande,
            "letra_mas_pequena": self.accion_letra_mas_pequena,
            "modo_solo_voz": self.accion_modo_solo_voz,
            "insertar_plantilla": self.accion_insertar_plantilla,
            "cambiar_plantilla": self.accion_cambiar_plantilla,
            "aplicar_sangria": self.accion_aplicar_sangria,
            "quitar_sangria": self.accion_quitar_sangria,
            "siguiente_linea": self.accion_siguiente_linea,
            "siguiente_marca": self.accion_siguiente_marca,
            "guardar": self.accion_guardar,
            "leer_linea": self.accion_leer_linea,
            "leer_seleccion": self.accion_leer_seleccion,
            "leer_portapapeles": self.accion_leer_portapapeles,
            "leer_todo": self.accion_leer_todo,
            # F5 y Ctrl+Alt+A hacen lo mismo, con dos nombres
            "leer_texto_entero": self.accion_leer_todo,
            "corregir": self.accion_corregir,
            "cancelar_correccion": self.accion_cancelar_correccion,
            "pausar_reanudar": self.accion_pausar_reanudar,
            "parar": self.accion_parar,
            "mas_rapido": self.accion_mas_rapido,
            "mas_lento": self.accion_mas_lento,
            "siguiente_voz": self.accion_siguiente_voz,
            "cambiar_modo": self.accion_cambiar_modo,
            "donde_estoy": self.accion_donde_estoy,
            "ayuda": self.accion_ayuda,
            "salir": self.accion_salir,
        }

    # ==================================================================
    # Utilidades del editor
    # ==================================================================
    def decir(self, mensaje: str) -> None:
        if mensaje and self.ajustes.get("anunciar_acciones", True):
            self.voz.hablar(mensaje)

    def leer_en_voz(self, contenido: str) -> None:
        """Lee un texto largo troceado, para que el 'parar' responda al vuelo."""
        trozos = textoutil.trocear(contenido, 400)
        if not trozos:
            self.decir("No hay texto que leer.")
            return
        self.voz.hablar(trozos[0])
        for trozo in trozos[1:]:
            self.voz.encolar(trozo)

    def _texto(self) -> str:
        return self.editor.get("1.0", "end-1c")

    def _cursor(self) -> int:
        return len(self.editor.get("1.0", "insert"))

    def _reemplazar(self, nuevo: str, cursor: int) -> None:
        """Sustituye el contenido y coloca el cursor.

        Se hace con un reemplazo completo para que `documento.py` sea la
        única fuente de verdad de la lógica de edición. El coste es
        despreciable en documentos de guion (decenas de miles de caracteres)
        y tkinter sigue registrando el cambio para Ctrl+Z.
        """
        # Con `autoseparators`, Tk mete un separador entre el delete y el
        # insert, y un solo Ctrl+Z dejaba el editor VACÍO. Se desactiva
        # durante el reemplazo para que sea una unidad.
        self.editor.edit_separator()
        self.editor.configure(autoseparators=False)
        try:
            self.editor.delete("1.0", "end")
            self.editor.insert("1.0", nuevo)
        finally:
            self.editor.configure(autoseparators=True)
        self.editor.mark_set("insert", f"1.0 + {cursor} chars")
        self.editor.see("insert")
        self.editor.edit_separator()

    def _marcar_modificado(self, evento=None) -> None:
        if self.editor.edit_modified():
            self.modificado = True
            self.editor.edit_modified(False)
            self._refrescar_estado()

    def _refrescar_estado(self) -> None:
        nombre_modo = (
            "Editor propio" if self.modo == "editor" else "Aplicación externa"
        )
        velocidad = self.ajustes.get("velocidad", 0)
        self.etiqueta_estado.config(
            text=(
                f"Modo: {nombre_modo}    ·    "
                f"Plantilla: {self.plantilla.nombre}    ·    "
                f"Velocidad: {velocidad}    ·    "
                f"Tema: {self.tema['nombre']}    ·    "
                f"Letra: {self.tamano}"
            )
        )
        archivo = str(self.ruta_actual) if self.ruta_actual else "Sin guardar"
        if self.modificado:
            archivo += "   (cambios sin guardar)"
        self.etiqueta_archivo.config(text=archivo)
        self._actualizar_titulo_ventana()

    def _persistir(self) -> None:
        if self._guardar_ajustes:
            try:
                self._guardar_ajustes(self.ajustes)
            except Exception:
                pass

    # ==================================================================
    # Dictado por voz
    # ==================================================================
    def _preparar_dictado(self) -> None:
        """Crea el servicio de dictado. Nunca lanza excepción.

        Si falta el modelo, la librería o el micrófono, el resto del
        programa tiene que seguir funcionando exactamente igual: se avisa
        cuando se pulsa F1, no al arrancar.
        """
        self.cola_dictado: queue.Queue = queue.Queue()
        self.dictando = False
        self.servicio_dictado = None

        if self._fabrica_dictado is not None:
            try:
                self.servicio_dictado = self._fabrica_dictado(self._evento_dictado)
            except Exception:
                self.servicio_dictado = None
            return

        try:
            self.servicio_dictado = moddictado.ServicioDictado(
                notificar=self._evento_dictado,
                ajustes=self.ajustes.get("dictado", {}),
                voz=self.voz,
            )
        except Exception:
            self.servicio_dictado = None

    def _evento_dictado(self, tipo: str, dato) -> None:
        """Lo llama el HILO DE GRABACIÓN. Solo encola: nada de widgets."""
        self.cola_dictado.put((tipo, dato))

    def _atender_dictado(self) -> None:
        """Corre en el hilo principal, desde `_atender_cola`."""
        try:
            while True:
                tipo, dato = self.cola_dictado.get_nowait()
                self._procesar_evento_dictado(tipo, dato)
        except queue.Empty:
            pass

    def _procesar_evento_dictado(self, tipo: str, dato) -> None:
        if tipo == "inicio":
            self.dictando = True
            self.etiqueta_dictado.config(
                text="● ESCUCHANDO — pulsa F1 para terminar", fg=self.tema["escucha"]
            )
            if self.ajustes.get("dictado", {}).get("anunciar", True):
                self.voz.hablar("Escuchando")

        elif tipo == "parcial":
            # Solo información visual: hablar aquí interrumpiría al usuario
            # justo mientras dicta.
            if self.correccion is not None:
                self.etiqueta_dictado.config(text=f"● CORRIGIENDO — {dato}")
            else:
                self.etiqueta_dictado.config(text=f"● ESCUCHANDO — {dato}")

        elif tipo == "texto":
            if self._descartar_proximo_texto:
                self._descartar_proximo_texto = False
            elif self.correccion is not None:
                self._aplicar_correccion(dato)
            else:
                self.voz.hablar("Procesando")
                self._insertar_dictado(dato)

        elif tipo == "aviso":
            # Whisper no disponible y se usa vosk, por ejemplo. Se dice
            # una vez y el dictado sigue.
            self.etiqueta_dictado.config(text=f"Dictado: {dato}", fg=self.tema["listo"])
            self.voz.hablar(str(dato))

        elif tipo == "error":
            self.etiqueta_dictado.config(text=f"Dictado: {dato}", fg=self.tema["escucha"])
            self.voz.hablar(str(dato))

        elif tipo == "fin":
            self.dictando = False
            self._descartar_proximo_texto = False   # el ciclo acabó: nada que tirar
            if "ESCUCHANDO" in self.etiqueta_dictado.cget("text"):
                self.etiqueta_dictado.config(text="")
            self._refrescar_estado()

    def _insertar_dictado(self, reconocido: str) -> None:
        """Mete el texto dictado donde toca, según el modo."""
        if self.modo == "externo":
            listo = moddictado.formatear_para_insercion(reconocido, "")
            try:
                puente.pegar_en_ventana_activa(listo)
                self.voz.hablar(f"Escrito: {listo}")
            except Exception:
                self.voz.hablar("No he podido escribir en la aplicación externa.")
            return

        texto, cursor = self._texto(), self._cursor()

        # ¿Es una corrección dicha en mitad del dictado? "cambia alpiste por
        # rueda" con F1 se aplica como tal, no se escribe. Es lo que hace
        # cualquiera: la misma tecla con la que dictó.
        if texto.strip():
            ambito = correccion.ambito_parrafo(texto, cursor)
            orden = correccion.orden_durante_dictado(reconocido, texto, ambito)
            if orden is not None:
                self._corregir_desde_dictado(orden, ambito)
                return

        # El contexto decide mayúscula inicial y espacio de separación.
        contexto = documento.contexto_antes_del_cursor(texto, cursor)
        listo = moddictado.formatear_para_insercion(reconocido, contexto)

        # La sangría vigente se propaga a los saltos de línea del dictado,
        # para no descuadrar la plantilla.
        sangria = documento.sangria_de_linea(documento.linea_actual(texto, cursor))
        nuevo, ncursor = documento.insertar_dictado(texto, cursor, listo, sangria)

        self._reemplazar(nuevo, ncursor)
        self.modificado = True
        self._refrescar_estado()
        recordatorio = ""
        if self.ajustes.get("correccion", {}).get("recordatorio", True) \
                and len(listo.split()) >= 4:
            recordatorio = " Para corregir, di: cambia, la palabra, por, la buena."
        frase = listo.strip()
        if frase and frase[-1] not in ".!?…":
            frase += "."
        self.voz.hablar(f"Escrito: {frase}{recordatorio}")

    def accion_dictar(self) -> None:
        """F1: empieza o termina el dictado."""
        if self.servicio_dictado is None:
            self.voz.hablar(
                "El dictado no está disponible en este ordenador. "
                "Ejecuta el diagnóstico para saber qué falta."
            )
            self.etiqueta_dictado.config(text="Dictado no disponible", fg=self.tema["suave"])
            return

        if self.dictando:
            self.etiqueta_dictado.config(text="Procesando…", fg=self.tema["listo"])
            self.servicio_dictado.detener(esperar=0)     # sin congelar la ventana
            return

        motivo = self.servicio_dictado.motivo_no_disponible()
        if motivo:
            self.voz.hablar(motivo)
            self.etiqueta_dictado.config(text=f"Dictado: {motivo}", fg=self.tema["suave"])
            return

        # Callar la voz antes de abrir el micrófono: si no, el programa se
        # graba a sí mismo y transcribe sus propios anuncios.
        self.voz.parar()
        self.servicio_dictado.empezar()

    # ==================================================================
    # Accesibilidad: contraste, tamaño de letra y modo solo voz
    # ==================================================================
    def accion_alto_contraste(self) -> None:
        """Rota entre los tres temas y lo dice en voz alta."""
        actual = self.ajustes.get("tema", "oscuro")
        try:
            siguiente = ORDEN_TEMAS[(ORDEN_TEMAS.index(actual) + 1) % len(ORDEN_TEMAS)]
        except ValueError:
            siguiente = ORDEN_TEMAS[0]

        self.ajustes["tema"] = siguiente
        self._aplicar_tema()
        self._refrescar_estado()
        self._persistir()
        self.voz.hablar(f"Tema {TEMAS[siguiente]['nombre']}")

    def accion_letra_mas_grande(self) -> None:
        self._cambiar_tamano(2)

    def accion_letra_mas_pequena(self) -> None:
        self._cambiar_tamano(-2)

    def _cambiar_tamano(self, delta: int) -> int:
        nuevo = max(TAMANO_MINIMO, min(TAMANO_MAXIMO, self.tamano + delta))
        if nuevo == self.tamano:
            self.voz.hablar(
                "Ya está en el tamaño máximo." if delta > 0
                else "Ya está en el tamaño mínimo."
            )
            return nuevo

        self.ajustes["tamano_fuente"] = nuevo
        self._aplicar_tema()      # reescala botones y rótulos, no solo el texto
        self._refrescar_estado()  # la franja muestra el tamaño vigente
        self._persistir()
        self.voz.hablar(f"Letra a {nuevo} puntos")
        return nuevo

    def accion_modo_solo_voz(self) -> None:
        """Encoge la ventana a una franja mínima, o la restaura.

        Para quien no mira la pantalla, una ventana grande solo estorba:
        tapa lo que haya detrás y no aporta nada. En modo solo voz queda
        una barra con el estado, y todo sigue funcionando por teclado y
        por voz exactamente igual.
        """
        activar = not self.ajustes.get("solo_voz", False)
        self.ajustes["solo_voz"] = activar
        self._aplicar_solo_voz(activar)
        self._persistir()

        if activar:
            self.voz.hablar(
                "Modo solo voz. La ventana se ha reducido. Todos los atajos "
                "siguen funcionando. Control alt zeta para volver."
            )
        else:
            self.voz.hablar("Ventana completa.")

    def _aplicar_solo_voz(self, activar: bool) -> None:
        if activar:
            self.botonera.pack_forget()
            self.marco_editor.pack_forget()
            self.pie.pack_forget()
            self.raiz.geometry("560x150")
        else:
            # Se reempaqueta en el orden correcto: cabecera (ya está),
            # botonera, editor y pie al fondo.
            self.botonera.pack(fill="x", after=self.cabecera)
            self.marco_editor.pack(fill="both", expand=True, padx=14, pady=(0, 12))
            self.pie.pack(fill="x", side="bottom")
            self.raiz.geometry("1100x740")
            self.editor.focus_set()
        self._refrescar_estado()

    def accion_siguiente_foco(self) -> None:
        """F6: salta entre el editor y la fila de botones.

        Con Tab se recorre todo de uno en uno; con F6 se salta de zona,
        que es mucho más rápido cuando no ves dónde está el foco.
        """
        try:
            actual = self.raiz.focus_get()
        except (KeyError, tk.TclError):
            actual = None

        if actual is self.editor:
            if self.botones:
                self.botones[0].focus_set()
        else:
            self.editor.focus_set()
            self.decir("Editor")

    # ==================================================================
    # Importar y exportar
    # ==================================================================
    def accion_importar(self) -> None:
        """Ctrl+Alt+O: abre un archivo dentro del editor propio.

        En modo externo también funciona: se importa aquí y luego se puede
        exportar a la aplicación de destino.
        """
        from tkinter import filedialog

        ruta = filedialog.askopenfilename(
            title="Abrir guion",
            initialdir=str(cfg.carpeta_guiones(self.ajustes)),
            filetypes=[
                ("Todos los admitidos", "*.txt *.md *.rtf *.docx"),
                ("Texto", "*.txt *.md"),
                ("Texto enriquecido", "*.rtf"),
                ("Word", "*.docx"),
                ("Todos", "*.*"),
            ],
        )
        if not ruta:
            self.decir("Importación cancelada.")
            return
        self.abrir(Path(ruta))

    def accion_exportar(self) -> None:
        """Ctrl+Alt+E: saca el documento de VozClip.

        En modo editor, lo copia entero al portapapeles: desde ahí se pega
        donde sea. En modo externo, lo escribe directamente en la
        aplicación que tenga el foco.
        """
        contenido = self._texto()
        if not contenido.strip():
            self.decir("El documento está vacío. No hay nada que exportar.")
            return

        if self.modo == "externo":
            destino = puente.describir_destino()
            try:
                metodo = puente.insertar_texto(contenido)
            except ErrorFuente as e:
                self.voz.hablar(str(e))
                return
            self.voz.hablar(
                f"Documento escrito en {destino}."
                + (" Tecleado letra a letra." if metodo == "teclear" else "")
            )
            return

        try:
            escribir_portapapeles(contenido)
        except Exception:
            self.voz.hablar("No he podido copiar al portapapeles.")
            return

        palabras = len(contenido.split())
        self.voz.hablar(
            f"Documento copiado al portapapeles: {palabras} palabras. "
            "Ya lo puedes pegar donde quieras con control uve."
        )

    def accion_importar_de_app_externa(self) -> None:
        """Trae a VozClip el documento de la aplicación activa.

        Selecciona todo allí, lo copia y lo carga aquí. Es la vía rápida
        para trabajar sobre algo que ya está abierto en Word.
        """
        try:
            contenido = puente.capturar_todo()
        except ErrorFuente as e:
            self.voz.hablar(str(e))
            return
        self._reemplazar(contenido, 0)
        self.ruta_actual = None
        self.modificado = True
        self._refrescar_estado()
        self.voz.hablar(
            f"Importado de la aplicación externa. "
            f"{documento.resumen_documento(contenido)}"
        )

    # ==================================================================
    # Los comandos de todos los días
    # ==================================================================
    def accion_nuevo_parrafo(self) -> None:
        """F2: abre un párrafo nuevo con la sangría de la plantilla."""
        sangria = self.plantilla.sangria_parrafo

        if self.modo == "externo":
            puente.enviar_salto_de_linea()
            puente.enviar_salto_de_linea(sangria)
            self.voz.hablar("Nuevo párrafo")
            return

        texto, cursor = self._texto(), self._cursor()
        nuevo, ncursor = documento.nuevo_parrafo(texto, cursor, sangria)
        self._reemplazar(nuevo, ncursor)
        self.modificado = True
        self._refrescar_estado()
        self.voz.hablar("Nuevo párrafo")

    def accion_nuevo_dialogo(self) -> None:
        """F3: abre una intervención hablada.

        Inserta EXACTAMENTE dos cosas, siempre, en todas las plantillas:

            1. La sangría de diálogo: dos espacios, que son los 0,63 cm del
               documento de estilo traducidos a una fuente monoespaciada.
            2. La raya (—, U+2014), pegada a la sangría.

        Y deja el cursor justo detrás, sin espacio. En castellano la raya de
        diálogo va pegada a la primera palabra: "—No me lo creo".

        Nada más. Ni nombre de personaje, ni verbo dicendi, ni marcas de
        relleno. El nombre de personaje se insertaba en las plantillas de
        teatro y cine, que se han retirado precisamente por esto.
        """
        plantilla = self.plantilla
        sangria = plantilla.sangria_dialogo
        marca = plantilla.marca_dialogo or "—"

        if self.modo == "externo":
            puente.enviar_salto_de_linea()
            puente.insertar_texto(f"{sangria}{marca}", metodo="teclear")
            self.voz.hablar("Nuevo diálogo")
            return

        texto, cursor = self._texto(), self._cursor()
        nuevo, ncursor = documento.nuevo_dialogo(
            texto, cursor, marca=marca, sangria_dialogo=sangria,
        )
        self._reemplazar(nuevo, ncursor)
        self.modificado = True
        self._refrescar_estado()
        self.voz.hablar("Nuevo diálogo")

    def _corregir_desde_dictado(self, orden, ambito) -> None:
        """Aplica una orden de corrección llegada por F1 (dictado normal)."""
        if orden.tipo == "cambiar" and orden.poner:
            orden.poner = moddictado.aplicar_puntuacion(orden.poner)
            if orden.poner[:1].isupper() and len(orden.poner) > 1:
                orden.poner = orden.poner[0].lower() + orden.poner[1:]
        resultado = correccion.aplicar(self._texto(), orden, ambito)
        if resultado.opciones:
            # Varias apariciones: se abre el flujo de F9 en la fase de
            # elegir, para no adivinar.
            self.correccion = {"ambito": ambito, "fase": "elegir_aparicion",
                               "opciones": resultado.opciones, "orden": orden,
                               "elegidas": None}
            self.etiqueta_dictado.config(
                text="● CORRIGIENDO — di el número y pulsa F1",
                fg=self.tema["corregir"],
            )
            self.voz.hablar(resultado.mensaje)
            self._escuchar_orden()
            return
        if not resultado.aplicado:
            self.voz.hablar(resultado.mensaje)
            return
        ini, fin = ambito
        desplazamiento = len(resultado.texto) - len(self._texto())
        self._reemplazar(resultado.texto, fin + desplazamiento)
        self.modificado = True
        self._refrescar_estado()
        self.voz.hablar(resultado.mensaje)

    # ==================================================================
    # Corrección por voz: "cambia casa por cosa"
    # ==================================================================
    def accion_corregir(self) -> None:
        """F9: corregir una palabra por voz.

        Dos modos, en `correccion.modo` del config.json:

          * "directo" (por defecto): F9, dices el cambio ("cambia casa por
            cosa"), F9. Una sola escucha. Si no sabes cómo se dice la
            palabra mal reconocida, dices "léelo" y pasas al guiado.
          * "numerado": F9 lee el párrafo con cada palabra numerada,
            pregunta cuál, la lee para confirmar, y pide la palabra nueva.
            Tres escuchas, pero nunca hay que pronunciar la palabra
            equivocada.

        Primera pulsación: empieza. Cada pulsación siguiente: para la
        escucha en curso y procesa. Escape: cancela.
        """
        if self.servicio_dictado is None:
            self.voz.hablar("Para corregir por voz hace falta el dictado, y no está disponible.")
            return

        if self.dictando and self.correccion is not None:
            self.etiqueta_dictado.config(text="Procesando la corrección…", fg=self.tema["listo"])
            self.servicio_dictado.detener(esperar=0)     # segunda pulsación: procesar
            return

        if self.dictando:
            self.voz.hablar("Termina el dictado primero, con efe uno.")
            return

        motivo = self.servicio_dictado.motivo_no_disponible()
        if motivo:
            self.voz.hablar(motivo)
            return

        if self.modo == "externo":
            try:
                linea = puente.capturar_linea_actual()
            except ErrorFuente as e:
                self.voz.hablar(str(e))
                return
            self.correccion = {"ambito": (0, len(linea)), "linea_externa": linea}
        else:
            texto = self._texto()
            if not texto.strip():
                self.voz.hablar("No hay nada escrito que corregir.")
                return
            self.correccion = {"ambito": correccion.ambito_parrafo(texto, self._cursor())}

        self.correccion.update({"fase": "orden", "opciones": None, "orden": None,
                                "elegidas": None})
        self.etiqueta_dictado.config(
            text="● CORRIGIENDO — di el cambio y pulsa F9", fg=self.tema["corregir"],
        )
        self.voz.parar()

        modo = self.ajustes.get("correccion", {}).get("modo", "directo")
        if modo == "numerado":
            self._fase_elegir_numero()
        else:
            self.voz.hablar("Dime el cambio. Por ejemplo, cambia casa por cosa.")
            self._escuchar_orden()

    def _segundos_de_silencio(self) -> float:
        """Cuánto silencio tras la orden para aplicarla sola. Cero = manual."""
        return float(self.ajustes.get("correccion", {}).get("parar_tras_silencio", 1.5))

    def _escuchar_orden(self) -> None:
        """Escucha una orden de corrección, con parada automática al callar."""
        self.servicio_dictado.empezar(parar_tras_silencio=self._segundos_de_silencio())

    def accion_cancelar_correccion(self) -> None:
        """Escape: dejar la corrección sin tocar nada."""
        if self.correccion is None:
            return
        # Se mira el estado REAL del servicio, no `self.dictando`, que solo
        # se activa al procesar el evento "inicio": si Escape llega antes,
        # el texto en camino se colaría como dictado normal.
        en_marcha = (
            self.servicio_dictado.activo
            or self.dictando
            or not self.cola_dictado.empty()
        )
        if en_marcha:
            self._descartar_proximo_texto = True
            self.servicio_dictado.detener(esperar=0)
        self.correccion = None
        self.etiqueta_dictado.config(text="")
        self.voz.hablar("Corrección cancelada.")

    # -- Fases del flujo guiado ---------------------------------------------
    def _texto_a_corregir(self) -> str:
        estado = self.correccion or {}
        if "linea_externa" in estado:
            return estado["linea_externa"]
        return self._texto()

    def _fase_elegir_numero(self) -> None:
        """Lee el párrafo numerado y espera un número (o un cambio entero)."""
        ini, fin = self.correccion["ambito"]
        self.correccion["fase"] = "elegir_numero"
        self.etiqueta_dictado.config(text="● CORRIGIENDO — di el número de la palabra y pulsa F9")
        self.voz.hablar(
            correccion.enumerar(self._texto_a_corregir()[ini:fin])
            + " ¿Cuál cambio? Di el número, o del dos al cuatro."
        )
        self._escuchar_orden()

    def _fase_dictar_nueva(self, elegidas: list) -> None:
        """Lee lo elegido para confirmar y pide la palabra nueva."""
        self.correccion["fase"] = "dictar_nueva"
        self.correccion["elegidas"] = elegidas
        que = " ".join(c.texto for c in elegidas)
        self.etiqueta_dictado.config(text=f"● CORRIGIENDO — dicta lo que sustituye a «{que}» y pulsa F9")
        self.voz.hablar(f"{que}. Dime la palabra correcta, o di borrar.")
        self._escuchar_orden()

    def _terminar_correccion(self, resultado) -> None:
        """Aplica el resultado al editor o a la app externa y cierra."""
        estado = self.correccion
        if "linea_externa" in estado:
            try:
                puente.reemplazar_linea_actual(resultado.texto)
            except ErrorFuente as e:
                self.voz.hablar(str(e))
                self.correccion = None
                self.etiqueta_dictado.config(text="")
                return
        else:
            # El cursor queda al final del párrafo corregido: lo natural es
            # seguir dictando desde ahí, no en mitad de la frase.
            ini, fin = estado["ambito"]
            desplazamiento = len(resultado.texto) - len(self._texto())
            self._reemplazar(resultado.texto, fin + desplazamiento)
            self.modificado = True
        self.correccion = None
        self.etiqueta_dictado.config(text="")
        self._refrescar_estado()
        self.voz.hablar(resultado.mensaje)

    def _aplicar_correccion(self, dicho: str) -> None:
        """Llega lo dicho tras F9. Qué hacer depende de la fase."""
        estado = self.correccion
        if estado is None:
            return

        orden = correccion.interpretar_orden(dicho)
        if orden.tipo == "cancelar":
            self.accion_cancelar_correccion()
            return
        if orden.tipo == "deshacer" and estado["fase"] == "orden":
            try:
                self.editor.edit_undo()
                self.voz.hablar("Deshecho.")
            except tk.TclError:
                self.voz.hablar("No hay nada que deshacer.")
            self.correccion = None
            self.etiqueta_dictado.config(text="")
            return

        fase = estado["fase"]
        texto = self._texto_a_corregir()
        ambito = estado["ambito"]

        # --- Esperábamos un número entre varias apariciones ----------------
        if fase == "elegir_aparicion":
            numeros = correccion._numeros_en(dicho)
            if not numeros:
                self.voz.hablar("Di solo el número. O di cancela.")
                self._escuchar_orden()
                return
            resultado = correccion.aplicar(texto, estado["orden"], ambito, eleccion=numeros[0])
            if resultado.aplicado:
                self._terminar_correccion(resultado)
            else:
                self.voz.hablar(resultado.mensaje)
                self._escuchar_orden()
            return

        # --- Esperábamos el número de palabra (flujo guiado) ---------------
        if fase == "elegir_numero":
            # "la tres por cosa" de una vez también vale
            if orden.tipo in ("cambiar", "borrar") and (orden.indices or orden.buscar):
                self._resolver_orden(orden)
                return
            if orden.tipo == "numerar":
                self._fase_elegir_numero()
                return
            numeros = correccion._numeros_en(dicho)
            if not numeros:
                self.voz.hablar("No he oído un número. Di, por ejemplo, tres. O del dos al cuatro.")
                self._escuchar_orden()
                return
            indices = list(range(numeros[0], numeros[-1] + 1)) if "a" in dicho.split() or "al" in dicho.split() else numeros
            elegidas = correccion.por_indices(texto, indices, ambito)
            if not elegidas:
                self.voz.hablar("No hay tantas palabras. Di otro número.")
                self._escuchar_orden()
                return
            if len(elegidas) > 1 and indices == list(range(indices[0], indices[-1] + 1)):
                primera, ultima = elegidas[0], elegidas[-1]
                elegidas = [correccion.Coincidencia(
                    primera.inicio, ultima.fin, texto[primera.inicio:ultima.fin], primera.contexto)]
            self._fase_dictar_nueva(elegidas)
            return

        # --- Esperábamos la palabra nueva (flujo guiado) -------------------
        if fase == "dictar_nueva":
            elegidas = estado["elegidas"]
            quitado = " y ".join(c.texto for c in elegidas)
            if orden.tipo == "borrar" and not orden.buscar and not orden.indices:
                # "borrar" a secas: quitar lo elegido
                nuevo_texto = correccion.sustituir(texto, elegidas, "")
                self._terminar_correccion(correccion.Resultado(
                    nuevo_texto, f"He borrado {quitado}.", aplicado=True))
                return
            nueva = moddictado.aplicar_puntuacion(dicho.strip())
            if nueva[:1].isupper() and len(nueva) > 1:
                nueva = nueva[0].lower() + nueva[1:]
            if not nueva:
                self.voz.hablar("No he entendido la palabra. Repítela.")
                self._escuchar_orden()
                return
            nuevo_texto = correccion.sustituir(texto, elegidas, nueva)
            self._terminar_correccion(correccion.Resultado(
                nuevo_texto, f"He cambiado {quitado} por {nueva}.", aplicado=True))
            return

        # --- Fase "orden": el modo directo -----------------------------------
        if orden.tipo == "numerar":
            self._fase_elegir_numero()
            return
        self._resolver_orden(orden)

    def _resolver_orden(self, orden) -> None:
        """Aplica una orden completa ("cambia X por Y", "borra X", "la 3 por Y")."""
        estado = self.correccion
        if orden.tipo == "cambiar" and orden.poner:
            orden.poner = moddictado.aplicar_puntuacion(orden.poner)
            if orden.poner[:1].isupper() and len(orden.poner) > 1:
                orden.poner = orden.poner[0].lower() + orden.poner[1:]
        resultado = correccion.aplicar(self._texto_a_corregir(), orden, estado["ambito"])
        estado["orden"] = orden

        if resultado.opciones:
            estado["fase"] = "elegir_aparicion"
            estado["opciones"] = resultado.opciones
            self.voz.hablar(resultado.mensaje)
            self._escuchar_orden()
            return
        if not resultado.aplicado:
            estado["fase"] = "orden"
            self.voz.hablar(resultado.mensaje)
            self._escuchar_orden()
            return
        self._terminar_correccion(resultado)

    def accion_leer_ultimo_parrafo(self) -> None:
        """F4: lee el párrafo en el que está el cursor, o el último escrito.

        Es lo que más se usa al dictar: acabas de soltar tres frases y
        quieres oír cómo han quedado, sin escuchar el capítulo entero.
        """
        if self.modo == "externo":
            try:
                self.leer_en_voz(puente.capturar_linea_actual())
            except ErrorFuente as e:
                self.voz.hablar(str(e))
            return

        texto = self._texto()
        if not texto.strip():
            self.voz.hablar("El documento está vacío.")
            return

        parrafo = documento.parrafo_actual(texto, self._cursor())
        if not parrafo:
            parrafo = documento.ultimo_parrafo(texto)

        if not parrafo:
            self.voz.hablar("No hay ningún párrafo escrito todavía.")
            return

        self.voz.hablar("Leyendo el último párrafo.")
        self.voz.encolar(parrafo)

    # ==================================================================
    # Perfiles de configuración
    # ==================================================================
    def accion_exportar_config(self) -> None:
        """Ctrl+Alt+Y: guarda los ajustes actuales como perfil."""
        from . import perfiles

        try:
            ruta = perfiles.exportar(self.ajustes)
        except ErrorFuente as e:
            self.voz.hablar(str(e))
            return
        self.voz.hablar(f"Configuración guardada como {ruta.name}")

    def accion_importar_config(self) -> None:
        """Ctrl+Alt+U: carga un perfil y lo aplica al momento."""
        from tkinter import filedialog

        from . import perfiles

        ruta = filedialog.askopenfilename(
            title="Abrir perfil de configuración",
            initialdir=str(perfiles.carpeta_perfiles()),
            filetypes=[("Perfiles de VozClip", "*.json"), ("Todos", "*.*")],
        )
        if not ruta:
            self.voz.hablar("Importación cancelada.")
            return
        self.cargar_perfil(ruta)

    def cargar_perfil(self, ruta) -> bool:
        """Aplica un perfil de golpe: tema, letra, voz, plantilla y atajos."""
        from . import perfiles

        try:
            nuevos = perfiles.importar(ruta, base=self.ajustes)
        except ErrorFuente as e:
            self.voz.hablar(str(e))
            return False

        self.ajustes.clear()
        self.ajustes.update(nuevos)

        # Todo lo que el perfil puede haber cambiado se vuelve a aplicar.
        self.plantilla = plantillas.obtener(self.ajustes.get("plantilla", "novela"))
        self.modo = self.ajustes.get("modo", "editor")
        self.voz.poner_velocidad(self.ajustes.get("velocidad", 0))
        self.voz.poner_volumen(self.ajustes.get("volumen", 100))
        if self.ajustes.get("voz"):
            self.voz.poner_voz(self.ajustes["voz"])
        self._aplicar_tema()
        self._aplicar_solo_voz(self.ajustes.get("solo_voz", False))
        self._refrescar_estado()
        self._persistir()

        self.voz.hablar(perfiles.describir(nuevos, perfiles.nombre_de(ruta)))
        return True

    def accion_perfil_julian(self) -> None:
        """Vuelve al perfil de fábrica de Julián.

        Es la salida de emergencia: si algo se descoloca y no se puede ver
        la pantalla para arreglarlo, esto devuelve el programa a un estado
        conocido con una sola combinación de teclas.
        """
        from . import perfiles

        self.ajustes.clear()
        self.ajustes.update(perfiles.perfil_julian())
        self.plantilla = plantillas.obtener(self.ajustes["plantilla"])
        self.voz.poner_velocidad(self.ajustes["velocidad"])
        self._aplicar_tema()
        self._refrescar_estado()
        self._persistir()
        self.voz.hablar("Perfil de Julián restaurado.")

    # ==================================================================
    # Exportar a Word con el formato de verdad
    # ==================================================================
    def accion_exportar_word(self) -> None:
        """Ctrl+Alt+W: guarda un .docx con las medidas exactas.

        En el editor las sangrías son espacios aproximados. Aquí se aplican
        los centímetros y los puntos del documento de estilo: es el archivo
        que se puede mandar a alguien.
        """
        from . import exportar_word

        contenido = self._texto()
        if not contenido.strip():
            self.voz.hablar("El documento está vacío. No hay nada que exportar.")
            return

        if self.ruta_actual is not None:
            destino = self.ruta_actual.with_suffix(".docx")
        else:
            marca = _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
            destino = cfg.carpeta_guiones(self.ajustes) / f"guion_{marca}.docx"

        try:
            exportar_word.exportar(contenido, destino, self.plantilla)
        except ErrorFuente as e:
            self.voz.hablar(str(e))
            return

        self.voz.hablar(
            f"Exportado a Word como {destino.name}. "
            f"{exportar_word.describir_formato(self.plantilla)}"
        )

    def accion_exportar_libreoffice(self) -> None:
        """Ctrl+Alt+Mayús+L: guarda un .odt para LibreOffice Writer.

        Es el formato nativo de LibreOffice: no hay conversión por medio y
        las medidas del documento de estilo llegan exactas.
        """
        from . import exportar_odt, exportar_word

        contenido = self._texto()
        if not contenido.strip():
            self.voz.hablar("El documento está vacío. No hay nada que exportar.")
            return

        if self.ruta_actual is not None:
            destino = self.ruta_actual.with_suffix(".odt")
        else:
            marca = _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
            destino = cfg.carpeta_guiones(self.ajustes) / f"guion_{marca}.odt"

        try:
            exportar_odt.exportar(contenido, destino, self.plantilla)
        except ErrorFuente as e:
            self.voz.hablar(str(e))
            return

        self.voz.hablar(
            f"Exportado a LibreOffice como {destino.name}. "
            f"{exportar_word.describir_formato(self.plantilla)}"
        )

    # ==================================================================
    # Acciones de escritura
    # ==================================================================
    def accion_insertar_plantilla(self) -> None:
        insercion = plantillas.preparar(self.plantilla)

        if self.modo == "externo":
            try:
                puente.pegar_en_ventana_activa(insercion.texto)
                self.decir(f"Plantilla {self.plantilla.nombre} pegada.")
            except Exception:
                self.decir("No he podido pegar en la aplicación externa.")
            return

        texto, cursor = self._texto(), self._cursor()
        nuevo, _ = documento.insertar(texto, cursor, insercion.texto)

        # Las marcas del texto insertado se desplazan por el cursor previo
        self.marcas = [cursor + p for p in insercion.posiciones]
        destino = self.marcas[0] if self.marcas else cursor + len(insercion.texto)

        self._reemplazar(nuevo, destino)
        self.decir(
            f"Plantilla {self.plantilla.nombre} insertada. "
            f"{len(self.marcas)} huecos. Control alt te para el siguiente."
        )
        self._refrescar_estado()

    def accion_cambiar_plantilla(self) -> None:
        siguiente = plantillas.siguiente_clave(self.plantilla.clave)
        self.plantilla = plantillas.obtener(siguiente)
        self.ajustes["plantilla"] = siguiente
        self._persistir()
        self._refrescar_estado()
        self.voz.hablar(plantillas.describir(self.plantilla))

    def accion_siguiente_marca(self) -> None:
        if not self.marcas:
            self.decir("No hay huecos pendientes.")
            return
        destino = documento.siguiente_marca(self.marcas, self._cursor())
        if destino is None:
            self.decir("No hay huecos pendientes.")
            return
        self.editor.mark_set("insert", f"1.0 + {destino} chars")
        self.editor.see("insert")
        self.accion_leer_linea()

    def accion_aplicar_sangria(self) -> None:
        sangria = self.plantilla.sangria_parrafo

        if self.modo == "externo":
            from pynput.keyboard import Controller

            Controller().type(sangria)
            self.decir("Sangría aplicada.")
            return

        texto, cursor = self._texto(), self._cursor()
        nuevo, ncursor = documento.aplicar_sangria(texto, cursor, sangria)
        self._reemplazar(nuevo, ncursor)
        self.decir(f"Sangría de {len(sangria)} espacios.")

    def accion_quitar_sangria(self) -> None:
        if self.modo == "externo":
            self.decir("Quitar sangría solo funciona en el editor propio.")
            return
        texto, cursor = self._texto(), self._cursor()
        nuevo, ncursor = documento.quitar_sangria(
            texto, cursor, self.plantilla.sangria_parrafo
        )
        if nuevo == texto:
            self.decir("Esta línea no tiene sangría.")
            return
        self._reemplazar(nuevo, ncursor)
        self.decir("Sangría quitada.")

    def accion_siguiente_linea(self) -> None:
        if self.modo == "externo":
            puente.enviar_salto_de_linea()
            self.decir("Nueva línea.")
            return

        texto, cursor = self._texto(), self._cursor()
        nuevo, ncursor = documento.siguiente_linea(texto, cursor)
        self._reemplazar(nuevo, ncursor)
        numero = documento.numero_linea(nuevo, ncursor)
        self.decir(f"Línea {numero}.")

    # ==================================================================
    # Acciones de lectura
    # ==================================================================
    def accion_leer_linea(self) -> None:
        if self.modo == "externo":
            try:
                self.leer_en_voz(puente.capturar_linea_actual())
            except ErrorFuente as e:
                self.decir(str(e))
            return
        self.voz.hablar(documento.contexto_para_voz(self._texto(), self._cursor()))

    def accion_leer_seleccion(self) -> None:
        if self.modo == "externo":
            from .fuentes import capturar_seleccion

            try:
                self.leer_en_voz(capturar_seleccion())
            except ErrorFuente as e:
                self.decir(str(e))
            return

        try:
            seleccion = self.editor.get("sel.first", "sel.last")
        except tk.TclError:
            self.decir("No hay nada seleccionado.")
            return
        self.leer_en_voz(seleccion)

    def accion_leer_portapapeles(self) -> None:
        try:
            contenido = leer_portapapeles()
        except ErrorFuente as e:
            self.decir(str(e))
            return
        if not contenido.strip():
            self.decir("El portapapeles está vacío.")
            return
        self.leer_en_voz(contenido)

    def accion_leer_todo(self) -> None:
        contenido = self._texto()
        if not contenido.strip():
            self.decir("El documento está vacío.")
            return
        self.leer_en_voz(contenido)

    def accion_pausar_reanudar(self) -> None:
        if self.voz.pausado:
            self.voz.reanudar()
        else:
            self.voz.pausar()

    def accion_parar(self) -> None:
        self.voz.parar()

    def accion_donde_estoy(self) -> None:
        texto = self._texto()
        cursor = self._cursor()
        modo = "editor propio" if self.modo == "editor" else "aplicación externa"
        archivo = self.ruta_actual.name if self.ruta_actual else "documento sin guardar"
        estado_dictado = (
            "Dictando." if self.dictando
            else "Dictado listo." if self.servicio_dictado is not None
            and not self.servicio_dictado.motivo_no_disponible()
            else "Dictado no disponible."
        )
        self.voz.hablar(
            f"VozClip {version_hablada()}. "
            f"Modo {modo}. Plantilla {self.plantilla.nombre}. {archivo}. "
            f"{estado_dictado} "
            f"{documento.resumen_documento(texto)} "
            f"{documento.contexto_para_voz(texto, cursor)}"
        )

    # ==================================================================
    # Ajustes
    # ==================================================================
    def accion_mas_rapido(self) -> None:
        self._cambiar_velocidad(1)

    def accion_mas_lento(self) -> None:
        self._cambiar_velocidad(-1)

    def _cambiar_velocidad(self, delta: int) -> None:
        nueva = max(-10, min(10, int(self.ajustes.get("velocidad", 0)) + delta))
        self.ajustes["velocidad"] = nueva
        self.voz.poner_velocidad(nueva)
        self._persistir()
        self._refrescar_estado()
        self.voz.hablar(f"Velocidad {nueva}")

    def accion_siguiente_voz(self) -> None:
        disponibles = self.voz.voces()
        if not disponibles:
            self.decir("No hay voces instaladas.")
            return
        actual = self.ajustes.get("voz")
        indice = disponibles.index(actual) if actual in disponibles else -1
        elegida = disponibles[(indice + 1) % len(disponibles)]
        self.voz.poner_voz(elegida)
        self.ajustes["voz"] = elegida
        self._persistir()
        self.voz.hablar(f"Voz {elegida}")

    def accion_cambiar_modo(self) -> None:
        self.modo = "externo" if self.modo == "editor" else "editor"
        self.ajustes["modo"] = self.modo
        self._persistir()
        self._refrescar_estado()
        if self.modo == "externo":
            destino = puente.describir_destino()
            self.voz.hablar(
                f"Modo aplicación externa. Voy a escribir en: {destino}."
            )
        else:
            self.voz.hablar("Modo editor propio.")
            self.editor.focus_set()

    def accion_ayuda(self) -> None:
        self.leer_en_voz(AYUDA_HABLADA)

    # ==================================================================
    # Archivos
    # ==================================================================
    def accion_guardar(self) -> None:
        if self.modo == "externo":
            puente.guardar_en_app_activa()
            self.decir("Guardado enviado a la aplicación externa.")
            return

        if self.ruta_actual is None:
            # Nombre automático: nada de diálogos que el escritor no ve.
            marca = _dt.datetime.now().strftime("%Y-%m-%d_%H%M")
            self.ruta_actual = cfg.carpeta_guiones(self.ajustes) / f"guion_{marca}.txt"

        try:
            fuentes.guardar_texto(self.ruta_actual, self._texto())
        except ErrorFuente as e:
            self.voz.hablar(str(e))
            return

        self.modificado = False
        self._refrescar_estado()
        self.voz.hablar(f"Guardado como {self.ruta_actual.name}")

    def accion_guardar_como(self) -> None:
        """Diálogo de archivo. Pensado para quien ve: úsalo tú al configurar."""
        ruta = filedialog.asksaveasfilename(
            defaultextension=".txt",
            initialdir=str(cfg.carpeta_guiones(self.ajustes)),
            filetypes=[("Texto", "*.txt"), ("Todos", "*.*")],
        )
        if not ruta:
            self.decir("Guardado cancelado.")
            return
        self.ruta_actual = Path(ruta)
        self.accion_guardar()

    def abrir(self, ruta: str | Path) -> None:
        """Carga un archivo en el editor.

        Usa `leer_para_editor`, que conserva las sangrías tal cual. El otro
        lector, `leer_fichero`, normaliza el texto para decirlo en voz alta
        y destrozaría los márgenes de un guion importado.
        """
        ruta = Path(ruta)
        try:
            contenido = fuentes.leer_para_editor(ruta)
        except ErrorFuente as e:
            self.voz.hablar(str(e))
            return
        except (OSError, UnicodeDecodeError):
            self.voz.hablar(f"No he podido abrir {ruta.name}.")
            return
        self._reemplazar(contenido, 0)
        self.ruta_actual = ruta
        self.modificado = False
        self._refrescar_estado()
        self.voz.hablar(
            f"Abierto {ruta.name}. {documento.resumen_documento(contenido)}"
        )

    # ==================================================================
    # Arranque y cierre
    # ==================================================================
    def accion_salir(self) -> None:
        self.detener_bucle()
        if getattr(self, "servicio_dictado", None) is not None:
            try:
                self.servicio_dictado.cerrar()
            except Exception:
                pass
        if self.modificado:
            self.accion_guardar()
        self.voz.hablar("Cerrando VozClip. Hasta luego.")
        try:
            self.voz.esperar_silencio(limite=4.0)
        except Exception:
            pass
        try:
            self.raiz.destroy()
        except tk.TclError:
            pass

    def saludar(self) -> None:
        """El saludo dice la VERSIÓN. Es la única forma de saber, sin ver la
        pantalla, si un arreglo ha llegado a este ordenador o se sigue
        ejecutando una versión antigua."""
        extra = ""
        if self.servicio_dictado is not None:
            if not self.servicio_dictado.motivo_no_disponible():
                extra = " Efe uno para dictar por voz."
        self.voz.hablar(
            f"VozClip Escritor {version_hablada()} en marcha. "
            f"Plantilla {self.plantilla.nombre}.{extra} "
            "Control alt hache para escuchar los atajos."
        )

    def detener_bucle(self) -> None:
        """Corta el bucle de eventos antes de destruir la ventana.

        Hay que llamarlo SIEMPRE antes de `raiz.destroy()`. Lo usan tanto
        `accion_salir` como los tests.
        """
        self._cerrando = True
        tarea = getattr(self, "_tarea_cola", None)
        if tarea is not None:
            try:
                self.raiz.after_cancel(tarea)
            except tk.TclError:
                pass
            self._tarea_cola = None

        # Cancelar no basta: si el temporizador ya saltó, su callback está
        # esperando turno en la cola de eventos de Tcl y se ejecutará de
        # todos modos. Aquí se vacía esa cola con la bandera `_cerrando`
        # puesta, así que el callback entra, ve la bandera y sale sin
        # reprogramarse. Después ya se puede destruir la ventana sin que
        # Tcl encuentre un comando que ya no existe.
        try:
            self.raiz.update()
        except tk.TclError:
            pass

    def arrancar(self) -> None:
        self.raiz.mainloop()
