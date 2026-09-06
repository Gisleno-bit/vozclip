# Registro de cambios

## 2.13.0 — El segundo F1 que no paraba

### Lo que vio Julián

«El primer F1 sí funciona, los demás se quedan escuchando.» Y con F9
igual: decía la orden, el programa la mostraba, y se quedaba escuchando.

### Causa raíz

Una condición de carrera entre las DOS rutas de cada tecla. `detener()`
hacía `join()` en el hilo principal y congelaba la ventana mientras Vosk
finalizaba. Al volver, se procesaban en este orden: el evento «fin»
(`dictando = False`) y **después** la orden global que pynput había
encolado al pulsar. Con `dictando` ya en falso, esa orden **volvía a
arrancar la escucha**. El texto sí se insertaba, pero el `voz.parar()` del
nuevo arranque cortaba la confirmación, y solo se veía que seguía
escuchando. Con F9, la corrección se aplicaba y se reabría al instante.
Mi filtro «por foco» era una heurística que en Windows fallaba con esa
sincronía.

Además, mis tests usaban una captura que termina sola, así que el camino
«pulsar otra vez para parar» con un micrófono que sigue hasta que se lo
ordenan **nunca se había probado**.

### Corregido

- **Guard de repetición por tiempo.** Cada acción recuerda cuándo se
  ejecutó; una repetición en menos de 0,4 s se descarta venga por
  tkinter, por pynput o por el ratón. No depende del orden ni del foco.
  Nadie pulsa F1 dos veces a propósito en un tercio de segundo. Las
  órdenes directas (tests, humo) no pasan por él.
- **`detener()` ya no bloquea el hilo principal** desde la ventana
  (`esperar=0`): la interfaz responde al instante y la cola de órdenes no
  se retrasa.
- **F9 se aplica solo al callar.** Si el parcial reconocido lleva 1,5 s
  sin cambiar, la escucha termina y la orden se aplica: «veo que detecta
  el texto, que instantáneamente se cambie». Pulsar F9 otra vez sigue
  valiendo. Configurable en `correccion.parar_tras_silencio`; el dictado
  normal sigue manual, porque quien escribe hace pausas para pensar.
- **Un número dicho como palabra.** Julián dictó una fecha y quiso cambiar
  «veintiséis»; el intérprete lo leía como «la palabra número 26» y decía
  que no había tantas. Sin artículo, un número se busca primero como
  palabra literal; con artículo («la dos») es posición.
- La etiqueta dice CORRIGIENDO durante la orden, no ESCUCHANDO.
- Tests con un micrófono que bloquea como el real y las dos rutas de cada
  tecla activas, el filtro por foco anulado (el peor caso): F1 para al
  pulsar otra vez, se puede seguir dictando, F9 se aplica solo y también
  con la segunda pulsación, el guard, `detener` no bloquea.

## 2.12.0 — Corregir con F1, como lo hizo Julián

### La primera captura real

Julián dictó «come alpiste mientras está bailando con un cisne», oyó
«alpiste» mal, y volvió a pulsar **F1** para decir «alpiste por rueda». El
programa lo escribió como texto. Es lo natural: la misma tecla con la que
acaba de dictar. Exigirle F9 era un paso mío, no suyo.

### Añadido

- **Corrección durante el dictado.** Si lo dictado con F1 empieza por
  «cambia», «sustituye», «corrige», «borra» o «quita», y lo que se quiere
  cambiar está en el párrafo (o se da por número), se aplica como
  corrección y no se escribe. Con varias apariciones, pregunta cuál. Sin
  el verbo se escribe tal cual: «fue por pan» también parecería una orden
  si «fue» estuviera en el texto. La orden lleva ahora `con_verbo`.
- El recordatorio tras dictar enseña la frase, no la tecla: «Para corregir,
  di: cambia, la palabra, por, la buena».
- `Ctrl+Alt+Mayús+J` restaura el perfil de Julián. La captura mostraba tema
  oscuro, letra 16 y velocidad 0: su `config.json` es anterior al perfil, y
  el archivo solo se crea la primera vez.
- 17 tests, con el párrafo real de la captura.

## 2.11.2 — Los tests dejan de fallar en la CI

La release compiló y publicó bien; lo que estaba en rojo eran los tests, en
los cuatro entornos, por dos causas distintas.

### Corregido

- **Los `.bat` se subieron al repositorio con saltos de Linux.** Git Bash
  en Windows viene con `core.autocrlf=true` y al hacer commit convierte
  CRLF en LF. No era solo cosmético: `cmd` se pierde con los `goto` cuando
  un `.bat` tiene LF suelto, así que `INSTALAR.bat` podía fallar de formas
  raras. Se añade **`.gitattributes`** con `*.bat text eol=crlf`: Git
  guarda LF y devuelve CRLF al sacarlo, sin depender de cómo tenga cada uno
  configurado su Git. Comprobado con un repositorio de prueba y
  `core.autocrlf=true`.

- **En Windows, los tests que ejecutan `--autotest` no comprobaban Tcl/Tk.**
  El autotest abre una ventana, y el Python del tool cache de esos runners
  trae a veces un Tcl/Tk incompleto. La comprobación existía solo para
  Linux. Ahora `_hay_tkinter_usable()` lo verifica lanzando un `tkinter.Tk()`
  de verdad, en cualquier sistema, y los cuatro tests se saltan con su
  motivo en lugar de fallar.

## 2.11.1 — La CI deja de ponerse roja por los workflows

### Corregido

- **La CI fallaba tras borrar `build-windows.yml`.** El `ci.yml` antiguo
  seguía en el repositorio y ejecutaba el código nuevo, cuyos tests exigen
  `release.yml` y `tests.yml`, que aún no se habían subido. Cuatro trabajos
  en rojo por un problema que **no se puede arreglar desde la propia CI**.

  El fallo de diseño era mío: los workflows son infraestructura de
  ENTREGA, no código. Que falten o estén viejos no impide que el programa
  funcione. Ahora:

  * Los tests que los inspeccionan se SALTAN si el archivo no está, con un
    motivo que dice qué hacer. Si está pero le falta algo, siguen fallando:
    eso sí es una incoherencia real.
  * `verificar_repo.py` los trata como AVISO y devuelve 0. Los avisos se
    listan aparte, con instrucciones. Lo que sí devuelve error es que falte
    un módulo del programa.

  Resultado, con el repositorio tal como está: 608 tests verdes y 11
  saltados, en vez de cuatro trabajos rojos.

