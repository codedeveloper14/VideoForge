@echo off
:: ══════════════════════════════════════════════════════
::  VideoForge — Script de instalación de dependencias
::  Usa EXCLUSIVAMENTE Python 3.13 oficial instalado
:: ══════════════════════════════════════════════════════
:: Ruta exacta del Python 3.13 que instalamos
set PYTHON=%LOCALAPPDATA%\Programs\Python\Python313\python.exe
set PIP=%LOCALAPPDATA%\Programs\Python\Python313\Scripts\pip.exe
set PLAYWRIGHT=%LOCALAPPDATA%\Programs\Python\Python313\Scripts\playwright.exe
:: Verificar que Python existe
if not exist "%PYTHON%" (
    echo ERROR: Python 3.13 no encontrado
    exit 1
)
:: Instalar dependencias base
"%PIP%" install flask requests Pillow openai openai-whisper faster-whisper playwright pymysql bcrypt replicate psutil pywebview
:: Instalar torch CPU
"%PIP%" install torch --index-url https://download.pytorch.org/whl/cpu
:: Instalar Chromium
"%PLAYWRIGHT%" install chromium
exit 0
