@echo off
chcp 65001 >nul 2>&1
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
:: ─────────────────────────────────────────────
if exist ".venv\Scripts\activate.bat" (
    call .venv\Scripts\activate.bat
    echo  [OK] Entorno virtual activado
    echo.
)

:: ─────────────────────────────────────────────
:: 3. Verificar dependencias
::    pip ya omite los paquetes que esten al dia,
::    solo instala lo que sea nuevo o haya cambiado
:: ─────────────────────────────────────────────
echo  [2/3] Verificando dependencias...
pip install -r requirements.txt -q
if %ERRORLEVEL% NEQ 0 (
    echo  [!] Error instalando dependencias. Revisa el mensaje arriba.
    pause
    exit /b 1
)
echo  [OK] Dependencias listas
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
:: 5. Iniciar servidor
:: ─────────────────────────────────────────────
echo  [3/3] Iniciando servidor...
echo.
echo  =========================================
echo   Abre tu navegador en:
echo   http://127.0.0.1:5000
echo.
echo   Presiona Ctrl+C para detener el servidor
echo  =========================================
echo.

python app.py

echo.
echo  Servidor detenido.
pause