- **`verificar_repo.py` no detectaba que faltara `correccion.py`**: el
  módulo no estaba en su lista. Añadido, y ahora también avisa de módulos
  en disco que no estén declarados, para que no vuelva a pasar.

- `SUBIR_A_GITHUB.html` pone **borrar los workflows viejos antes** que
  crear los nuevos: mientras existan siguen ejecutándose y fallando.

## 2.11.0 — La versión se oye; F9 con flujo guiado; release automática

### Entrega

- **La release se crea sola en cada push a `main`.** `release.yml` lee la
  versión de `pyproject.toml` (`scripts/version.py`) y publica `v<versión>`
  con el ZIP, el instalador y los dos ejecutables. Nadie etiqueta nada. La
  descarga queda en una URL fija: `releases/latest/download/VozClip-Windows.zip`.
- **`SUBIR_A_GITHUB.html`**: un botón por workflow que abre GitHub con el
  archivo ya escrito, vía `/new/main?filename=…&value=…`. Solo hay que
  pulsar «Commit changes». Es la respuesta a que tres veces seguidas el
  workflow del repositorio se quedara viejo: los archivos que empiezan por
  punto no llegan con la subida a mano, y copiar YAML era el paso que se
  saltaba. Como GitHub solo prerrellena archivos NUEVOS, los workflows
  cambian de nombre: `release.yml` y `tests.yml`; la página enlaza también
  la papelera de los viejos.
- La falta de `modelos/` en `.gitignore` deja de romper la CI: es un aviso
  del verificador, no un test.

### Por qué esta versión

Se reportaron como vigentes dos fallos corregidos en la 2.8.0 (la raya
doble con F3) y la 2.10.0 (F9). La causa no estaba en el código: **no
había forma de saber, de oído, qué versión se ejecutaba**. Un arreglo que
no llega al ordenador es indistinguible de uno que no funciona.

### Añadido

- **La versión se dice en voz alta** en el saludo («VozClip Escritor dos
  punto diez en marcha») y en «dónde estoy» (`Ctrl+Alt+W`). Va en el título
  de la ventana, en `--version`, y en las cabeceras del diagnóstico y del
  autotest. El diagnóstico también la dice por voz.
- **F9 en modo numerado** (`correccion.modo: "numerado"`): F9 lee el
  párrafo con cada palabra numerada, pregunta cuál, lee la elegida para
  confirmar, pide la nueva, sustituye solo ese tramo y confirma. Tres
  escuchas, pero nunca hay que pronunciar la palabra mal reconocida.
  Acepta rangos («del tres al cinco»), «borrar» para quitar la elegida, y
  también la orden entera de una vez («la dos por tarde»).
- Desde el modo directo, «léelo» entra en el mismo flujo guiado.
- La máquina de estados de la corrección tiene fases explícitas (orden,
  elegir número, dictar nueva, elegir aparición).
- Tests: el flujo numerado completo, con rango, con borrar, insistiendo si
  no oye un número; F9 por el atajo global sin foco; F9 no se dispara dos
  veces con foco (el mismo doble disparo de F3); la versión en el saludo,
  en dónde estoy y en el título.

### Corregido

- «no sé» cancelaba la corrección, porque empezaba por «no». Ahora «no»
  solo cancela si es todo lo dicho.
- «borrar» a secas no se reconocía como orden en el flujo guiado.
- Un test del F9 global era intermitente por la sincronía del foco en
  Xvfb; ahora fija el foco a mano, porque prueba el enrutado, no Xvfb.

## 2.10.1 — La versión se oye; F9 guiado como opción

### Diagnóstico

Se reportaron como vigentes el guion doble de F3 (corregido en la 2.8.0)
y un F9 que "no hace nada" (implementado en la 2.10.0). Las dos cosas
están corregidas y cubiertas por tests desde entonces; los síntomas
corresponden a una versión anterior en el ordenador de uso. El problema
real: no había forma de saber, sin ver la pantalla, qué versión se
estaba ejecutando.

### Añadido

- **La versión se dice en voz alta**: en el saludo («VozClip Escritor dos
  punto diez en marcha»), en «dónde estoy» (Ctrl+Alt+W) y al final del
  diagnóstico. Va también en el título de la ventana y en `--version`.
- **`correccion.modo = "numerado"`**: F9 lee el párrafo numerado, pregunta
  cuál, lee la palabra elegida para confirmar y pide la nueva. El flujo de
  cuatro pasos tal como se pidió, como alternativa al directo (que sigue
  siendo el predeterminado). Desde el directo, «léelo» entra en el mismo
  flujo guiado. Admite rangos («del tres al cuatro») y «borrar».
- La corrección se reescribió como máquina de fases explícitas (orden,
  elegir número, dictar la nueva, elegir aparición): el mismo código
  sirve a los dos modos.
- Tests: F9 por el atajo global con la ventana sin foco, F9 sin doble
  disparo con foco, el flujo numerado completo (número, rango, borrar,
  sin número, orden entera de una vez), y la versión en saludo, título y
  «dónde estoy». 14 nuevos.

### Corregido

- «no sé» cancelaba la corrección porque empieza por «no». Ahora «no» solo
  cancela si es todo lo dicho.
- «borrar» a secas no se reconocía como orden en el flujo guiado.

## 2.10.0 — Corregir una palabra por voz (F9)

### Añadido

- **Corrección por voz.** F9, «cambia casa por cosa», F9. Se localiza la
  palabra en el párrafo del cursor (sin distinguir mayúsculas ni acentos:
  el reconocedor no siempre los pone), se sustituye solo ese tramo y se
  confirma. Sangrías, puntuación pegada y mayúscula inicial se conservan.
  Frases enteras, «borra X», «cancela», «deshacer». Si aparece varias
  veces, pregunta cuál y espera el número.
