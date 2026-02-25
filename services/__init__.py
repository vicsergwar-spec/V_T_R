"""
Módulo de servicios para V_T_R - Video Transcriptor y Resumen
"""
from .audio_extractor import AudioExtractor
from .transcriber import Transcriber
from .gemini_service import GeminiService
from .file_manager import FileManager
from .slide_extractor import SlideExtractor

__all__ = [
    "AudioExtractor",
    "Transcriber",
    "GeminiService",
    "FileManager",
    "SlideExtractor",
]
