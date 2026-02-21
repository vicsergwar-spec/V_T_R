"""
Servicio de gestión de archivos y carpetas
"""
import os
import re
import json
import shutil
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Detecta el sufijo de fecha/hora que añadimos al crear clases: _YYYY-MM-DD_HH-MM
_DATE_SUFFIX_RE = re.compile(r'^(.+?)_(\d{4}-\d{2}-\d{2})_(\d{2}-\d{2})$')


class FileManager:
    """Gestiona la organización de archivos y carpetas del sistema"""

    def __init__(self, base_dir: str, clases_dir: str, temp_dir: str):
        self.base_dir = Path(base_dir)
        self.clases_dir = Path(clases_dir)
        self.temp_dir = Path(temp_dir)

        self.clases_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dir.mkdir(parents=True, exist_ok=True)

        logger.info(f"FileManager inicializado. Clases en: {self.clases_dir}")

    # ──────────────────────────────────────────────────────────
    # Gestión de clases
    # ──────────────────────────────────────────────────────────

    def create_class_folder(self, folder_name: str, parent_path: str = "") -> Path:
        """
        Crea una carpeta para una nueva clase.
        El nombre final será: {nombre_IA}_{YYYY-MM-DD}_{HH-MM}

        Args:
            folder_name: Nombre generado por Gemini (Materia_Tema)
            parent_path: Ruta relativa de la carpeta destino (vacío = raíz)

        Returns:
            Path de la carpeta creada
        """
        folder_name = self._sanitize_folder_name(folder_name)

        # Añadir sufijo de fecha y hora
        now = datetime.now()
        date_suffix = now.strftime("%Y-%m-%d_%H-%M")
        full_name = f"{folder_name}_{date_suffix}"

        # Directorio padre
        if parent_path:
            parent_dir = self.clases_dir / parent_path
            parent_dir.mkdir(parents=True, exist_ok=True)
        else:
            parent_dir = self.clases_dir

        class_folder = parent_dir / full_name

        # Manejar duplicados
        if class_folder.exists():
            counter = 1
            while (parent_dir / f"{full_name}_{counter}").exists():
                counter += 1
            class_folder = parent_dir / f"{full_name}_{counter}"

        class_folder.mkdir(parents=True, exist_ok=True)
        logger.info(f"Carpeta de clase creada: {class_folder}")
        return class_folder

    def save_transcription(self, segments: list, class_folder: Path) -> str:
        output_path = class_folder / "transcripcion.jsonl"
        with open(output_path, "w", encoding="utf-8") as f:
            for segment in segments:
                f.write(json.dumps(segment, ensure_ascii=False) + "\n")
        logger.info(f"Transcripción guardada: {output_path}")
        return str(output_path)

    def save_summary(self, summary: str, class_folder: Path) -> str:
        output_path = class_folder / "resumen.md"
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(summary)
        logger.info(f"Resumen guardado: {output_path}")
        return str(output_path)

    def save_video_to_temp(self, file_storage, filename: str) -> str:
        safe_filename = self._sanitize_filename(filename)
        temp_path = self.temp_dir / safe_filename
        file_storage.save(str(temp_path))
        logger.info(f"Video guardado temporalmente: {temp_path}")
        return str(temp_path)

    def cleanup_temp_files(self, video_path: str, audio_path: str = None) -> None:
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
        Obtiene todas las clases de forma recursiva (incluyendo las de subcarpetas).
        Ordenadas de más vieja a más nueva.
        """
        classes = []
        if not self.clases_dir.exists():
            return classes
        try:
            self._scan_for_classes(self.clases_dir, "", classes)
        except OSError as e:
            logger.error(f"Error al leer directorio de clases: {e}")
        classes.sort(key=lambda x: x.get("created_at", ""))  # más vieja primero
        return classes

    def _scan_for_classes(self, directory: Path, relative_path: str, classes: list) -> None:
        """Escanea recursivamente buscando carpetas de clase (las que tienen transcripcion.jsonl)"""
        try:
            for item in sorted(directory.iterdir(), key=lambda p: p.name):
                if not item.is_dir():
                    continue
                item_rel = f"{relative_path}/{item.name}" if relative_path else item.name
                class_info = self._get_class_info(item, item_rel)
                if class_info:
                    classes.append(class_info)
                else:
                    # Es una carpeta de organización, recursear
                    self._scan_for_classes(item, item_rel, classes)
        except OSError as e:
            logger.error(f"Error escaneando {directory}: {e}")

    def get_class_by_id(self, class_id: str) -> Optional[dict]:
        """
        Obtiene información de una clase por su ID (ruta relativa desde clases_dir).

        Args:
            class_id: Ruta relativa, ej: "Matematicas/Git_2026-02-19_22-07" o "Git_2026-02-19"
        """
        class_folder = self.clases_dir / class_id
        if not class_folder.exists() or not class_folder.is_dir():
            return None
        return self._get_class_info(class_folder, class_id)

    def get_transcription(self, class_id: str) -> Optional[list]:
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
        segments = self.get_transcription(class_id)
        if segments:
            return " ".join(segment["texto"] for segment in segments)
        return None

    def get_summary(self, class_id: str) -> Optional[str]:
        summary_path = self.clases_dir / class_id / "resumen.md"
        if not summary_path.exists():
            return None
        with open(summary_path, "r", encoding="utf-8") as f:
            return f.read()

    def get_chat_history(self, class_id: str) -> Optional[list]:
        """Lee el historial de chat guardado en disco para una clase."""
        history_path = self.clases_dir / class_id / "chat_historial.json"
        if not history_path.exists():
            return None
        try:
            with open(history_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Error al leer historial de chat: {e}")
            return None

    def save_chat_history(self, class_id: str, history: list) -> None:
        """Guarda el historial de chat en disco."""
        history_path = self.clases_dir / class_id / "chat_historial.json"
        try:
            with open(history_path, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning(f"Error al guardar historial de chat: {e}")

    def delete_chat_history(self, class_id: str) -> None:
        """Elimina el historial de chat del disco."""
        history_path = self.clases_dir / class_id / "chat_historial.json"
        if history_path.exists():
            try:
                history_path.unlink()
            except Exception as e:
                logger.warning(f"Error al eliminar historial de chat: {e}")

    def get_cache_name(self, class_id: str) -> Optional[str]:
        """Lee el nombre del caché de Gemini guardado para una clase."""
        path = self.clases_dir / class_id / "gemini_cache.txt"
        if not path.exists():
            return None
        content = path.read_text(encoding="utf-8").strip()
        return content if content else None

    def save_cache_name(self, class_id: str, cache_name: str) -> None:
        """Guarda el nombre del caché de Gemini para una clase."""
        path = self.clases_dir / class_id / "gemini_cache.txt"
        path.write_text(cache_name, encoding="utf-8")

    def delete_cache_name(self, class_id: str) -> None:
        """Elimina el archivo con el nombre del caché de Gemini."""
        path = self.clases_dir / class_id / "gemini_cache.txt"
        if path.exists():
            path.unlink()

    def delete_class(self, class_id: str) -> bool:
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

    # ──────────────────────────────────────────────────────────
    # Gestión de carpetas de organización
    # ──────────────────────────────────────────────────────────

    def get_folder_tree(self) -> list:
        """
        Devuelve lista plana de carpetas de organización (no clases)
        ordenadas por ruta.
        """
        folders = []
        if self.clases_dir.exists():
            self._scan_for_folders(self.clases_dir, "", folders)
        return sorted(folders, key=lambda x: x["path"])

    def _scan_for_folders(self, directory: Path, relative_path: str, folders: list) -> None:
        """Escanea directorios que NO son clases (no tienen transcripcion.jsonl)"""
        try:
            for item in sorted(directory.iterdir(), key=lambda p: p.name):
                if not item.is_dir():
                    continue
                # Si tiene archivos de clase, no es carpeta de organización
                if (item / "transcripcion.jsonl").exists() or (item / "resumen.md").exists():
                    continue
                item_rel = f"{relative_path}/{item.name}" if relative_path else item.name
                depth = item_rel.count("/")
                folders.append({
                    "path": item_rel,
                    "name": item.name,
                    "depth": depth
                })
                self._scan_for_folders(item, item_rel, folders)
        except OSError as e:
            logger.error(f"Error escaneando carpetas en {directory}: {e}")

    def create_folder(self, folder_path: str) -> dict:
        """
        Crea una carpeta de organización (no una clase).

        Args:
            folder_path: Ruta relativa, ej: "Matematicas" o "Matematicas/Calculo"
        """
        parts = folder_path.replace("\\", "/").split("/")
        safe_parts = [self._sanitize_folder_name(p) for p in parts if p.strip()]
        if not safe_parts:
            raise ValueError("Nombre de carpeta inválido")
        folder = self.clases_dir / "/".join(safe_parts)
        folder.mkdir(parents=True, exist_ok=True)
        rel_path = "/".join(safe_parts)
        logger.info(f"Carpeta de organización creada: {folder}")
        return {"path": rel_path, "name": safe_parts[-1], "depth": len(safe_parts) - 1}

    def rename_class(self, class_id: str, new_name: str) -> bool:
        """
        Guarda un nombre personalizado para una clase en nombre.txt.
        No mueve ni renombra la carpeta, preservando el ID y todos los archivos.
        """
        class_folder = self.clases_dir / class_id
        if not class_folder.exists() or not class_folder.is_dir():
            return False
        new_name = new_name.strip()
        if not new_name:
            return False
        (class_folder / "nombre.txt").write_text(new_name, encoding="utf-8")
        logger.info(f"Clase renombrada: {class_id} → {new_name}")
        return True

    # ──────────────────────────────────────────────────────────
    # Helpers internos
    # ──────────────────────────────────────────────────────────

    def _get_class_info(self, folder: Path, relative_path: str = None) -> Optional[dict]:
        """Construye el dict de información de una clase dado su folder y ruta relativa."""
        transcription_path = folder / "transcripcion.jsonl"
        summary_path = folder / "resumen.md"

        if not transcription_path.exists() and not summary_path.exists():
            return None

        created_at = datetime.fromtimestamp(folder.stat().st_mtime)

        segment_count = 0
        if transcription_path.exists():
            with open(transcription_path, "r", encoding="utf-8") as f:
                segment_count = sum(1 for line in f if line.strip())

        # Nombre para mostrar: parsear sufijo _YYYY-MM-DD_HH-MM si existe
        base_name = folder.name
        match = _DATE_SUFFIX_RE.match(base_name)
        if match:
            topic = match.group(1).replace("_", " ")
            date_part = match.group(2)   # YYYY-MM-DD
            time_part = match.group(3).replace("-", ":")  # HH:MM
            try:
                d = datetime.strptime(date_part, "%Y-%m-%d")
                display_name = f"{topic} · {d.strftime('%d/%m/%Y')} {time_part}"
            except ValueError:
                display_name = base_name.replace("_", " ")
        else:
            display_name = base_name.replace("_", " ")

        class_id = relative_path if relative_path else base_name
        folder_path = "/".join(class_id.split("/")[:-1]) if "/" in class_id else ""

        # Nombre personalizado si el usuario lo cambió
        custom_name_path = folder / "nombre.txt"
        if custom_name_path.exists():
            custom = custom_name_path.read_text(encoding="utf-8").strip()
            if custom:
                if match:
                    try:
                        d = datetime.strptime(match.group(2), "%Y-%m-%d")
                        time_part = match.group(3).replace("-", ":")
                        display_name = f"{custom} · {d.strftime('%d/%m/%Y')} {time_part}"
                    except ValueError:
                        display_name = custom
                else:
                    display_name = custom

        return {
            "id": class_id,
            "name": display_name,
            "folder_path": folder_path,
            "created_at": created_at.isoformat(),
            "created_at_formatted": created_at.strftime("%d/%m/%Y %H:%M"),
            "has_transcription": transcription_path.exists(),
            "has_summary": summary_path.exists(),
            "segment_count": segment_count,
            "path": str(folder)
        }

    @staticmethod
    def _sanitize_folder_name(name: str) -> str:
        """Sanitiza un nombre de carpeta (reemplaza espacios, guiones, caracteres especiales)"""
        name = name.replace(" ", "_").replace("-", "_")
        sanitized = "".join(c for c in name if c.isalnum() or c == "_")
        if len(sanitized) > 60:
            sanitized = sanitized[:60]
        return sanitized or "Clase_Sin_Nombre"

    @staticmethod
    def _sanitize_filename(filename: str) -> str:
        """Sanitiza un nombre de archivo y añade timestamp para evitar colisiones"""
        path = Path(filename)
        name = path.stem
        ext = path.suffix
        name = "".join(c for c in name if c.isalnum() or c in "._- ")
        name = name.replace(" ", "_")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return f"{name}_{timestamp}{ext}"
