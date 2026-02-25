"""
Servicio de extracción de contenido de slides en videos.

Flujo:
  1. ffmpeg detecta cambios de escena y extrae un frame por slide
  2. Google Cloud Vision API (DOCUMENT_TEXT_DETECTION) extrae el texto
  3. Si hay regiones sin texto (>15% del alto) → Gemini Vision describe el diagrama
  4. Devuelve lista estructurada de slides para enriquecer el resumen y el chat
"""

import base64
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)

# ─── Parámetros de detección ────────────────────────────────────────────────
SCENE_THRESHOLD = 0.35      # Sensibilidad de cambio de escena (0-1, menor = más sensible)
MAX_SLIDES = 60             # Máximo de slides a procesar por video
VISUAL_GAP_RATIO = 0.13     # Gap > 13% del alto de imagen → probable diagrama
MIN_GAP_PIXELS = 80         # Gap mínimo en píxeles para considerar región visual
MAX_FRAME_WIDTH = 1280      # Reducir frames grandes para ahorrar ancho de banda
# ────────────────────────────────────────────────────────────────────────────

_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class SlideExtractor:
    """
    Extrae y analiza slides de un video de clase.

    - Cloud Vision API → texto estructurado de cada slide
    - Gemini Vision    → descripción de diagramas/figuras cuando se detectan
    """

    def __init__(self, vision_api_key: str, gemini_api_key: Optional[str] = None):
        if not vision_api_key:
            raise ValueError("Se requiere GOOGLE_VISION_API_KEY para SlideExtractor")

        self.vision_api_key = vision_api_key
        self._gemini_model = None

        if gemini_api_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=gemini_api_key)
                self._gemini_model = genai.GenerativeModel("gemini-2.0-flash")
                logger.info("SlideExtractor: Gemini Vision disponible para diagramas")
            except Exception as e:
                logger.warning(f"SlideExtractor: Gemini Vision no disponible: {e}")

        logger.info("SlideExtractor inicializado con Cloud Vision API")

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def extract_slides(
        self,
        video_path: str,
        temp_dir: str,
        progress_callback=None,
    ) -> list[dict]:
        """
        Extrae y analiza todos los slides del video.

        Args:
            video_path:        Ruta al archivo de video.
            temp_dir:          Directorio temporal para los frames extraídos.
            progress_callback: Callable(current, total, message) opcional.

        Returns:
            Lista de dicts con keys:
                frame_num (int), timestamp (float), text (str),
                visual_description (str), has_visual (bool)
        """
        video_path = Path(video_path)
        frames_dir = Path(temp_dir) / "slide_frames"
        frames_dir.mkdir(exist_ok=True)

        try:
            frame_pairs = self._extract_keyframes(video_path, frames_dir)
        except Exception as e:
            logger.error(f"Error extrayendo keyframes: {e}")
            return []

        if not frame_pairs:
            logger.warning("No se detectaron cambios de escena significativos")
            return []

        logger.info(f"{len(frame_pairs)} slides detectados en el video")
        slides = []

        for i, (frame_path, timestamp) in enumerate(frame_pairs, start=1):
            if progress_callback:
                progress_callback(i, len(frame_pairs), f"Analizando slide {i}/{len(frame_pairs)}…")
            try:
                slide = self._analyze_frame(frame_path, i, timestamp)
                slides.append(slide)
                status = "📊" if slide["has_visual"] else "📝"
                logger.info(
                    f"Slide {i}/{len(frame_pairs)} {status}  "
                    f"texto={len(slide['text'])} chars  "
                    f"ts={timestamp:.1f}s"
                )
            except Exception as e:
                logger.error(f"Error en slide {i}: {e}")
                slides.append(
                    dict(frame_num=i, timestamp=timestamp, text="", visual_description="", has_visual=False)
                )

        self._cleanup_frames(frames_dir)
        return slides

    def format_slides_for_context(self, slides: list[dict]) -> str:
        """
        Convierte la lista de slides a texto Markdown para incluir en el
        contexto del resumen y del chat.
        """
        if not slides:
            return ""

        useful = [s for s in slides if s.get("text") or s.get("visual_description")]
        if not useful:
            return ""

        lines = ["\n\n---\n## CONTENIDO DE SLIDES DE LA PRESENTACIÓN\n"]
        for slide in useful:
            ts = slide.get("timestamp", 0)
            mm, ss = divmod(int(ts), 60)
            lines.append(f"\n### Slide {slide['frame_num']} [{mm:02d}:{ss:02d}]")
            if slide.get("text"):
                lines.append(slide["text"])
            if slide.get("visual_description"):
                lines.append(f"\n*[Elemento visual: {slide['visual_description']}]*")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # Extracción de frames con ffmpeg
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_keyframes(self, video_path: Path, frames_dir: Path) -> list[tuple[str, float]]:
        """
        Usa ffmpeg para extraer un frame por cada cambio de escena.
        Retorna lista de (ruta_frame, timestamp_segundos).
        """
        # Extraer frames en cambios de escena
        cmd_extract = [
            "ffmpeg", "-i", str(video_path),
            "-vf", (
                f"select='gt(scene,{SCENE_THRESHOLD})',"
                f"scale='if(gt(iw,{MAX_FRAME_WIDTH}),{MAX_FRAME_WIDTH},-2)':-2"
            ),
            "-vsync", "vfr",
            "-q:v", "3",
            str(frames_dir / "frame_%05d.jpg"),
            "-y",
        ]
        self._run_ffmpeg(cmd_extract, timeout=600)

        frame_files = sorted(frames_dir.glob("frame_*.jpg"))
        if not frame_files:
            # Fallback: un frame cada 30 segundos si no se detectan escenas
            logger.info("Sin cambios de escena detectados, usando muestreo cada 30s")
            cmd_fallback = [
                "ffmpeg", "-i", str(video_path),
                "-vf", (
                    f"fps=1/30,"
                    f"scale='if(gt(iw,{MAX_FRAME_WIDTH}),{MAX_FRAME_WIDTH},-2)':-2"
                ),
                "-q:v", "3",
                str(frames_dir / "frame_%05d.jpg"),
                "-y",
            ]
            self._run_ffmpeg(cmd_fallback, timeout=600)
            frame_files = sorted(frames_dir.glob("frame_*.jpg"))

        # Obtener timestamps de los frames con ffprobe
        timestamps = self._get_scene_timestamps(video_path)

        # Limitar al máximo configurado
        if len(frame_files) > MAX_SLIDES:
            step = len(frame_files) / MAX_SLIDES
            frame_files = [frame_files[int(i * step)] for i in range(MAX_SLIDES)]

        pairs = []
        for i, fp in enumerate(frame_files):
            ts = timestamps[i] if i < len(timestamps) else float(i * 30)
            pairs.append((str(fp), ts))

        return pairs

    def _get_scene_timestamps(self, video_path: Path) -> list[float]:
        """Usa ffprobe para obtener los timestamps de los frames con cambios de escena."""
        cmd = [
            "ffprobe",
            "-v", "quiet",
            "-select_streams", "v:0",
            "-show_frames",
            "-show_entries", "frame=pkt_pts_time",
            "-vf", f"select='gt(scene,{SCENE_THRESHOLD})'",
            "-of", "csv=p=0",
            str(video_path),
        ]
        timestamps = []
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=300, creationflags=_SUBPROCESS_FLAGS
            )
            for line in result.stdout.strip().splitlines():
                line = line.strip()
                if line and line not in ("N/A", ""):
                    try:
                        timestamps.append(float(line))
                    except ValueError:
                        pass
        except Exception as e:
            logger.warning(f"No se pudieron obtener timestamps de escenas: {e}")
        return timestamps

    def _run_ffmpeg(self, cmd: list, timeout: int = 600) -> None:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, creationflags=_SUBPROCESS_FLAGS
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {result.stderr[-500:]}")

    # ─────────────────────────────────────────────────────────────────────────
    # Análisis de un frame individual
    # ─────────────────────────────────────────────────────────────────────────

    def _analyze_frame(self, frame_path: str, frame_num: int, timestamp: float) -> dict:
        """Extrae texto con Cloud Vision y, si hay diagramas, los describe con Gemini."""
        vision_resp = self._call_vision_api(frame_path)
        text, text_blocks = self._parse_vision_response(vision_resp)

        has_visual = False
        visual_description = ""

        if self._gemini_model:
            img_height = self._get_image_height(frame_path)
            visual_regions = self._detect_visual_regions(text_blocks, img_height)
            if visual_regions:
                has_visual = True
                visual_description = self._describe_with_gemini(frame_path, text)

        return dict(
            frame_num=frame_num,
            timestamp=timestamp,
            text=text.strip(),
            visual_description=visual_description,
            has_visual=has_visual,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Google Cloud Vision API
    # ─────────────────────────────────────────────────────────────────────────

    def _call_vision_api(self, image_path: str, max_retries: int = 3) -> dict:
        """Llama a Cloud Vision REST API con reintentos exponenciales."""
        url = f"https://vision.googleapis.com/v1/images:annotate?key={self.vision_api_key}"

        with open(image_path, "rb") as fh:
            content = base64.b64encode(fh.read()).decode("utf-8")

        payload = {
            "requests": [{
                "image": {"content": content},
                "features": [{"type": "DOCUMENT_TEXT_DETECTION"}],
            }]
        }

        for attempt in range(max_retries):
            try:
                resp = requests.post(url, json=payload, timeout=30)
                if resp.status_code == 403:
                    raise RuntimeError("Cloud Vision API key inválida o sin permisos (HTTP 403)")
                if resp.status_code in (429, 500, 502, 503):
                    wait = (2 ** attempt) * 2
                    logger.warning(f"Vision API HTTP {resp.status_code}, reintento en {wait}s")
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                return resp.json()
            except requests.RequestException as exc:
                if attempt == max_retries - 1:
                    raise RuntimeError(f"Error en Cloud Vision API: {exc}") from exc
                time.sleep(2 ** attempt)

        return {}

    def _parse_vision_response(self, response: dict) -> tuple[str, list[dict]]:
        """
        Parsea la respuesta de Vision API.
        Retorna (texto_completo, lista_de_bounding_boxes).
        """
        if not response or "responses" not in response:
            return "", []

        result = response["responses"][0]

        if "error" in result:
            logger.warning(f"Vision API error en respuesta: {result['error'].get('message', '')}")
            return "", []

        annotation = result.get("fullTextAnnotation", {})
        full_text = annotation.get("text", "")

        text_blocks = []
        for page in annotation.get("pages", []):
            for block in page.get("blocks", []):
                vertices = block.get("boundingBox", {}).get("vertices", [])
                if len(vertices) >= 4:
                    ys = [v.get("y", 0) for v in vertices]
                    xs = [v.get("x", 0) for v in vertices]
                    text_blocks.append(
                        dict(y1=min(ys), y2=max(ys), x1=min(xs), x2=max(xs))
                    )

        return full_text, text_blocks

    # ─────────────────────────────────────────────────────────────────────────
    # Detección de regiones visuales (diagramas)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_image_height(self, image_path: str) -> int:
        try:
            with Image.open(image_path) as img:
                return img.size[1]
        except Exception:
            return 720  # fallback HD

    def _detect_visual_regions(self, text_blocks: list[dict], img_height: int) -> list[dict]:
        """
        Detecta huecos grandes entre bloques de texto → posibles diagramas o imágenes.
        Retorna lista de regiones {y1, y2}.
        """
        if not text_blocks:
            return []

        sorted_blocks = sorted(text_blocks, key=lambda b: b["y1"])
        visual_regions = []
        prev_bottom = 0

        for block in sorted_blocks:
            gap = block["y1"] - prev_bottom
            if gap > img_height * VISUAL_GAP_RATIO and gap > MIN_GAP_PIXELS:
                visual_regions.append(dict(y1=prev_bottom, y2=block["y1"]))
            prev_bottom = max(prev_bottom, block["y2"])

        # Hueco al final de la imagen
        final_gap = img_height - prev_bottom
        if final_gap > img_height * VISUAL_GAP_RATIO and final_gap > MIN_GAP_PIXELS:
            visual_regions.append(dict(y1=prev_bottom, y2=img_height))

        return visual_regions

    # ─────────────────────────────────────────────────────────────────────────
    # Gemini Vision para diagramas
    # ─────────────────────────────────────────────────────────────────────────

    def _describe_with_gemini(self, image_path: str, existing_text: str) -> str:
        """Usa Gemini Vision para describir el contenido visual del slide."""
        try:
            img = Image.open(image_path)
            text_ctx = (
                f"El texto visible en el slide es: «{existing_text[:400].strip()}»"
                if existing_text.strip()
                else "El slide no contiene texto significativo."
            )
            prompt = (
                f"Analiza este slide de una clase universitaria.\n{text_ctx}\n\n"
                "Describe ÚNICAMENTE los elementos visuales no textuales: "
                "diagramas, gráficas, fórmulas matemáticas, tablas, esquemas, imágenes o figuras. "
                "Si no hay elementos visuales relevantes, responde exactamente: Sin elementos visuales.\n"
                "Sé conciso y técnico. Máximo 120 palabras."
            )
            response = self._gemini_model.generate_content([prompt, img])
            description = response.text.strip()
            if "Sin elementos visuales" in description:
                return ""
            return description
        except Exception as e:
            logger.warning(f"Gemini Vision no pudo describir el slide: {e}")
            return ""

    # ─────────────────────────────────────────────────────────────────────────
    # Limpieza
    # ─────────────────────────────────────────────────────────────────────────

    def _cleanup_frames(self, frames_dir: Path) -> None:
        try:
            for fp in frames_dir.glob("frame_*.jpg"):
                fp.unlink(missing_ok=True)
            frames_dir.rmdir()
        except Exception as e:
            logger.warning(f"No se pudo limpiar frames temporales: {e}")
