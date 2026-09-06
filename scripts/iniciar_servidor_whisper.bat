@echo off
setlocal
title VozClip - Servidor de whisper

REM Arranca el servidor local de faster-whisper. Deja esta ventana abierta
REM mientras dictes: VozClip le manda el audio y recibe el texto.
REM
REM Con GPU NVIDIA usa large-v3 en float16 automaticamente. Sin GPU, small
REM en int8. Se puede forzar: iniciar_servidor_whisper.bat --modelo medium

cd /d "%~dp0\.."

python -c "import faster_whisper" 2>nul
if errorlevel 1 (
    echo faster-whisper no esta instalado. Instalandolo...
    python -m pip install -r requirements-whisper.txt
    if errorlevel 1 (
        echo No se ha podido instalar. Comprueba que Python esta en el PATH.
        pause
        exit /b 1
    )
)

python scripts\servidor_whisper.py %*
pause