- **Numeración como apoyo, no como camino.** «Léelo» enumera el párrafo
  («1, aquella. 2, noche…») y se corrige por número o por rango («de la
  tres a la cinco por…»). Un rango es UN tramo, no palabras sueltas.
  Se eligió esto frente a numerar siempre: leer treinta palabras con su
  número tarda el doble, y preguntar tras cada dictado añade un turno las
  veinte veces que no hay nada que cambiar.
- Números en castellano hasta noventa y nueve («treinta y dos»), y en
  cifra.
- Botón «Corregir palabra» (F9), sexto de la fila de comandos, con color
  propio. Escape cancela. Modo externo: sobre la línea del cursor en Word.
- Tras dictar cuatro o más palabras, se recuerda «efe nueve para corregir»
  (desactivable en `correccion.recordatorio`).
- 74 tests de la lógica pura y 18 de integración con dictado simulado,
  incluidos los flujos de varias apariciones, «léelo», cancelar, deshacer
  y modo externo.

### Corregido

- **Escape podía dejar que un texto tardío se insertara como dictado.** La
  cancelación miraba `self.dictando`, que solo se activa al procesar el
  evento «inicio»; si Escape llegaba antes, el texto en camino se colaba.
  Ahora se mira el estado real del servicio y se descarta lo que venga.
- **Un solo Ctrl+Z dejaba el editor vacío.** Con `autoseparators`, Tk
  separaba el delete y el insert de cada reemplazo en dos unidades de
  deshacer. Se desactiva durante el reemplazo.
- Tras corregir, el cursor queda al final del párrafo, para seguir
  dictando desde ahí y no en mitad de la frase.

## 2.9.1 — INSTALAR.bat

### Añadido

- **`INSTALAR.bat`** en la raíz: un doble clic desde el código fuente.
  Busca Python (lo instala con winget si falta), crea `.venv`, instala las
  librerías, descarga el modelo de voz a una carpeta sin acentos y deja un
  acceso directo "VozClip" en el escritorio. Lo dice todo en voz alta y
  pita al terminar. Es idempotente: si falla a medias, se vuelve a pulsar
  y lo hecho no se repite. No duplica lógica: llama a
  `scripts/descargar_modelo.py`, que ya tiene sus tests.
- **`Iniciar VozClip.bat`**: abre el programa con `pythonw`, sin consola.
- 9 tests sobre los dos `.bat` y su presencia en el verificador.

## 2.9.0 — Whisper con GPU y servidor local; captura que distingue el silencio

### Añadido

- **`scripts/servidor_whisper.py`**: servidor local con la biblioteca
  estándar (`http.server`), sin flask ni websockets. Carga el modelo UNA
  vez y se queda caliente. Es lo que permite `large-v3` con GPU sin que
  VozClip lo note: los 3 GB y el medio minuto de carga pasan en otro
  proceso, y VozClip puede seguir siendo el `.exe` estándar. Solo escucha
  en 127.0.0.1. `iniciar_servidor_whisper.bat` instala lo que falte y lo
  arranca.
- **`MotorWhisperRemoto`**: tercer motor, `"motor": "whisper-servidor"`.
  Manda el WAV por HTTP y recibe el texto. Si el servidor no responde, lo
  dice en voz alta y sigue con Vosk. Distingue "servidor caído" de "el
  modelo ha fallado".
- **GPU automática.** `hay_gpu_cuda()` pregunta a CTranslate2. Con `"auto"`
  se elige `large-v3` en `float16` si hay CUDA y `small` en `int8` si no.
  `large-v3` en CPU tarda medio minuto por cada 10 s de audio: se avisa.
- **La captura mide el nivel.** `nivel_rms` sin numpy. Si lo grabado es
  silencio, el error dice "el micrófono está silenciado o en otro
  dispositivo" en vez de "no he entendido nada": son dos problemas con dos
  soluciones. Los bloques desbordados ya no se tiran (recortaban palabras
  sin avisar); se entregan y se cuentan, y se avisa si hubo pérdidas.
- `requirements-whisper.txt` aparte, con las notas de CUDA.
- 21 tests: el servidor levantado de verdad con un transcriptor simulado
  (salud, ciclo completo por HTTP, rechazo de lo que no es WAV, error del
  modelo), la GPU automática, el fallback, el nivel de señal y los bloques
  perdidos. Y un test más del doble disparo, con tecla y ratón juntos.

### Verificado con la librería real

`faster-whisper` 1.2.1 se instala, el motor se construye y el servidor
arranca: se detiene exactamente al descargar el modelo, porque Hugging Face
está bloqueado en el entorno de desarrollo. Todo lo anterior a ese punto
está probado; la transcripción real la verá el usuario en local.

## 2.8.0 — La raya doble y Whisper opcional

### Corregido

- **F3 insertaba la raya dos veces con la ventana enfocada.** Cada tecla
  tenía dos rutas: el `bind_all` de tkinter (solo con el foco) y el atajo
  global de pynput (siempre). Una pulsación llegaba por las dos. Peor: F1
  arrancaba el dictado y lo paraba 50 ms después, que explica dictados que
  "no arrancaban". Ahora las órdenes globales se marcan y se descartan si
  la ventana tiene el foco, porque ya las ha atendido tkinter. Sin foco
  siguen funcionando. 6 tests de regresión, incluido el de F1.

### Añadido

- **Motor faster-whisper, opcional.** Mucho más preciso que el Vosk
  pequeño; no es streaming, transcribe al pulsar F1. Se activa con
  `pip install faster-whisper` y `"motor": "whisper"` en el config.json.
  Si la librería no está, se avisa por voz y se sigue con Vosk. No va en
  el `.exe` estándar (81 MB de librerías más el modelo); `build_exe.py` lo
  excluye aunque esté instalado. 20 tests con la librería simulada, y
  comprobación de que la real se integra.
- El evento "aviso" del dictado: se dice una vez y el dictado sigue.

## 2.7.0 — El YAML deja de cambiar

### El problema de fondo

