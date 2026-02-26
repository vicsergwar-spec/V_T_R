@echo off
chcp 65001 >nul 2>&1
:: Moverse al directorio donde esta este archivo (funciona desde cualquier ubicacion)
cd /d "%~dp0"
title V_T_R - Video Transcriptor y Resumen

echo.
echo  =========================================
echo   V_T_R - Video Transcriptor y Resumen
echo  =========================================
echo.

:: ─────────────────────────────────────────────
:: 1. Actualizar codigo desde el repositorio
:: ─────────────────────────────────────────────
echo  [1/3] Buscando actualizaciones...
git pull >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo  [!] Sin conexion o sin cambios — usando version local
) else (
    echo  [OK] Codigo al dia
)
echo.

:: ─────────────────────────────────────────────
:: 2. Activar entorno virtual si existe
::    Busca primero .venv\ y luego venv\
:: ─────────────────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo  [OK] Entorno virtual activado ^(.venv^)
    echo.
) else if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
    echo  [OK] Entorno virtual activado ^(venv^)
    echo.
) else (
    echo  [!] No se encontro entorno virtual — usando Python del sistema
    echo.
)

:: ─────────────────────────────────────────────
:: 3. Verificar dependencias
::    Se usa "python -m pip" para asegurar que
::    funciona aunque pip no este en el PATH solo
:: ─────────────────────────────────────────────
echo  [2/3] Verificando dependencias...
python -m pip install -r requirements.txt -q
if %ERRORLEVEL% NEQ 0 (
    echo  [!] Error instalando dependencias. Revisa el mensaje arriba.
    pause
    exit /b 1
)
echo  [OK] Dependencias listas
echo.

:: ─────────────────────────────────────────────
:: 3b. Verificar ventana nativa (PyQt6)
::     PyQt6 se instala desde requirements.txt
::     con wheels precompilados (sin compilar nada).
:: ─────────────────────────────────────────────
python -c "from PyQt6.QtWebEngineWidgets import QWebEngineView" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo  [OK] Ventana nativa disponible ^(Qt^)
) else (
    echo  [!] Ventana nativa no disponible — se abrira el navegador automaticamente
)
echo.

:: ─────────────────────────────────────────────
:: 4. Verificar archivo .env
:: ─────────────────────────────────────────────
if not exist ".env" (
    echo  [!] AVISO: No se encontro el archivo .env
    echo      Copia .env.example a .env y configura tu GEMINI_API_KEY
    echo      Para copiarlo: copy .env.example .env
    echo.
)

:: ─────────────────────────────────────────────
:: 5. Iniciar ventana nativa (pywebview + Flask)
:: ─────────────────────────────────────────────
echo  [3/3] Abriendo ventana de la aplicacion...
echo.
echo  =========================================
echo   Abriendo V_T_R...
echo   ^(ventana propia si pywebview esta OK,
echo    navegador automatico si no^)
echo.
echo   Cierra la ventana / presiona Ctrl+C para salir
echo  =========================================
echo.

python launch.py

echo.
echo  Servidor detenido.
pause
