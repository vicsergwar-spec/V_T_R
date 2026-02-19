"""
Servicio de transcripción usando Whisper (local con CUDA) y OpenAI API como respaldo
"""
import json
import logging
from pathlib import Path
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

try:
    import torch
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    logger.warning("PyTorch no está instalado. La transcripción local no estará disponible.")


class Transcriber:
    """Transcribe audio usando Whisper local (CUDA) o OpenAI Whisper API"""

    def __init__(self, model_name: str = "small", openai_api_key: Optional[str] = None):
        """
        Inicializa el transcriptor.

        Args:
            model_name: Nombre del modelo Whisper ("small" o "medium")
            openai_api_key: API key de OpenAI para respaldo (opcional)
        """
        self.model_name = model_name
        self.openai_api_key = openai_api_key
        self.model = None
        self.device = self._get_device()

    def _get_device(self) -> str:
        """Determina el dispositivo a usar (CUDA o CPU)"""
        if not TORCH_AVAILABLE:
            logger.warning("PyTorch no disponible. Se usará API de OpenAI como respaldo.")
            return "cpu"

        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            logger.info(f"GPU detectada: {gpu_name} ({gpu_memory:.1f} GB)")
            return "cuda"
        else:
            logger.warning("CUDA no disponible. Usando CPU (será más lento)")
            return "cpu"

    def load_model(self) -> None:
        """Carga el modelo Whisper en memoria"""
        if self.model is not None:
            return

        if not TORCH_AVAILABLE:
            raise RuntimeError(
                "PyTorch no está instalado. Instálalo con: "
                "pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121"
            )

        logger.info(f"Cargando modelo Whisper '{self.model_name}' en {self.device}...")

        try:
            import whisper
            self.model = whisper.load_model(self.model_name, device=self.device)
            logger.info(f"Modelo cargado exitosamente en {self.model.device}")
        except Exception as e:
            logger.error(f"Error al cargar modelo Whisper: {e}")
            raise

    def transcribe_local(
        self,
        audio_path: str,
        language: str = "es",
        progress_callback: callable = None
    ) -> dict:
        """
        Transcribe audio usando Whisper local.

        Args:
            audio_path: Ruta al archivo de audio WAV
            language: Idioma del audio (default: español)
            progress_callback: Función para reportar progreso

        Returns:
            Diccionario con la transcripción y segmentos
        """
        self.load_model()

        logger.info(f"Transcribiendo: {audio_path}")

        if progress_callback:
            progress_callback("Iniciando transcripción...")

        try:
            # Transcribir con Whisper
            result = self.model.transcribe(
                audio_path,
                language=language,
                task="transcribe",
                verbose=False,
                fp16=(self.device == "cuda"),  # FP16 solo en GPU
                word_timestamps=False
            )

            # Procesar segmentos
            raw_segments = result.get("segments", [])
            segments = []
            for segment in raw_segments:
                # avg_logprob va de ~-1 (baja confianza) a 0 (alta confianza)
                # Normalizamos a rango 0.0 - 1.0
                confianza = max(0.0, min(1.0, round(segment.get("avg_logprob", 0) + 1, 2)))
                segments.append({
                    "timestamp_inicio": self._format_timestamp(segment["start"]),
                    "timestamp_fin": self._format_timestamp(segment["end"]),
                    "texto": segment["text"].strip(),
                    "confianza": confianza
                })

            logger.info(f"Transcripción completada: {len(segments)} segmentos")

            return {
                "text": result["text"],
                "segments": segments,
                "language": result.get("language", language),
                "duration": raw_segments[-1]["end"] if raw_segments else 0.0
            }

        except Exception as e:
            logger.error(f"Error en transcripción local: {e}")
            raise

    def transcribe_openai_api(
        self,
        audio_path: str,
        progress_callback: callable = None
    ) -> dict:
        """
        Transcribe audio usando la API de OpenAI Whisper (respaldo).

        Args:
            audio_path: Ruta al archivo de audio
            progress_callback: Función para reportar progreso

        Returns:
            Diccionario con la transcripción
        """
        if not self.openai_api_key:
            raise ValueError("Se requiere API key de OpenAI para usar el respaldo")

        logger.info("Usando API de OpenAI Whisper como respaldo...")

        if progress_callback:
            progress_callback("Usando API de OpenAI...")

        try:
            from openai import OpenAI
            client = OpenAI(api_key=self.openai_api_key)

            with open(audio_path, "rb") as audio_file:
                response = client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    language="es",
                    response_format="verbose_json",
                    timestamp_granularities=["segment"]
                )

            # Procesar respuesta
            raw_segments = response.segments or []
            segments = []
            for segment in raw_segments:
                confianza = max(0.0, min(1.0, round(getattr(segment, "avg_logprob", 0) + 1, 2)))
                segments.append({
                    "timestamp_inicio": self._format_timestamp(segment.start),
                    "timestamp_fin": self._format_timestamp(segment.end),
                    "texto": segment.text.strip(),
                    "confianza": confianza
                })

            return {
                "text": response.text,
                "segments": segments,
                "language": "es",
                "duration": raw_segments[-1].end if raw_segments else 0.0
            }

        except Exception as e:
            logger.error(f"Error en API de OpenAI: {e}")
            raise

    def transcribe(
        self,
        audio_path: str,
        progress_callback: callable = None
    ) -> dict:
        """
        Transcribe audio usando el modelo configurado.

        Si model_name es 'openai', usa la API de OpenAI directamente.
        Si es un modelo local ('small'/'medium') y falla, lanza la excepción
        sin hacer fallback automático a OpenAI.

        Args:
            audio_path: Ruta al archivo de audio
            progress_callback: Función para reportar progreso

        Returns:
            Diccionario con la transcripción
        """
        if self.model_name == "openai":
            return self.transcribe_openai_api(audio_path, progress_callback)
        else:
            return self.transcribe_local(audio_path, progress_callback=progress_callback)

    def save_transcription_jsonl(self, segments: list, output_path: str) -> str:
        """
        Guarda la transcripción en formato JSONL.

        Args:
            segments: Lista de segmentos de transcripción
            output_path: Ruta de salida

        Returns:
            Ruta del archivo guardado
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, "w", encoding="utf-8") as f:
            for segment in segments:
                f.write(json.dumps(segment, ensure_ascii=False) + "\n")

        logger.info(f"Transcripción guardada en: {output_path}")
        return str(output_path)

    def load_transcription_jsonl(self, file_path: str) -> list:
        """
        Carga una transcripción desde un archivo JSONL.

        Args:
            file_path: Ruta al archivo JSONL

        Returns:
            Lista de segmentos
        """
        segments = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    segments.append(json.loads(line))
        return segments

    def get_full_text(self, segments: list) -> str:
        """
        Obtiene el texto completo de la transcripción.

        Args:
            segments: Lista de segmentos

        Returns:
            Texto completo
        """
        return " ".join(segment["texto"] for segment in segments)

    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        """Convierte segundos a formato HH:MM:SS.mmm"""
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = seconds % 60
        return f"{hours:02d}:{minutes:02d}:{secs:06.3f}"

    def get_gpu_info(self) -> dict:
        """Obtiene información sobre la GPU disponible"""
        if TORCH_AVAILABLE and torch.cuda.is_available():
            return {
                "available": True,
                "device": self.device,
                "name": torch.cuda.get_device_name(0),
                "memory_total_gb": torch.cuda.get_device_properties(0).total_memory / (1024**3),
                "memory_allocated_gb": torch.cuda.memory_allocated(0) / (1024**3),
                "memory_cached_gb": torch.cuda.memory_reserved(0) / (1024**3)
            }
        return {"available": False, "device": "cpu"}

    def unload_model(self) -> None:
        """Descarga el modelo de memoria para liberar VRAM"""
        if self.model is not None:
            del self.model
            self.model = None
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Modelo Whisper descargado de memoria")
