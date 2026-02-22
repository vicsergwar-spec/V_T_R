"""
Configuración del sistema V_T_R - Video Transcriptor y Resumen
"""
import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Directorio base del proyecto
BASE_DIR = Path(__file__).parent.absolute()

# Directorio donde se guardan las clases procesadas
CLASES_DIR = BASE_DIR / "clases"
CLASES_DIR.mkdir(exist_ok=True)

# Directorio temporal para archivos de procesamiento
TEMP_DIR = BASE_DIR / "temp"
TEMP_DIR.mkdir(exist_ok=True)

# API Keys
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Configuración de faster-whisper
# VRAM estimado con cuantización automática (float16 en GPU para small/medium, int8_float16 para large-v3)
WHISPER_MODELS = {
    "small": {
        "name": "small",
        "description": "Modelo pequeño - Rápido, ~1-2GB VRAM",
        "vram_required": "~1-2GB"
    },
    "medium": {
        "name": "medium",
        "description": "Modelo mediano - Recomendado, calidad/velocidad óptima, ~3GB VRAM",
        "vram_required": "~3GB"
    },
    "large-v3": {
        "name": "large-v3",
        "description": "Modelo grande - Máxima calidad (experimental), ~4-5GB VRAM",
        "vram_required": "~4-5GB"
    },
    "openai": {
        "name": "openai",
        "description": "API de OpenAI Whisper - En la nube, no requiere GPU",
        "vram_required": "N/A"
    }
}
DEFAULT_WHISPER_MODEL = "medium"

# Configuración de Gemini
# Para cambiar de modelo: pon aquí el ID exacto que ves en Google AI Studio
GEMINI_MODEL = "gemini-3-flash-preview"
GEMINI_MODEL_PRO = "gemini-3-flash-preview"

# Configuración de FFmpeg
AUDIO_FORMAT = "wav"
AUDIO_SAMPLE_RATE = 16000  # 16kHz es óptimo para Whisper

# Formatos de video soportados
SUPPORTED_VIDEO_FORMATS = [
    ".mp4", ".mkv", ".avi", ".mov", ".webm",
    ".flv", ".wmv", ".m4v", ".mpeg", ".mpg"
]

# Configuración del servidor Flask
FLASK_HOST = "127.0.0.1"
FLASK_PORT = 5000
FLASK_DEBUG = True

# Tamaño máximo de archivo (en bytes) - 2GB
MAX_CONTENT_LENGTH = 2 * 1024 * 1024 * 1024