Por tercera vez, la CI fallaba porque el `build-windows.yml` del repositorio
era de una versión anterior. `.github/` es una carpeta oculta y las subidas
a mano a GitHub se la saltan; el YAML tenía nueve bloques de PowerShell y
cambiaba en cada versión. Dar el archivo corregido no bastaba: al siguiente
cambio, volvía a quedarse atrás.

### Cambiado

- **Toda la lógica sale del YAML a scripts de Python.** El workflow pasa
  de 255 líneas y nueve bloques de PowerShell a 99 líneas y dos (el plan B
  de Tcl/Tk y el instalador de Inno Setup, que no se pueden hacer desde
  Python). Cada paso es una línea: `python scripts/X.py`.
- **`scripts/verificar_binario.py`**: ejecuta el `.exe` con `--autotest`,
  lee las marcas ASCII con `errors="replace"` (da igual la página de
  códigos), comprueba las diez obligatorias y lee la cabecera PE para
  confirmar que el principal es de tipo ventana. Añadir una marca es tocar
  una lista en Python; el YAML no cambia.
- **`scripts/empaquetar.py`**: arma el ZIP de entrega, con el modelo si
  está, y se niega a crear un paquete a medias.
- **Los tests dejan de mirar dentro del YAML.** Antes había diez tests que
  buscaban cadenas en el workflow; ahora hay UNO, que comprueba que el YAML
  llama a los scripts, y el resto prueban los scripts directamente: las
  marcas, la cabecera PE, el empaquetado con y sin modelo.
- `verificar_repo.py` y `_exigir_en_workflow` dicen por su nombre qué
  archivo está viejo y qué le falta.

### Resultado

Si el YAML del repositorio vuelve a quedarse atrás, la CI falla en dos
segundos con: "A .github/workflows/build-windows.yml le faltan N cosa(s):
... Suele significar que el workflow del repositorio es más antiguo que el
código". Y como el YAML ya casi nunca cambia, debería quedarse atrás mucho
menos.

## 2.6.2 — "Failed to create a model" con el modelo bien instalado

### Causa raíz

El modelo estaba. El problema era la RUTA. `vosk` hace
`model_path.encode("utf-8")` y se lo pasa a la librería en C, que en
Windows abre archivos con la página de códigos ANSI. Los bytes de "Julián"
en UTF-8 (`Juli\xc3\xa1n`) los lee como "JuliÃ¡n": una carpeta que no
existe. Devuelve NULL, y el binding lanza "Failed to create a model".

Cualquier ruta con tilde o eñe lo provoca: `C:\Users\Julián\AppData\...`,
`C:\Users\Julián\Descargas\VozClip\modelos\...`. Todas las que tenía.

### Corregido

- **`ruta_segura_para_vosk`**: antes de cargar, si la ruta tiene acentos,
  usa el nombre corto 8.3 de Windows (`C:\Users\JULIN~1\...`, ASCII y
  apunta al mismo sitio, sin copiar nada); y si los nombres cortos están
  desactivados, copia el modelo una sola vez a una carpeta ASCII y usa la
  copia. Transparente para el usuario.
- **La carpeta de modelos en Windows pasa a `C:\Users\Public\VozClip\modelos`**,
  que es ASCII por construcción y siempre escribible. El perfil del usuario
  se sigue mirando por compatibilidad, pero ya no se instala ahí.
- **`instalar_modelos.bat` instala en Public.** Si `%PUBLIC%` no existiera,
  en `C:\VozClip\modelos`. Nunca en el perfil.
- **El error se traduce.** En vez de "Failed to create a model": "El modelo
  está en una carpeta con tildes o eñes en el nombre, y la librería de
  reconocimiento no puede abrirla. Ejecuta instalar modelos punto bat".
- El diagnóstico avisa si la ruta del modelo lleva acentos y dice qué
  remedio ha aplicado.
- 11 tests que reproducen el caso con una carpeta "Julián": la copia a un
  sitio ASCII, su reutilización, el nombre corto, la carpeta Public y la
  traducción del error.

## 2.6.1 — F3 sin personaje, en ninguna plantilla

### Corregido

- **F3 seguía metiendo "PERSONAJE".** La causa no estaba en el formato de
  diálogo, que ya era correcto, sino en el `config.json`: se crea una sola
  vez, y uno antiguo guardaba `plantilla: "teatro"`. Teatro y cine eran las
  únicas plantillas con `pide_personaje`, así que F3 insertaba el nombre
  por muchas veces que se arreglara el resto.

  **Se han retirado las plantillas de teatro y cine.** Con eso, un ajuste
  antiguo que diga "teatro" se resuelve solo a novela al arrancar, sin que
  el usuario tenga que tocar nada. Quedan tres: novela, diálogo narrativo
  y escaleta.

- **F3 inserta ahora exactamente lo mismo en todas las plantillas**: dos
  espacios de sangría (los 0,63 cm), la raya U+2014 pegada, y el cursor
  detrás. Se ha eliminado el parámetro `personaje` de `nuevo_dialogo` y el
  código que lo construía. Hay un test que recorre las tres plantillas y
  comprueba que ninguna produce otra cosa.

- El `.bat` de instalación, cuando la descarga falla, escribe en pantalla y
  dice en voz alta la dirección para bajar el modelo a mano, con la ruta
  exacta donde dejarlo.

### Añadido

- El LEEME explica cómo instalar el modelo a mano, con la estructura de
  carpetas que hay que dejar y cómo comprobarlo con el diagnóstico.

## 2.6.0 — El modelo de dictado viene incluido

### Corregido

- **F1 decía "falta el modelo de voz" aunque el modelo estuviera al lado
  del programa.** `localizar_modelo` solo miraba en la carpeta de datos del
  usuario (`%APPDATA%\VozClip\modelos`), así que un modelo que viajara
  junto al ejecutable se ignoraba. Ahora busca por orden en: la ruta del
  `config.json`, la carpeta `modelos` junto al programa, y la del usuario.
  En un `.exe` de PyInstaller mira junto a `sys.executable`, no junto a
  `sys._MEIPASS`, que es la carpeta temporal que desaparece al cerrar.
- **La ruta configurada a mano dejó de tenerse en cuenta** al añadir la
  búsqueda múltiple. Corregido, con test de regresión.
