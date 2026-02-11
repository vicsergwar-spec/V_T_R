"""
Servicio de gestión de archivos y carpetas
"""
import os
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class FileManager:
    """Gestiona la organización de archivos y carpetas del sistema"""

    def __init__(self, base_dir: str, clases_dir: str, temp_dir: str):
        """
        Inicializa el gestor de archivos.

        Args:
            base_dir: Directorio base del proyecto
            clases_dir: Directorio donde se guardan las clases
            temp_dir: Directorio temporal para procesamiento
        """
        self.base_dir = Path(base_dir)
        self.clases_dir = Path(clases_dir)
        self.temp_dir = Path(temp_dir)

        # Crear directorios si no existen
        self.clases_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"FileManager inicializado. Clases en: {self.clases_dir}")

    def create_class_folder(self, folder_name: str) -> Path:
        """
        Crea una carpeta para una nueva clase.

        Args:
            folder_name: Nombre de la carpeta (formato Materia_Tema)

        Returns:
            Path de la carpeta creada
        """
        # Sanitizar nombre
        folder_name = self._sanitize_folder_name(folder_name)

        # Crear ruta
        class_folder = self.clases_dir / folder_name

        # Si ya existe, agregar sufijo numérico
        if class_folder.exists():
            counter = 1
            while (self.clases_dir / f"{folder_name}_{counter}").exists():
                counter += 1
            class_folder = self.clases_dir / f"{folder_name}_{counter}"

        class_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Carpeta de clase creada: {class_folder}")

        return class_folder

    def save_transcription(self, segments: list, class_folder: Path) -> str:
        """
        Guarda la transcripción en formato JSONL.

        Args:
            segments: Lista de segmentos de transcripción
            class_folder: Carpeta de la clase

        Returns:
            Ruta del archivo guardado
        """
        output_path = class_folder / "transcripcion.jsonl"

        with open(output_path, "w", encoding="utf-8") as f:
            for segment in segments:
                f.write(json.dumps(segment, ensure_ascii=False) + "\n")

        logger.info(f"Transcripción guardada: {output_path}")
        return str(output_path)

    def save_summary(self, summary: str, class_folder: Path) -> str:
        """
        Guarda el resumen en formato Markdown.

        Args:
            summary: Texto del resumen
            class_folder: Carpeta de la clase

        Returns:
            Ruta del archivo guardado
        """
        output_path = class_folder / "resumen.md"

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(summary)

        logger.info(f"Resumen guardado: {output_path}")
        return str(output_path)

    def save_video_to_temp(self, file_storage, filename: str) -> str:
        """
        Guarda un video subido en el directorio temporal.

        Args:
            file_storage: Objeto FileStorage de Flask
            filename: Nombre del archivo

        Returns:
            Ruta del archivo guardado
        """
        # Sanitizar nombre de archivo
        safe_filename = self._sanitize_filename(filename)
        temp_path = self.temp_dir / safe_filename

        file_storage.save(str(temp_path))
        logger.info(f"Video guardado temporalmente: {temp_path}")

        return str(temp_path)

    def cleanup_temp_files(self, video_path: str, audio_path: str = None) -> None:
        """
        Elimina archivos temporales (video y audio).

        Args:
            video_path: Ruta del video a eliminar
            audio_path: Ruta del audio a eliminar (opcional)
        """
        try:
            if video_path and Path(video_path).exists():
                os.remove(video_path)
                logger.info(f"Video temporal eliminado: {video_path}")

            if audio_path and Path(audio_path).exists():
                os.remove(audio_path)
                logger.info(f"Audio temporal eliminado: {audio_path}")

        except Exception as e:
            logger.warning(f"Error al eliminar archivos temporales: {e}")

    def get_all_classes(self) -> list:
        """
        Obtiene lista de todas las clases procesadas.

        Returns:
            Lista de diccionarios con información de cada clase
        """
        classes = []

        if not self.clases_dir.exists():
            logger.warning(f"El directorio de clases no existe: {self.clases_dir}")
            return classes

        try:
            for folder in self.clases_dir.iterdir():
                if folder.is_dir():
                    class_info = self._get_class_info(folder)
                    if class_info:
                        classes.append(class_info)
        except OSError as e:
            logger.error(f"Error al leer el directorio de clases: {e}")
            return classes

        # Ordenar por fecha de modificación (más reciente primero)
        classes.sort(key=lambda x: x.get("created_at", ""), reverse=True)

        return classes

    def get_class_by_id(self, class_id: str) -> Optional[dict]:
        """
        Obtiene información de una clase específica.

        Args:
            class_id: ID (nombre de carpeta) de la clase

        Returns:
            Diccionario con información de la clase o None
        """
        class_folder = self.clases_dir / class_id

        if not class_folder.exists() or not class_folder.is_dir():
            return None

        return self._get_class_info(class_folder)

    def get_transcription(self, class_id: str) -> Optional[list]:
        """
        Obtiene la transcripción de una clase.

        Args:
            class_id: ID de la clase

        Returns:
            Lista de segmentos o None
        """
        transcription_path = self.clases_dir / class_id / "transcripcion.jsonl"

        if not transcription_path.exists():
            return None

        segments = []
        with open(transcription_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    segments.append(json.loads(line))

        return segments

    def get_transcription_text(self, class_id: str) -> Optional[str]:
        """
        Obtiene el texto completo de la transcripción.

        Args:
            class_id: ID de la clase

        Returns:
            Texto completo o None
        """
        segments = self.get_transcription(class_id)
        if segments:
            return " ".join(segment["texto"] for segment in segments)
        return None

    def get_summary(self, class_id: str) -> Optional[str]:
        """
        Obtiene el resumen de una clase.

        Args:
            class_id: ID de la clase

        Returns:
            Texto del resumen o None
        """
        summary_path = self.clases_dir / class_id / "resumen.md"

        if not summary_path.exists():
            return None

        with open(summary_path, "r", encoding="utf-8") as f:
            return f.read()

    def delete_class(self, class_id: str) -> bool:
        """
        Elimina una clase y todos sus archivos.

        Args:
            class_id: ID de la clase

        Returns:
            True si se eliminó exitosamente
        """
        class_folder = self.clases_dir / class_id

        if not class_folder.exists():
            return False

        try:
            shutil.rmtree(class_folder)
            logger.info(f"Clase eliminada: {class_id}")
            return True
        except Exception as e:
            logger.error(f"Error al eliminar clase: {e}")
            return False

    def _get_class_info(self, folder: Path) -> Optional[dict]:
        """Obtiene información de una carpeta de clase"""
        transcription_path = folder / "transcripcion.jsonl"
        summary_path = folder / "resumen.md"

        # Verificar que tenga al menos uno de los archivos esperados
        if not transcription_path.exists() and not summary_path.exists():
            return None

        # Obtener estadísticas (st_mtime es más confiable que st_ctime en Linux)
        created_at = datetime.fromtimestamp(folder.stat().st_mtime)

        # Contar segmentos de transcripción
        segment_count = 0
        if transcription_path.exists():
            with open(transcription_path, "r", encoding="utf-8") as f:
                segment_count = sum(1 for line in f if line.strip())

        return {
            "id": folder.name,
            "name": folder.name.replace("_", " "),
            "created_at": created_at.isoformat(),
            "created_at_formatted": created_at.strftime("%d/%m/%Y %H:%M"),
            "has_transcription": transcription_path.exists(),
            "has_summary": summary_path.exists(),
            "segment_count": segment_count,
            "path": str(folder)
        }

    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        """Sanitiza un nombre de carpeta"""
        # Reemplazar espacios y caracteres especiales
        name = name.replace(" ", "_")
        name = name.replace("-", "_")

        # Mantener solo caracteres alfanuméricos y guiones bajos
        sanitized = "".join(c for c in name if c.isalnum() or c == "_")

        # Limitar longitud
        if len(sanitized) > 100:
            sanitized = sanitized[:100]

        return sanitized or "Clase_Sin_Nombre"

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitiza un nombre de archivo"""
        # Obtener extensión
        path = Path(filename)
        name = path.stem
        ext = path.suffix

        # Sanitizar nombre
        name = "".join(c for c in name if c.isalnum() or c in "._- ")
        name = name.replace(" ", "_")

        # Agregar timestamp para evitar colisiones
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        return f"{name}_{timestamp}{ext}"
