@echo off
REM ---------------------------------------------------------------
REM  Crea un acceso directo a VozClip.exe en la carpeta de Inicio,
REM  para que el programa arranque solo al encender el ordenador.
REM
REM  Uso: copia este .bat junto a VozClip.exe y haz doble clic.
REM ---------------------------------------------------------------

set "ORIGEN=%~dp0VozClip.exe"
set "DESTINO=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\VozClip.lnk"

if not exist "%ORIGEN%" (
    echo No encuentro VozClip.exe en esta carpeta.
    echo Copia este archivo .bat junto al ejecutable y vuelve a intentarlo.
    pause
    exit /b 1
)

powershell -NoProfile -Command ^
  "$s = (New-Object -ComObject WScript.Shell).CreateShortcut('%DESTINO%');" ^
  "$s.TargetPath = '%ORIGEN%';" ^
  "$s.WorkingDirectory = '%~dp0';" ^
  "$s.Description = 'VozClip - lector de texto por voz';" ^
  "$s.Save()"

echo.
echo Listo. VozClip arrancara automaticamente al iniciar Windows.
echo Para deshacerlo, borra el acceso directo de: shell:startup
pause
