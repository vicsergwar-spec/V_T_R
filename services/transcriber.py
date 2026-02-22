"""
Servicio de transcripción usando faster-whisper (local con CUDA) y OpenAI API como respaldo
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
    logger.warning("PyTorch no está instalado. La información de GPU estará limitada.")


class Transcriber:
    """Transcribe audio usando faster-whisper local (CUDA) o OpenAI Whisper API"""

    # Compute type por modelo y dispositivo.
    # float16    → máxima velocidad en GPU, calidad completa (requiere más VRAM)
    # int8_float16 → mitad de VRAM que float16, calidad casi idéntica (ideal para large-v3)
    # int8       → mínima VRAM, ideal para CPU
    _COMPUTE_TYPES = {
        "small":    {"cuda": "float16",       "cpu": "int8"},
        "medium":   {"cuda": "float16",       "cpu": "int8"},
        "large-v3": {"cuda": "int8_float16",  "cpu": "int8"},
    }

    def __init__(self, model_name: str = "medium", openai_api_key: Optional[str] = None):
        """
        Inicializa el transcriptor.

        Args:
            model_name: Nombre del modelo faster-whisper ("small", "medium", "large-v3")
            openai_api_key: API key de OpenAI para respaldo (opcional)
        """
        self.model_name = model_name
        self.openai_api_key = openai_api_key
        self.model = None
        self.device = self._get_device()
        self.compute_type = self._get_compute_type()

    def _get_device(self) -> str:
        """Determina el dispositivo a usar (CUDA o CPU)"""
        if TORCH_AVAILABLE and torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            gpu_memory = torch.cuda.get_device_properties(0).total_memory / (1024**3)
            logger.info(f"GPU detectada: {gpu_name} ({gpu_memory:.1f} GB)")
            return "cuda"
        else:
            logger.warning("CUDA no disponible. Usando CPU (será más lento)")
            return "cpu"

    def _get_compute_type(self) -> str:
        """Determina el compute_type óptimo para faster-whisper según modelo y dispositivo"""
        types = self._COMPUTE_TYPES.get(self.model_name, {"cuda": "float16", "cpu": "int8"})
        return types[self.device]

    def load_model(self) -> None:
        """Carga el modelo faster-whisper en memoria"""
        if self.model is not None:
            return

        logger.info(
            f"Cargando modelo faster-whisper '{self.model_name}' "
            f"en {self.device} ({self.compute_type})..."
        )

        try:
            from faster_whisper import WhisperModel
            self.model = WhisperModel(
                self.model_name,
                device=self.device,
                compute_type=self.compute_type,
            )
            logger.info("Modelo faster-whisper cargado exitosamente")
        except Exception as e:
            logger.error(f"Error al cargar modelo faster-whisper: {e}")
            raise

    def transcribe_local(
        self,
        audio_path: str,
        language: str = "es",
        progress_callback: callable = None
    ) -> dict:
        """
        Transcribe audio usando faster-whisper local.

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
            # faster-whisper devuelve un generador de segmentos e información del audio
            segments_gen, info = self.model.transcribe(
                audio_path,
                language=language,
                task="transcribe",
                beam_size=5,
                vad_filter=True,   # filtra silencios automáticamente
            )

            # Convertir el generador a lista procesando cada segmento
            segments = []
            full_text_parts = []
            last_end = 0.0

            for segment in segments_gen:
                # avg_logprob va de ~-1 (baja confianza) a 0 (alta confianza)
                # Normalizamos a rango 0.0 - 1.0
                confianza = max(0.0, min(1.0, round(segment.avg_logprob + 1, 2)))
                segments.append({
                    "timestamp_inicio": self._format_timestamp(segment.start),
                    "timestamp_fin":    self._format_timestamp(segment.end),
                    "texto":            segment.text.strip(),
                    "confianza":        confianza,
                })
                full_text_parts.append(segment.text.strip())
                last_end = segment.end

            full_text = " ".join(full_text_parts)

            logger.info(f"Transcripción completada: {len(segments)} segmentos")

            return {
                "text":     full_text,
                "segments": segments,
                "language": info.language,
                "duration": last_end,
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
                    "timestamp_fin":    self._format_timestamp(segment.end),
                    "texto":            segment.text.strip(),
                    "confianza":        confianza,
                })

            return {
                "text":     response.text,
                "segments": segments,
                "language": "es",
                "duration": raw_segments[-1].end if raw_segments else 0.0,
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
        Si es un modelo local ('small', 'medium', 'large-v3') y falla, lanza la excepción
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
                "memory_total_gb":     torch.cuda.get_device_properties(0).total_memory / (1024**3),
                "memory_allocated_gb": torch.cuda.memory_allocated(0) / (1024**3),
                "memory_cached_gb":    torch.cuda.memory_reserved(0) / (1024**3),
            }
        return {"available": False, "device": "cpu"}

    def unload_model(self) -> None:
        """Descarga el modelo de memoria para liberar VRAM"""
        if self.model is not None:
            del self.model
            self.model = None
            if TORCH_AVAILABLE and torch.cuda.is_available():
                torch.cuda.empty_cache()
            logger.info("Modelo faster-whisper descargado de memoria")