- **Un servicio de dictado con motor propio ya no exige el modelo de Vosk.**
  Si alguien trae su propio reconocedor, el modelo lo pone él; comprobarlo
  igualmente bloqueaba un servicio que funcionaba.
- El mensaje de "falta el modelo" ahora dice QUÉ hacer ("haz doble clic en
  instalar modelos punto bat") en vez de nombrar una opción de menú.

### Añadido

- **`scripts/descargar_modelo.py`**: descarga, descomprime y verifica el
  modelo. Lo usa la compilación para meterlo en el paquete, y también se
  puede ejecutar a mano (`--destino`, `--usuario`).
- **La compilación incluye el modelo en el ZIP y en el instalador.** Son
  46 MB más, pero es la diferencia entre "descomprime y dicta" y
  "descomprime, busca un .bat, ejecútalo, espera y entonces dicta". Para
  quien no ve la pantalla, cada paso extra es un sitio donde atascarse.
- Si el sitio del modelo estuviera caído, la compilación **publica el
  paquete igual**, sin modelo y con un aviso: el `.bat` sigue incluido.
  Mejor un paquete sin modelo que ningún paquete.
- El diagnóstico enumera todas las carpetas donde ha buscado y si existen.
- 18 tests nuevos: el modelo incluido, la prioridad entre carpetas, el
  script de descarga de principio a fin (con un zip servido desde disco,
  sin internet) y su presencia en el paquete y el instalador.

### Cambiado

- `modelos/` va en el `.gitignore`: son 46 MB que descarga la compilación,
  no viven en el repositorio.
- El acceso directo del escritorio para instalar el modelo desaparece: ya
  no hace falta. El del menú Inicio queda como "Reinstalar el dictado".

## 2.5.1 — Detectar archivos desactualizados en el repositorio

### Corregido

- **La CI fallaba con tres AssertionError opacos.** No era un fallo del
  código: el `build-windows.yml` del repositorio era de una versión
  anterior, porque al subir los archivos a mano se quedó atrás. Los tests
  detectaban bien la incoherencia, pero el mensaje era
  `assert 'OutputEncoding' in 'name: Compilar Windows\n\n# Genera...'`
  seguido del YAML entero, que no dice qué hacer.

  Ahora esas comprobaciones pasan por `_exigir_en_workflow`, que enumera
  exactamente lo que falta y explica la causa más probable:

      A .github/workflows/build-windows.yml le faltan 6 cosa(s):
      'OutputEncoding', 'VOZCLIP_ODT=OK', 'instalar_modelos.bat'...
      Suele significar que el workflow del repositorio es más antiguo
      que el código.

### Añadido

- **`scripts/verificar_repo.py`**: comprueba en un segundo que están todos
  los módulos, que los archivos de configuración contienen lo que el
  código da por hecho, y que el `.bat` y `modelo.py` apuntan al mismo
  modelo. Dice qué archivo hay que volver a subir, por su nombre.
- Los dos workflows lo ejecutan **antes que nada**: si algo se ha quedado
  atrás, la CI falla en dos segundos con un mensaje claro en vez de a los
  treinta con un volcado de YAML.
- 3 tests: que el verificador aprueba este proyecto, que detecta de verdad
  un archivo recortado, y que los workflows lo ejecutan.

## 2.5.0 — LibreOffice, la plantilla de diálogo y el instalador del modelo

### Añadido

- **Exportación a LibreOffice** (`Ctrl+Alt+Mayús+L`, botón violeta, Alt+0).
  Genera un `.odt`, el formato propio de LibreOffice Writer: no hay
  conversión por medio y las medidas del documento de estilo llegan
  exactas. Está escrito con la biblioteca estándar (`zipfile` y cadenas de
  XML), sin añadir ninguna dependencia: un .odt es un zip con cuatro
  archivos. Se comprueba con LibreOffice REAL en los tests, convirtiendo el
  archivo a PDF: si estuviera mal formado, la conversión fallaría.
- **`instalar_modelos.bat`**: doble clic y descarga e instala el modelo de
  voz en español. **Habla cada paso con la voz de Windows** ("descargando",
  "descarga terminada", "modelo instalado") y termina con dos notas
  ascendentes si fue bien o una grave si falló, con el motivo en voz alta.
  Rechaza descargas de menos de un mega (una página de error, no el
  modelo), verifica `am\final.mdl` igual que hace VozClip, y no pide nada
  al usuario. Va en el ZIP, en el instalador, en el menú Inicio y como
  acceso directo en el escritorio.
- Un `.txt`, un `.docx` y un `.odt` pueden convivir con el mismo nombre
  base: guardar, exportar a Word y exportar a LibreOffice.
- 35 tests nuevos: el .odt pieza a pieza (mimetype primero y sin
  comprimir, manifest, estilos, medidas, escapado de XML), la apertura real
  con LibreOffice, la estructura del .bat, y que el .bat descarga el mismo
  modelo y lo deja donde el programa lo busca.

### Corregido

- **La plantilla 3 (diálogo narrativo) y F3.** Antes insertaba raya,
  espacio, hueco, "dijo", hueco y punto. Ahora inserta EXACTAMENTE lo que
  Julián pide: dos caracteres de sangría (0,63 cm), la raya pegada a ellos
  y el cursor justo detrás. Sin espacio tras la raya, sin nombre de
  personaje, sin nada más. En castellano la raya de diálogo va pegada a la
  primera palabra: "—No me lo creo".
- "Nuevo diálogo" (F3) en modo externo también teclea sangría y raya sin
  espacio. "Nuevo párrafo" (F2) no arrastra nada del diálogo.

### Cambiado

- Diez botones en dos filas de cinco: los cinco comandos en azul, guardar
  en verde, importar, exportar y Word en naranja, LibreOffice en violeta.
- Los `.bat` van en ASCII puro y con saltos CRLF: la consola de Windows
  destroza los acentos, y con LF suelto cmd se pierde con los `goto`.
- 36 atajos, sin choques y todos aceptados por pynput.

## 2.4.0 — El formato de Julián

### Añadido

- **La plantilla "novela con diálogos", que es su formato de verdad.** Sale
  de su documento de estilo: diálogos con sangría izquierda 0,63 cm y
  sangría francesa 0,63, espacio posterior 18 pt e interlineado mínimo;
  narrador con primera línea 1,25 cm, posterior 18 pt y justificado. Es la
  plantilla que viene puesta de salida.

- **Exportación a Word (`Ctrl+Alt+Mayús+E`) con las medidas exactas.** Esto
  hacía falta: el texto plano no tiene centímetros, ni puntos de espaciado,
  ni justificación. En el editor las sangrías se aproximan con espacios,
  que sirve para escribir y orientarse de oído; el formato de verdad existe
  en el .docx. Cada párrafo se clasifica solo: si empieza por raya recibe el
  formato de diálogo, si no el de narrador. No añade ninguna dependencia,
  porque python-docx ya estaba para leer Word.

- **Perfil "Julián", cargado en el primer arranque.** Alto contraste, letra
  de 20 puntos, velocidad 2 y su plantilla. Solo guarda lo que se aparta de
  los valores por defecto, así que hereda automáticamente cualquier opción
  que se añada más adelante. La acción "perfil Julián" lo restaura: es la
  salida de emergencia cuando algo se descoloca y no se puede ver la
  pantalla para arreglarlo.

- **Configuración importable y exportable** (`Ctrl+Alt+U` y `Ctrl+Alt+Y`),
  con validación antes de aplicar: un perfil con valores imposibles se
  rechaza en vez de dejar el programa en un estado del que no se pueda
  salir a ciegas.

- **Los cinco comandos de todos los días, en F1 a F5.** Grabar, nuevo
  párrafo, nuevo diálogo, leer el último párrafo y leer el texto entero.
  Una sola tecla, sin modificadores, con una mano.

- **Botonera agrupada por color**: los cinco comandos en azul con borde
  blanco, guardar en verde, y en naranja lo que entra y sale. Con baja
  visión, localizar un bloque de color cuesta mucho menos que leer nueve
  rótulos iguales; y separar guardar de exportar evita el error caro.

- "Nuevo diálogo" se adapta a la plantilla: raya en novela y narrativo,
  nombre del personaje con su margen en teatro y cine.

- 92 tests nuevos: las medidas del .docx una por una, los perfiles, la
  validación, y los comandos en el HUD.

### Corregido

- `_linea_de_personaje` borraba el margen con un `rstrip()`, así que en cine
  el nombre acababa pegado al borde izquierdo en vez de a 20 espacios.
- El nombre de un perfil se perdía al aplicarlo, porque `aplicar` descarta
  los metadatos. Ahora se lee aparte con `nombre_de`.

### Cambiado

- **Atajos reorganizados** para hacer sitio: quitar sangría pasa de
  `Ctrl+Alt+U` a `Ctrl+Alt+Mayús+I` (emparejado con aplicar sangría en
  `Ctrl+Alt+I`), y `Ctrl+Alt+U` queda para importar configuración.
- La plantilla por defecto pasa de teatro a novela.
- 35 atajos en total, sin choques y todos aceptados por pynput.

## 2.3.1 — La CI ya no falla con el autotest en verde

### Corregido

- **El paso "Verificar el ejecutable" fallaba aunque el autotest pasara.**
  El ejecutable escribe UTF-8; la consola de Windows lo leía como cp1252,
  así que "vosk y sounddevice están empaquetados" llegaba a PowerShell como
  "vosk y sounddevice estÃ¡n empaquetados". El `-notmatch` buscaba el texto
  con acento, no lo encontraba, y abortaba con `exit code 1` justo después
  de imprimir "AUTOTEST CORRECTO".

  Se arregla en dos capas, porque una sola no basta:
  1. **Marcas en ASCII puro.** El autotest imprime al final un bloque
     `VOZCLIP_TKINTER=OK`, `VOZCLIP_DICTADO_EMPAQUETADO=OK`,
     `VOZCLIP_RESULTADO=OK`... Sin un solo carácter fuera de ASCII, así que
     se leen igual con cualquier página de códigos. La CI comprueba esas
     marcas y el código de salida, nunca texto acentuado.
  2. **UTF-8 de verdad en la consola.** `_forzar_utf8()` llama a
     `SetConsoleOutputCP(65001)` y reconfigura los flujos, para que además
     el log de la CI se lea bien.

- **`$ErrorActionPreference` de pwsh.** GitHub arranca PowerShell con
  `'stop'`: el `2>&1` de un ejecutable nativo podía abortar el paso antes
  de llegar a mirar el código de salida. Ahora se pone en `'Continue'` y se
  evalúa el resultado explícitamente.

- Las dos ejecuciones del `.exe` en el workflow se fusionan en una sola.

- **`Fatal Python error: Aborted` en la batería completa.** Salió al
  validar lo anterior. La recolección de basura se disparaba dentro de un
  hilo de voz y finalizaba objetos de tkinter de ventanas ya destruidas;
  tocar Tcl desde fuera del hilo principal hace que Tcl llame a `abort()`
  y se lleve el proceso entero, sin señalar a ningún test. Tres arreglos:
  `detener_bucle()` cancela el `after` y además vacía la cola de eventos
  de Tcl (cancelar no basta si el temporizador ya saltó), `_atender_cola`
  comprueba que la ventana siga existiendo, y las fixtures recogen la
  basura en el hilo principal.

- **El bucle de eventos había perdido su identificador.** `_tarea_cola` no
  guardaba el `after` inicial, así que `detener_bucle` no podía cancelarlo.
  Peor: ningún test lo habría notado, porque todos llamaban a
  `_atender_cola()` a mano. En la aplicación real eso deja los atajos
  globales y el dictado sin procesar. Hay un test nuevo que encola una
  orden y espera a que el bucle la ejecute por su cuenta.

### Añadido

- 13 tests nuevos: que las marcas existan, que sean ASCII, que sobrevivan
  a cp1252, cp437 y latin-1, que las marcas que el workflow exige sean
  exactamente las que el autotest emite, y las regresiones del aborto y
  del bucle de eventos.

## 2.3.0 — Portabilidad, importación y accesibilidad

### Corregido

- **La CI de Windows fallaba con `Windows fatal exception: code 0x80000003`.**
  Era un bug real: `_bucle` llamaba a `CoInitialize()` en Windows siempre,
  incluso con el motor falso, que no toca COM. Con casi trescientos tests
  creando servicios, eso era inicializar y desinicializar apartamentos COM
  en cientos de hilos efímeros. Y había una fuga: cuando la creación del
  motor fallaba, el `return` se saltaba el `CoUninitialize()`. Ahora una
  función `eleccion_motor()` decide qué motor se usará ANTES de tocar COM,
  y solo SAPI5 lo inicializa; todo lo demás va en un `try/finally`.
- **Los tests del HUD fallaban de forma intermitente en Windows.** El
  guardián se evaluaba una sola vez al importar el módulo, y en los runners
  el Tcl/Tk del tool cache falla a ratos (`ttk/notebook.tcl` no encontrado).
  Ahora cada fixture intenta crear la ventana en ese momento y salta si no
  puede.
- **Con letra grande los rótulos se recortaban** (`6. Importa`), la botonera
  empujaba al editor fuera de la pantalla, y `winfo_width()` devolvía 1
  durante la construcción, así que el ajuste de línea salía siempre a 140
  píxeles. Se vio mirando las capturas, no en los tests.
- `pytest.importorskip` ya no salta ante un `ImportError` genérico desde
  pytest 8; el test de pynput lo captura a mano.
- El bucle `after` de tkinter se cancela al cerrar, sin tareas huérfanas.
- Cambiar el tamaño de letra no refrescaba la franja de estado.

### Añadido

- **Portabilidad entre editores.** Espera adaptativa por aplicación (Bloc de
  notas 0,12 s; Word 0,45; navegador 0,50), que sube deprisa al fallar y
  baja despacio al acertar. Detección de la aplicación activa con ctypes,
  sin psutil. Portapapeles prestado que se restaura siempre, incluso ante
  excepción. Reintentos con marca centinela. Tabla `COMPATIBILIDAD` que
  documenta también lo que NO funciona.
- **Importar y exportar.** `Ctrl+Alt+O` abre .txt, .md, .rtf y .docx
  conservando las sangrías intactas; `Ctrl+Alt+E` exporta al portapapeles o
  a la aplicación activa; `Ctrl+Alt+S` guardar como. Lector de RTF propio,
  sin añadir dependencias, y traducción de la sangría de párrafo de Word a
  espacios. Guardado atómico.
- **Tres temas** (`Ctrl+Alt+C`): oscuro, alto contraste (negro y amarillo
  puros, 21:1) y claro.
- **Tamaño de letra ajustable** de 10 a 42 puntos (`Ctrl+Alt++` y `-`), con
  la botonera repartiéndose en dos filas cuando hace falta.
- **Modo solo voz** (`Ctrl+Alt+Z`): la ventana se reduce al mínimo y todo
  sigue funcionando por teclado y por voz.
- **Navegación por teclado**: `F6` salta entre zonas, `Alt+1`…`Alt+8` pulsa
  cada botón, y los botones se presentan solos al recibir el foco.
- El título de la ventana refleja el estado, que es lo único que un lector
  de pantalla externo lee bien de tkinter.
- 88 tests nuevos: puente, importación y exportación, accesibilidad y las
  regresiones de todo lo corregido.

### Cambiado

- **Atajos reorganizados** para evitar choques con las funciones nuevas:
  quitar sangría pasa de `Ctrl+Alt+O` a `Ctrl+Alt+U`, y leer selección de
  `Ctrl+Alt+S` a `Ctrl+Alt+K`. Las cuatro lecturas quedan juntas en el
  teclado: J línea, K selección, L portapapeles, A todo.
- Los rótulos de la interfaz se topan en 22 puntos aunque el texto llegue a
  42: sin ese tope, los botones acababan tapando el editor.
- El cursor ya no parpadea; `ttk.Scrollbar` se sustituye por `tk.Scrollbar`,
  que sí se puede colorear en modo alto contraste.
- Sin dependencias nuevas: el ejecutable no crece.

## 2.2.0 — Dictado por voz

### Añadido

- **Dictado con F1.** Pulsar F1, hablar y volver a pulsar F1: el texto
  aparece en el editor, en la posición del cursor. Motor Vosk, offline.
- **Puntuación hablada.** "coma", "punto", "punto y aparte", "raya",
  "abrir interrogación", "dos puntos", "nueva línea" y una docena más.
  Respeta las reglas del castellano: mayúscula después de la raya de
  diálogo y del signo de apertura de interrogación.
- **El dictado respeta las plantillas.** Un "punto y aparte" dentro de un
  bloque de diálogo de cine deja la línea nueva con la misma sangría, para
  que el guion no se descuadre.
- **Indicador de dictado en el HUD**, en rojo y grande, con el texto parcial
  reconocido. Pitido al empezar y al terminar, más aviso hablado.
- **Séptimo botón** "Dictar F1", el primero de la fila.
- **`--instalar-modelo-dictado`**: descarga el modelo de español (39 MB) una
  sola vez, cantando el porcentaje en voz alta.
- Entrada en el menú Inicio del instalador para descargar el modelo.
- El diagnóstico comprueba vosk, sounddevice, el modelo y los micrófonos.
- 71 tests nuevos: puntuación hablada, servicio de dictado, captura de
  audio, integración con el HUD y empaquetado de las librerías nativas.

### Decisiones técnicas

- **Vosk y no Whisper.** Whisper arrastra PyTorch (cientos de MB) y tarda
  segundos por frase en CPU; para dictar mientras se escribe, esa latencia
  lo hace inservible. Vosk reconoce en tiempo real con un núcleo.
- **Vosk y no Google Web Speech.** Depender de internet para poder escribir
  es inaceptable en una herramienta de accesibilidad.
- **`RawInputStream` y no `InputStream`** de sounddevice: entrega bytes
  crudos en vez de arrays, así el programa no depende de numpy y el
  ejecutable no engorda 30 MB.
- **Se espera a que la voz calle antes de abrir el micrófono.** Si no, el
  programa graba su propio "Escuchando" y lo transcribe al guion.
- **Los parciales se ven pero no se hablan**, para no interrumpir al usuario
  justo mientras dicta.
- **`--collect-all vosk`** en PyInstaller: vosk no tiene hook, así que
  `libvosk.dll` (25 MB) se quedaría fuera y el dictado fallaría en un .exe
  que habría compilado sin quejarse.

### Cambiado

- El ejecutable pasa de 26 a 36 MB por libvosk y PortAudio.
- La CI de Linux instala `libportaudio2`.
- El workflow de Windows verifica que vosk y sounddevice viajan dentro
  del `.exe`, ejecutándolo.

## 2.1.0 — Entrega: ejecutable, instalador y CI verde

### Corregido

- **PyInstaller no soportaba el punto de entrada.** El script apuntaba a
  `src/vozclip/__main__.py`, que usa `from .cli import main`. PyInstaller
  ejecuta el script de entrada sin contexto de paquete, así que lanzaba
  `ImportError: attempted relative import with no known parent package`.
  Compilado con `--windowed`, ese error no se ve: doble clic y nada.
  Detectado al compilar un binario de prueba y ejecutarlo. Se añade
  `scripts/lanzador.py`, con import absoluto, y un test que lo vigila.
- **La CI fallaba en Windows.** El guardián de los tests del HUD daba por
  hecho que en Windows siempre se puede abrir una ventana. En los runners
  de GitHub, el Python del tool cache trae a veces un Tcl/Tk incompleto
  (`Can't find a usable init.tcl`). Ahora el guardián intenta crear una
  ventana de verdad antes de decidir, así que esos tests se saltan con su
  motivo en vez de romper la CI.

### Añadido

- **`--autotest`**: verifica un binario de principio a fin (tkinter, hilo de
  voz, construcción del HUD, acciones, atajos y guardado) usando el motor
  falso, así que no necesita audio. Es lo que valida el `.exe` en la CI.
- **`.github/workflows/build-windows.yml`**: compila, verifica y empaqueta.
  Comprueba Tcl/Tk antes de compilar y, si está roto, instala el Python
  oficial en su lugar. Después ejecuta el `.exe` con `--autotest` y lee la
  cabecera PE para confirmar que el subsistema es 2 (ventana) y no 3
  (consola).
- **Instalador con Inno Setup** (`installer/VozClip.iss`): acceso directo en
  el escritorio, entrada en el menú Inicio, arranque con Windows opcional y
  `PrivilegesRequired=lowest` para no disparar el aviso de UAC.
- **`LEEME.txt`** para el usuario final y ZIP de entrega con ambos
  ejecutables, la guía rápida y el `.bat` de arranque automático.
- Redirección de `sys.stdout` y `sys.stderr` al archivo de registro cuando
  se ejecuta sin consola, y manejador global de excepciones que anota el
  error, lo dice en voz alta y muestra un aviso.
- 17 tests nuevos de empaquetado: vigilan el import absoluto del lanzador,
  los hidden imports, el modo sin consola y el contenido del instalador.

### Cambiado

- `build_exe.py` excluye numpy, pandas, matplotlib y demás: el ejecutable
  baja de unos 40 MB a unos 15.
- Comprobación de Tcl/Tk antes de compilar, con mensaje claro si falla.

## 2.0.0 — Editor de guiones con HUD

### Corregido (la causa del "se abre un cmd y no hace nada")

- **El objeto COM de SAPI5 se usaba desde el hilo equivocado.** Se creaba en
  el hilo principal y se llamaba desde el hilo del escuchador de teclado.
  Windows no lo permite: los objetos COM viven en un apartamento (STA). La
  llamada a `Speak` lanzaba una excepción que el envoltorio de seguridad se
  tragaba, así que los atajos se detectaban pero no sonaba nada.
  Ahora `ServicioVoz` es un hilo propio que crea el motor dentro de sí mismo
  tras llamar a `CoInitialize`, y recibe órdenes por una cola.
- **Los errores de arranque se perdían.** Si faltaba `pywin32`, el fallo
  ocurría dentro de un callback y nadie se enteraba. Ahora el motor se
  valida en el arranque y la excepción se propaga donde se puede ver y oír.
- **No había ninguna ventana.** `--sin-hud` mostraba solo texto en consola,
  que para un usuario ciego equivale a nada.
- **`tk.Frame(pady=(0, 12))` rompía la construcción de la ventana** con
  `bad screen distance`. Los tests del HUD lo detectaron.
- **Los `print()` desaparecían al compilar sin consola.** Ahora todo lo
  importante se escribe además en `%APPDATA%\VozClip\ultimo_arranque.log`.

### Añadido

- **HUD en tkinter**: franja de estado con modo, plantilla y velocidad;
  seis botones grandes navegables con Tab; editor de alto contraste con
  fuente monoespaciada y Ctrl+Z.
- **Plantillas de guion**: teatro, cine (formato estándar), diálogo
  narrativo y escaleta. Marcas `|` para saltar de hueco en hueco.
- **Modo editor propio / modo aplicación externa**, conmutable con
  Ctrl+Alt+M y anunciado por voz.
- **`--diagnostico`**: comprueba cada dependencia, enumera las voces y emite
  una frase de prueba.
- **`VozClip-Diagnostico.exe`** además del ejecutable sin consola.
- **Navegación hablada**: al moverse con las flechas se anuncia la línea.
- Normalización de atajos: `ctrl+alt+l` y `<ctrl>+<alt>+l` valen igual.
- Degradación elegante: si los atajos globales no se pueden registrar, el
  programa avisa por voz y sigue funcionando con los atajos de la ventana.

### Cambiado

- `lector.py` se sustituye por `hud.py` + `documento.py`.
- Los atajos globales ya no ejecutan acciones: solo encolan su nombre.
- La batería de tests pasa de 47 a 121, incluyendo 31 que levantan una
  ventana real bajo Xvfb.

## 1.0.0 — Lector de portapapeles

- Lectura de portapapeles, selección y archivos (txt, docx, pdf).
- Atajos globales con pynput y voces SAPI5.
