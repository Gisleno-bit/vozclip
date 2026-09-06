@echo off
setlocal EnableExtensions
title VozClip - Instalar el dictado por voz

REM =====================================================================
REM  INSTALADOR DEL MODELO DE DICTADO EN ESPANOL
REM
REM  Doble clic y listo. Descarga el modelo de voz en espanol (unos 39
REM  megas), lo descomprime en la carpeta de VozClip y comprueba que ha
REM  quedado bien. No hay que escribir nada.
REM
REM  TODO EL PROCESO SE DICE EN VOZ ALTA con la voz de Windows, porque
REM  quien lo ejecuta puede no ver esta ventana. Al final, un pitido
REM  distinto segun haya ido bien o mal.
REM
REM  Este archivo evita los acentos a proposito: la consola de Windows
REM  los destroza si el archivo no esta en la codificacion exacta.
REM =====================================================================

set "URL=https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip"
set "NOMBRE_MODELO=vosk-model-small-es-0.42"
REM  Se instala en C:\Users\Public y NO en el perfil del usuario. La
REM  libreria de Vosk esta en C y no puede abrir rutas con tildes o
REM  enyes: "C:\Users\Julian-con-tilde\..." falla con "Failed to create
REM  a model". Public es ASCII por construccion y siempre escribible.
set "DESTINO=%PUBLIC%\VozClip\modelos"
if "%PUBLIC%"=="" set "DESTINO=C:\VozClip\modelos"
set "ZIP=%TEMP%\vozclip_modelo.zip"

echo.
echo  VozClip - Instalar el dictado por voz
echo  =====================================
echo.

call :decir "Instalando el modelo de dictado en espanol. Son unos treinta y nueve megas. Solo hay que hacerlo una vez. Espera un momento."

REM --- 1. Ya instalado? -------------------------------------------------
if exist "%DESTINO%\%NOMBRE_MODELO%\am\final.mdl" (
    echo  [ OK ] El modelo ya estaba instalado en:
    echo         %DESTINO%\%NOMBRE_MODELO%
    call :decir "El modelo de voz ya estaba instalado. No hay que hacer nada mas. Ya puedes dictar con efe uno."
    call :pitido_bien
    goto :fin_bien
)

REM --- 2. Carpeta de destino --------------------------------------------
if not exist "%DESTINO%" mkdir "%DESTINO%" 2>nul
if not exist "%DESTINO%" (
    echo  [FALLA] No he podido crear la carpeta %DESTINO%
    call :decir "No he podido crear la carpeta de modelos. Comprueba que tienes permisos en tu carpeta de usuario."
    goto :fin_mal
)

REM --- 3. Descarga ------------------------------------------------------
echo  [ .. ] Descargando el modelo, unos 39 MB...
echo         %URL%
if exist "%ZIP%" del /q "%ZIP%" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12;" ^
  "$ProgressPreference = 'SilentlyContinue';" ^
  "try { Invoke-WebRequest -Uri '%URL%' -OutFile '%ZIP%' -UseBasicParsing; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo  [FALLA] La descarga no ha funcionado.
    echo.
    echo  Puedes descargarlo a mano desde:
    echo    %URL%
    echo.
    echo  Descomprime el ZIP y deja la carpeta vosk-model-small-es-0.42
    echo  dentro de:
    echo    %DESTINO%
    echo.
    call :decir "La descarga no ha funcionado. En la ventana tienes la direccion para bajarlo a mano."
    goto :fin_mal
)
if not exist "%ZIP%" (
    echo  [FALLA] No ha aparecido el archivo descargado.
    call :decir "La descarga no ha dejado ningun archivo. Vuelve a intentarlo."
    goto :fin_mal
)

REM Un zip de menos de un mega es una pagina de error, no el modelo.
for %%A in ("%ZIP%") do set "TAMANO=%%~zA"
if %TAMANO% LSS 1000000 (
    echo  [FALLA] El archivo descargado es demasiado pequeno: %TAMANO% bytes.
    call :decir "El archivo descargado no es el modelo. Puede que la direccion haya cambiado. Vuelve a intentarlo mas tarde."
    del /q "%ZIP%" 2>nul
    goto :fin_mal
)
echo  [ OK ] Descargado: %TAMANO% bytes.
call :decir "Descarga terminada. Descomprimiendo."

REM --- 4. Descomprimir --------------------------------------------------
echo  [ .. ] Descomprimiendo en %DESTINO% ...
if exist "%DESTINO%\%NOMBRE_MODELO%" rmdir /s /q "%DESTINO%\%NOMBRE_MODELO%" 2>nul

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$ProgressPreference = 'SilentlyContinue';" ^
  "try { Expand-Archive -LiteralPath '%ZIP%' -DestinationPath '%DESTINO%' -Force; exit 0 } catch { Write-Host $_.Exception.Message; exit 1 }"

if errorlevel 1 (
    echo  [FALLA] No he podido descomprimir el modelo.
    call :decir "No he podido descomprimir el modelo. El archivo puede estar danado. Vuelve a intentarlo."
    goto :fin_mal
)
del /q "%ZIP%" 2>nul

REM --- 5. Verificacion --------------------------------------------------
REM Un modelo de Vosk valido tiene el modelo acustico en am\final.mdl.
REM Es lo mismo que comprueba VozClip al arrancar.
if not exist "%DESTINO%\%NOMBRE_MODELO%\am\final.mdl" (
    echo  [FALLA] El modelo se ha descomprimido pero no tiene la estructura esperada.
    call :decir "El modelo se ha descomprimido pero falta una parte. Vuelve a intentarlo."
    goto :fin_mal
)

echo.
echo  [ OK ] Modelo de voz instalado correctamente en:
echo         %DESTINO%\%NOMBRE_MODELO%
echo.
call :decir "Modelo de voz instalado correctamente. Ya puedes dictar con efe uno. Abre VozClip cuando quieras."
call :pitido_bien
goto :fin_bien

REM =====================================================================
REM  Subrutinas
REM =====================================================================
:decir
REM Habla con la voz de Windows. Si no hay voz instalada, no pasa nada.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "try { Add-Type -AssemblyName System.Speech; $v = New-Object System.Speech.Synthesis.SpeechSynthesizer; $v.Rate = 1; $v.Speak('%~1') } catch { }" >nul 2>&1
goto :eof

:pitido_bien
REM Dos notas ascendentes: ha ido bien.
powershell -NoProfile -Command "[console]::beep(660,150); [console]::beep(880,250)" >nul 2>&1
goto :eof

:pitido_mal
REM Una nota grave y larga: ha fallado.
powershell -NoProfile -Command "[console]::beep(220,500)" >nul 2>&1
goto :eof

:fin_mal
call :pitido_mal
echo.
echo  Ha habido un problema. Puedes cerrar esta ventana y volver a intentarlo.
echo  Si sigue fallando, abre VozClip-Diagnostico.exe para mas detalles.
echo.
pause
exit /b 1

:fin_bien
echo  Puedes cerrar esta ventana.
echo.
pause
exit /b 0
