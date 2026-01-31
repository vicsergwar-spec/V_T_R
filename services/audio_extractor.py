"""
Servicio de extracción de audio usando FFmpeg
"""
import subprocess
import os
from pathlib import Path
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class AudioExtractor:
    """Extrae audio de archivos de video usando FFmpeg"""

    def __init__(self, sample_rate: int = 16000):
        """
        Inicializa el extractor de audio.

        Args:
            sample_rate: Frecuencia de muestreo del audio (16000 Hz es óptimo para Whisper)
        """
        self.sample_rate = sample_rate
        self._check_ffmpeg()

    def _check_ffmpeg(self) -> bool:
        """Verifica que FFmpeg está instalado y disponible"""
        try:
            result = subprocess.run(
                ["ffmpeg", "-version"],
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )
            if result.returncode == 0:
                logger.info("FFmpeg encontrado y funcionando")
                return True
        except FileNotFoundError:
            raise RuntimeError(
                "FFmpeg no está instalado o no está en el PATH. "
                "Por favor instala FFmpeg siguiendo las instrucciones del README."
            )
        return False

    def extract_audio(self, video_path: str, output_path: str = None) -> str:
        """
        Extrae el audio de un archivo de video.

        Args:
            video_path: Ruta al archivo de video
            output_path: Ruta de salida para el audio WAV (opcional)

        Returns:
            Ruta al archivo de audio extraído
        """
        video_path = Path(video_path)

        if not video_path.exists():
            raise FileNotFoundError(f"No se encontró el archivo de video: {video_path}")

        # Generar ruta de salida si no se proporciona
        if output_path is None:
            output_path = video_path.with_suffix(".wav")
        else:
            output_path = Path(output_path)

        logger.info(f"Extrayendo audio de: {video_path}")
        logger.info(f"Guardando en: {output_path}")

        # Comando FFmpeg para extraer audio
        # -i: archivo de entrada
        # -vn: sin video
        # -acodec pcm_s16le: codec de audio WAV estándar
        # -ar: sample rate
        # -ac 1: mono (mejor para transcripción)
        # -y: sobrescribir si existe
        cmd = [
            "ffmpeg",
            "-i", str(video_path),
            "-vn",
            "-acodec", "pcm_s16le",
            "-ar", str(self.sample_rate),
            "-ac", "1",
            "-y",
            str(output_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode != 0:
                logger.error(f"Error de FFmpeg: {result.stderr}")
                raise RuntimeError(f"Error al extraer audio: {result.stderr}")

            if not output_path.exists():
                raise RuntimeError("FFmpeg no generó el archivo de audio")

            # Obtener información del archivo generado
            file_size = output_path.stat().st_size / (1024 * 1024)  # MB
            logger.info(f"Audio extraído exitosamente. Tamaño: {file_size:.2f} MB")

            return str(output_path)

        except subprocess.TimeoutExpired:
            raise RuntimeError("Tiempo de espera agotado al extraer audio")

    def get_video_duration(self, video_path: str) -> float:
        """
        Obtiene la duración de un video en segundos.

        Args:
            video_path: Ruta al archivo de video

        Returns:
            Duración en segundos
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            str(video_path)
        ]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            )

            if result.returncode == 0:
                return float(result.stdout.strip())
        except Exception as e:
            logger.warning(f"No se pudo obtener la duración del video: {e}")

        return 0.0

    def get_video_info(self, video_path: str) -> dict:
        """
        Obtiene información sobre un archivo de video.

        Args:
            video_path: Ruta al archivo de video

        Returns:
            Diccionario con información del video
        """
        video_path = Path(video_path)

        info = {
            "filename": video_path.name,
            "size_mb": video_path.stat().st_size / (1024 * 1024),
            "duration_seconds": self.get_video_duration(str(video_path)),
            "format": video_path.suffix.lower()
        }

        # Convertir duración a formato legible
        duration = info["duration_seconds"]
        hours = int(duration // 3600)
        minutes = int((duration % 3600) // 60)
        seconds = int(duration % 60)
        info["duration_formatted"] = f"{hours:02d}:{minutes:02d}:{seconds:02d}"

        return info
