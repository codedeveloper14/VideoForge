@echo off
title IVR 2.5 - VideoForge
echo =========================================
echo     IVR 2.5 - Iniciando aplicación
echo =========================================

:: Crear carpeta AppData
set APPDATA_LOCAL=%APPDATA%\VideoForge
if not exist "%APPDATA_LOCAL%" mkdir "%APPDATA_LOCAL%"

echo 📁 Datos en: %APPDATA_LOCAL%
echo 🌐 API: http://localhost:8080
echo 🔌 WebSocket: ws://localhost:5557
echo.

:: Iniciar la aplicación
echo  Iniciando IVR 2.5...
start "" "%~dp0dist_final\IVR_2.5.exe"

echo ✅ Aplicación iniciada
echo.
pause
