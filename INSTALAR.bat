@echo off
setlocal EnableExtensions
title VozClip - Instalacion

REM =====================================================================
REM  INSTALAR VOZCLIP CON UN DOBLE CLIC
REM
REM  Hace todo lo necesario para que VozClip funcione en este ordenador:
REM    1. Busca Python. Si no esta, lo instala (con winget).
REM    2. Crea un entorno propio en la carpeta .venv (no toca nada mas).
REM    3. Instala las librerias.
REM    4. Descarga el modelo de voz en espanol (39 MB, una sola vez).
REM    5. Crea un acceso directo "VozClip" en el escritorio.
REM
REM  Todo se dice en voz alta, porque quien lo ejecuta puede no ver esta
REM  ventana. Al final, dos notas si ha ido bien y una grave si ha fallado.
REM  Sin acentos a proposito: la consola de Windows los destroza.
REM =====================================================================

cd /d "%~dp0"
set "PY="

echo.
echo  VozClip - Instalacion
echo  =====================
echo.
call :decir "Instalando VozClip. Tarda unos minutos. Te ire diciendo lo que hago."

REM --- 1. Python --------------------------------------------------------
echo  [ .. ] Buscando Python...
call :buscar_python
if defined PY goto :python_ok

echo  [ .. ] Python no esta instalado. Instalandolo con winget...
call :decir "Python no esta instalado. Lo instalo ahora. Puede tardar dos o tres minutos."
winget --version >nul 2>&1
if errorlevel 1 (
    echo  [FALLA] winget no esta disponible en este Windows.
    echo          Instala Python desde https://www.python.org/downloads/
    echo          marcando "Add python.exe to PATH", y vuelve a hacer doble clic.
    call :decir "No puedo instalar Python solo en este Windows. Hay que bajarlo de python punto org, marcando la casilla de anadir al PATH, y volver a hacer doble clic aqui."
    start https://www.python.org/downloads/
    goto :fin_mal
)
winget install --id Python.Python.3.12 --silent --accept-package-agreements --accept-source-agreements
call :buscar_python
if not defined PY (
    echo  [FALLA] Python se ha instalado pero no lo encuentro. Cierra esta
    echo          ventana y vuelve a hacer doble clic: al abrirla de nuevo
    echo          Windows ya lo vera.
    call :decir "Python ya esta instalado. Cierra esta ventana y vuelve a hacer doble clic en instalar, para que Windows lo vea."
    goto :fin_mal
)

:python_ok
for /f "tokens=2" %%v in ('"%PY%" --version 2^>^&1') do set "PYVER=%%v"
echo  [ OK ] Python %PYVER%: %PY%

REM --- 2. Entorno propio ------------------------------------------------
if exist ".venv\Scripts\python.exe" (
    echo  [ OK ] Entorno .venv ya existia.
) else (
    echo  [ .. ] Creando el entorno .venv...
    "%PY%" -m venv .venv
    if errorlevel 1 (
        echo  [FALLA] No he podido crear el entorno.
        call :decir "No he podido crear el entorno de Python. Comprueba que tienes permisos en esta carpeta."
        goto :fin_mal
    )
    echo  [ OK ] Entorno creado.
)
set "VPY=%~dp0.venv\Scripts\python.exe"
set "VPYW=%~dp0.venv\Scripts\pythonw.exe"

REM --- 3. Librerias -----------------------------------------------------
echo  [ .. ] Instalando las librerias (un par de minutos)...
call :decir "Instalando las librerias. Un par de minutos."
"%VPY%" -m pip install --upgrade pip --quiet
"%VPY%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [FALLA] No se han podido instalar las librerias.
    call :decir "No se han podido instalar las librerias. Comprueba la conexion a internet y vuelve a intentarlo."
    goto :fin_mal
)
"%VPY%" -m pip install -e . --quiet
if errorlevel 1 (
    echo  [FALLA] No se ha podido instalar VozClip.
    call :decir "No se ha podido instalar el programa. Vuelve a intentarlo."
    goto :fin_mal
)
echo  [ OK ] Librerias instaladas.

REM --- 4. Modelo de voz -------------------------------------------------
echo  [ .. ] Modelo de voz en espanol...
call :decir "Descargando el modelo de voz. Son treinta y nueve megas, solo esta vez."
"%VPY%" scripts\descargar_modelo.py --usuario
if errorlevel 1 (
    echo  [AVISO] El modelo no se ha podido descargar. VozClip funciona igual;
    echo          el dictado con efe uno no, hasta que lo bajes con
    echo          scripts\instalar_modelos.bat
    call :decir "El modelo de voz no se ha podido descargar. Todo lo demas funciona. Para el dictado, haz doble clic en instalar modelos punto bat mas tarde."
) else (
    echo  [ OK ] Modelo de voz listo.
)

REM --- 5. Acceso directo en el escritorio -------------------------------
echo  [ .. ] Creando el acceso directo...
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$d = [Environment]::GetFolderPath('Desktop');" ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut(\"$d\\VozClip.lnk\");" ^
  "$s.TargetPath = '%VPYW%';" ^
  "$s.Arguments = '-m vozclip';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.Description = 'VozClip Escritor';" ^
  "$s.Save()" >nul 2>&1
if errorlevel 1 (
    echo  [AVISO] No he podido crear el acceso directo. Para abrir VozClip
    echo          haz doble clic en "Iniciar VozClip.bat".
) else (
    echo  [ OK ] Acceso directo "VozClip" en el escritorio.
)

REM --- 6. Comprobacion final --------------------------------------------
echo  [ .. ] Comprobando...
"%VPY%" -m vozclip --diagnostico >nul 2>&1
echo.
echo  =====================================================
echo   Listo. Para abrir VozClip:
echo     - doble clic en el acceso directo "VozClip" del escritorio
echo     - o en "Iniciar VozClip.bat", en esta carpeta
echo  =====================================================
echo.
call :decir "VozClip esta instalado. Tienes un acceso directo en el escritorio que se llama VozClip. Al abrirlo te saluda y con control alt hache te dice todos los atajos."
call :pitido_bien
pause
exit /b 0

REM =====================================================================
:buscar_python
REM Prueba el lanzador py, luego python, luego las rutas habituales.
py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%p in ('py -3 -c "import sys; print(sys.executable)"') do set "PY=%%p"
    goto :eof
)
python -c "import sys; sys.exit(0 if sys.version_info >= (3,9) else 1)" >nul 2>&1
if not errorlevel 1 (
    for /f "delims=" %%p in ('python -c "import sys; print(sys.executable)"') do set "PY=%%p"
    goto :eof
)
for %%v in (313 312 311 310 39) do (
    if not defined PY if exist "%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe" (
        set "PY=%LOCALAPPDATA%\Programs\Python\Python%%v\python.exe"
    )
)
goto :eof

:decir
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Add-Type -AssemblyName System.Speech; $v = New-Object System.Speech.Synthesis.SpeechSynthesizer; $v.Rate = 1; $v.Speak('%~1') } catch { }" >nul 2>&1
goto :eof

:pitido_bien
powershell -NoProfile -Command "[console]::beep(660,150); [console]::beep(880,250)" >nul 2>&1
goto :eof

:pitido_mal
powershell -NoProfile -Command "[console]::beep(220,500)" >nul 2>&1
goto :eof

:fin_mal
call :pitido_mal
echo.
echo  La instalacion no ha terminado. Corrige lo de arriba y vuelve a hacer
echo  doble clic: lo que ya estaba hecho no se repite.
echo.
pause
exit /b 1
