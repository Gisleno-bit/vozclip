@echo off
REM Abre VozClip sin ventana de consola. Requiere haber ejecutado INSTALAR.bat.
cd /d "%~dp0"
if not exist ".venv\Scripts\pythonw.exe" (
    echo Primero haz doble clic en INSTALAR.bat
    pause
    exit /b 1
)
start "" ".venv\Scripts\pythonw.exe" -m vozclip
