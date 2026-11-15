@echo off
title PS2 a PS4 - Conversor ISO a PKG
cd /d "%~dp0"
echo ========================================================
echo    Iniciando Conversor de ISO PS2 a PKG PS4...
echo ========================================================
python main.py
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo [ERROR] Hubo un problema al iniciar la aplicacion.
    echo Asegurate de tener Python instalado y accesible en tu PATH.
    pause
)

