#!/bin/bash
# V_T_R - Video Transcriptor y Resumen
# Script de inicio para Linux / macOS

# Moverse al directorio del script (por si se ejecuta desde otro lado)
cd "$(dirname "$0")"

echo ""
echo " ========================================="
echo "  V_T_R - Video Transcriptor y Resumen"
echo " ========================================="
echo ""

# ──────────────────────────────────────────────
# 1. Actualizar código desde el repositorio
# ──────────────────────────────────────────────
echo " [1/3] Buscando actualizaciones..."
if git pull > /dev/null 2>&1; then
    echo " [OK] Codigo al dia"
else
    echo " [!]  Sin conexion o sin cambios — usando version local"
fi
echo ""

# ──────────────────────────────────────────────
# 2. Activar entorno virtual si existe
# ──────────────────────────────────────────────
if [ -f ".venv/bin/activate" ]; then
    source .venv/bin/activate
    echo " [OK] Entorno virtual activado"
    echo ""
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
    echo " [OK] Entorno virtual activado"
    echo ""
fi

# ──────────────────────────────────────────────
# 3. Verificar dependencias
#    pip ya omite paquetes al dia, solo instala
#    lo que sea nuevo o haya cambiado
# ──────────────────────────────────────────────
echo " [2/3] Verificando dependencias..."
if ! pip install -r requirements.txt -q; then
    echo " [!]  Error instalando dependencias. Revisa el mensaje arriba."
    exit 1
fi
echo " [OK] Dependencias listas"
echo ""

# ──────────────────────────────────────────────
# 4. Verificar archivo .env
# ──────────────────────────────────────────────
if [ ! -f ".env" ]; then
    echo " [!]  AVISO: No se encontro el archivo .env"
    echo "      Copia .env.example a .env y configura tu GEMINI_API_KEY"
    echo "      Para copiarlo:  cp .env.example .env"
    echo ""
fi

# ──────────────────────────────────────────────
# 5. Iniciar servidor
# ──────────────────────────────────────────────
echo " [3/3] Iniciando servidor..."
echo ""
echo " ========================================="
echo "  Abre tu navegador en:"
echo "  http://127.0.0.1:5000"
echo ""
echo "  Presiona Ctrl+C para detener el servidor"
echo " ========================================="
echo ""

python app.py
