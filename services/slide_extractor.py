"""
Servicio de extracción de contenido de slides en videos.

Flujo:
  1. ffmpeg detecta cambios de escena y extrae un frame por slide
  2. Filtros de eficiencia (sin llamadas API):
       a) Frame en blanco → descartado (sin coste)
       b) Frame duplicado del anterior → descartado (sin coste)
  3. Google Cloud Vision API (DOCUMENT_TEXT_DETECTION) extrae el texto
       - Los bloques de botones/UI de la interfaz son filtrados
  4. Si hay regiones sin texto (>13% del alto) → Gemini Vision describe el diagrama
  5. Devuelve lista estructurada de slides para enriquecer el resumen y el chat
"""

import base64
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from statistics import stdev
from typing import Optional

import requests
from PIL import Image, ImageStat

logger = logging.getLogger(__name__)

# ─── Parámetros de detección de escenas ─────────────────────────────────────
SCENE_THRESHOLD = 0.35      # Sensibilidad (0-1, menor = más sensible)
MAX_SLIDES = 60             # Máximo de slides a procesar por video
MAX_FRAME_WIDTH = 1280      # Reducir frames grandes para ahorrar ancho de banda

# ─── Eficiencia: blancos y duplicados ────────────────────────────────────────
BLANK_STD_THRESHOLD = 12    # Desviación estándar < 12 → frame en blanco
PHASH_DIFF_THRESHOLD = 8    # Bits distintos ≤ 8 → frame duplicado del anterior

# ─── Detección de diagramas ──────────────────────────────────────────────────
VISUAL_GAP_RATIO = 0.13     # Gap > 13% del alto → probable diagrama
MIN_GAP_PIXELS = 80

# ─── Filtro de botones / UI ──────────────────────────────────────────────────
# Texto corto común en controles de reproductor, barra de navegación, etc.
_UI_TEXT_RE = re.compile(
    r"^(skip\s*(intro|ad)?|next|prev(ious)?|back|play|pause|stop|resume|replay|"
    r"forward|rewind|mute|unmute|fullscreen|settings|subtitles?|captions?|"
    r"close|cancel|ok|yes|no|submit|send|upload|download|share|like|"
    r"subscribe|follow|login|logout|sign\s*in|sign\s*up|menu|home|search|"
    r"more|less|show|hide|view|exit|continue|start|begin|end|"
    r"►|▶|◀|⏸|⏹|⏺|⏭|⏮|\d+:\d+(:\d+)?|\d+%|cc)$",
    re.IGNORECASE,
)
# Fracción del alto de la imagen que se considera "zona de controles del reproductor"
UI_BOTTOM_ZONE = 0.10       # 10% inferior → zona de controles del video
UI_TOP_ZONE = 0.06          # 6% superior → barra de título del reproductor
UI_MAX_BLOCK_CHARS = 30     # Bloques muy cortos en zonas extremas = UI

# ─────────────────────────────────────────────────────────────────────────────
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class SlideExtractor:
    """
    Extrae y analiza slides de un video de clase de forma eficiente.

    Estrategia de coste:
      - Pillow (local, gratis): blancos y duplicados
      - Cloud Vision API (de pago): solo frames únicos con contenido
      - Gemini Vision (de pago): solo cuando se detectan diagramas
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

        logger.info("SlideExtractor inicializado (Cloud Vision + filtros locales)")

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

        Returns:
            Lista de dicts:
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

        # ── Filtros locales sin coste de API ──────────────────────────────
        frame_pairs = self._filter_blank_and_duplicates(frame_pairs)
        logger.info(f"{len(frame_pairs)} slides después de filtrar blancos/duplicados")

        if not frame_pairs:
            return []

        slides = []
        total = len(frame_pairs)

        for i, (frame_path, timestamp) in enumerate(frame_pairs, start=1):
            if progress_callback:
                progress_callback(i, total, f"Analizando slide {i}/{total}…")
            try:
                slide = self._analyze_frame(frame_path, i, timestamp)
                slides.append(slide)
                icon = "📊" if slide["has_visual"] else "📝"
                logger.info(
                    f"  Slide {i}/{total} {icon}  "
                    f"texto={len(slide['text'])} chars  ts={timestamp:.1f}s"
                )
            except Exception as e:
                logger.error(f"Error en slide {i}: {e}")
                slides.append(
                    dict(frame_num=i, timestamp=timestamp,
                         text="", visual_description="", has_visual=False)
                )

        self._cleanup_frames(frames_dir)
        return slides

    def format_slides_for_context(self, slides: list[dict]) -> str:
        """
        Convierte la lista de slides a texto Markdown para el contexto de
        resumen y chat. Solo incluye slides con contenido real.
        """
        useful = [s for s in slides if s.get("text") or s.get("visual_description")]
        if not useful:
            return ""

        lines = ["\n\n---\n## CONTENIDO DE SLIDES DE LA PRESENTACIÓN\n"]
        for slide in useful:
            mm, ss = divmod(int(slide.get("timestamp", 0)), 60)
            lines.append(f"\n### Slide {slide['frame_num']} [{mm:02d}:{ss:02d}]")
            if slide.get("text"):
                lines.append(slide["text"])
            if slide.get("visual_description"):
                lines.append(f"\n*[Elemento visual: {slide['visual_description']}]*")

        return "\n".join(lines)

    def format_slides_for_download(self, slides: list[dict], class_name: str) -> str:
        """
        Genera Markdown completo y enriquecido para descargar y usar con otra IA.
        Incluye metadatos, contexto y formato limpio optimizado para LLMs.
        """
        from datetime import datetime
        useful = [s for s in slides if s.get("text") or s.get("visual_description")]
        total_text = sum(len(s.get("text", "")) for s in useful)
        total_visual = sum(1 for s in useful if s.get("has_visual"))

        lines = [
            f"# Slides: {class_name.replace('_', ' ')}",
            f"\n> Generado por V_T_R · {datetime.now().strftime('%d/%m/%Y %H:%M')}",
            f"> Total slides con contenido: **{len(useful)}** "
            f"| Con diagramas: **{total_visual}** "
            f"| Texto total: **{total_text} caracteres**",
            "\n---\n",
        ]

        if not useful:
            lines.append("*No se detectó contenido en los slides del video.*")
            return "\n".join(lines)

        for slide in useful:
            mm, ss = divmod(int(slide.get("timestamp", 0)), 60)
            lines.append(f"## Slide {slide['frame_num']} · [{mm:02d}:{ss:02d}]")

            if slide.get("text"):
                lines.append("\n**Texto en pantalla:**\n")
                lines.append(slide["text"])

            if slide.get("visual_description"):
                lines.append("\n**Elemento visual detectado:**\n")
                lines.append(f"> {slide['visual_description']}")

            lines.append("\n---\n")

        return "\n".join(lines)

    # ─────────────────────────────────────────────────────────────────────────
    # Filtros locales (sin coste de API)
    # ─────────────────────────────────────────────────────────────────────────

    def _filter_blank_and_duplicates(
        self, frame_pairs: list[tuple[str, float]]
    ) -> list[tuple[str, float]]:
        """
        Descarta frames en blanco y frames demasiado similares al anterior.
        Opera completamente en local con Pillow. Sin coste de API.
        """
        kept = []
        prev_hash = None
        blanks = dupes = 0

        for frame_path, timestamp in frame_pairs:
            # 1. Detectar blancos
            if self._is_blank(frame_path):
                blanks += 1
                logger.debug(f"Frame en blanco descartado: {frame_path}")
                continue

            # 2. Detectar duplicados vs frame anterior
            h = self._phash(frame_path)
            if prev_hash is not None and self._hash_distance(h, prev_hash) <= PHASH_DIFF_THRESHOLD:
                dupes += 1
                logger.debug(f"Frame duplicado descartado: {frame_path}")
                continue

            prev_hash = h
            kept.append((frame_path, timestamp))

        if blanks or dupes:
            logger.info(f"Filtros locales: {blanks} blancos + {dupes} duplicados descartados")
        return kept

    def _is_blank(self, image_path: str) -> bool:
        """Devuelve True si el frame es casi enteramente de un solo color."""
        try:
            with Image.open(image_path) as img:
                gray = img.convert("L").resize((64, 64))
                pixels = list(gray.getdata())
                return stdev(pixels) < BLANK_STD_THRESHOLD
        except Exception:
            return False

    def _phash(self, image_path: str) -> int:
        """Calcula un hash perceptual simple de 64 bits para detectar duplicados."""
        try:
            with Image.open(image_path) as img:
                small = img.resize((8, 8)).convert("L")
                pixels = list(small.getdata())
                avg = sum(pixels) / len(pixels)
                return sum(1 << i for i, p in enumerate(pixels) if p >= avg)
        except Exception:
            return 0

    @staticmethod
    def _hash_distance(a: int, b: int) -> int:
        """Distancia de Hamming entre dos hashes."""
        return bin(a ^ b).count("1")

    # ─────────────────────────────────────────────────────────────────────────
    # Extracción de frames con ffmpeg
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_keyframes(self, video_path: Path, frames_dir: Path) -> list[tuple[str, float]]:
        """
        Usa ffmpeg para extraer un frame por cada cambio de escena.
        Retorna lista de (ruta_frame, timestamp_segundos).
        """
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
            logger.info("Sin cambios de escena, muestreo cada 30s como fallback")
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

        timestamps = self._get_scene_timestamps(video_path)

        if len(frame_files) > MAX_SLIDES:
            step = len(frame_files) / MAX_SLIDES
            frame_files = [frame_files[int(i * step)] for i in range(MAX_SLIDES)]

        pairs = []
        for i, fp in enumerate(frame_files):
            ts = timestamps[i] if i < len(timestamps) else float(i * 30)
            pairs.append((str(fp), ts))

        return pairs

    def _get_scene_timestamps(self, video_path: Path) -> list[float]:
        cmd = [
            "ffprobe", "-v", "quiet", "-select_streams", "v:0",
            "-show_frames", "-show_entries", "frame=pkt_pts_time",
            "-vf", f"select='gt(scene,{SCENE_THRESHOLD})'",
            "-of", "csv=p=0", str(video_path),
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
            logger.warning(f"No se pudieron obtener timestamps: {e}")
        return timestamps

    def _run_ffmpeg(self, cmd: list, timeout: int = 600) -> None:
        result = subprocess.run(
            cmd, capture_output=True, text=True,
            timeout=timeout, creationflags=_SUBPROCESS_FLAGS
        )
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg error: {result.stderr[-500:]}")

    # ─────────────────────────────────────────────────────────────────────────
    # Análisis individual de un frame
    # ─────────────────────────────────────────────────────────────────────────

    def _analyze_frame(self, frame_path: str, frame_num: int, timestamp: float) -> dict:
        """
        1. Cloud Vision → texto (filtrando UI)
        2. Si hay regiones sin texto → Gemini Vision describe el diagrama
        """
        img_w, img_h = self._get_image_size(frame_path)

        vision_resp = self._call_vision_api(frame_path)
        text, text_blocks = self._parse_vision_response(vision_resp, img_h)

        has_visual = False
        visual_description = ""

        if self._gemini_model:
            visual_regions = self._detect_visual_regions(text_blocks, img_h)
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

    def _parse_vision_response(
        self, response: dict, img_height: int = 720
    ) -> tuple[str, list[dict]]:
        """
        Parsea la respuesta de Vision API filtrando bloques de UI/botones.
        Retorna (texto_limpio, lista_de_bounding_boxes).
        """
        if not response or "responses" not in response:
            return "", []

        result = response["responses"][0]
        if "error" in result:
            logger.warning(f"Vision API error: {result['error'].get('message', '')}")
            return "", []

        annotation = result.get("fullTextAnnotation", {})

        # Recopilar bloques con su texto y posición para poder filtrar UI
        raw_blocks = []
        for page in annotation.get("pages", []):
            for block in page.get("blocks", []):
                vertices = block.get("boundingBox", {}).get("vertices", [])
                if len(vertices) < 4:
                    continue
                ys = [v.get("y", 0) for v in vertices]
                xs = [v.get("x", 0) for v in vertices]
                # Extraer texto del bloque concatenando párrafos/palabras
                block_text = self._block_text(block)
                raw_blocks.append(dict(
                    y1=min(ys), y2=max(ys), x1=min(xs), x2=max(xs),
                    text=block_text,
                ))

        # Filtrar botones / elementos de UI
        content_blocks = [
            b for b in raw_blocks
            if not self._is_ui_block(b, img_height)
        ]

        text_blocks = [
            dict(y1=b["y1"], y2=b["y2"], x1=b["x1"], x2=b["x2"])
            for b in content_blocks
        ]
        clean_text = "\n".join(b["text"] for b in content_blocks if b["text"]).strip()

        return clean_text, text_blocks

    @staticmethod
    def _block_text(block: dict) -> str:
        """Extrae el texto concatenado de un bloque de Vision API."""
        parts = []
        for para in block.get("paragraphs", []):
            for word in para.get("words", []):
                word_str = "".join(
                    s.get("text", "") for s in word.get("symbols", [])
                )
                parts.append(word_str)
        return " ".join(parts)

    def _is_ui_block(self, block: dict, img_height: int) -> bool:
        """
        Determina si un bloque de texto es un elemento de interfaz de usuario
        (botón, control del reproductor, barra de navegación, watermark, etc.)
        """
        text = block["text"].strip()
        y1 = block["y1"]
        y2 = block["y2"]

        if not text:
            return True  # bloque vacío

        # Zona inferior (controles del reproductor de video)
        if y1 > img_height * (1 - UI_BOTTOM_ZONE):
            return True

        # Zona superior (barra de título del reproductor)
        if y2 < img_height * UI_TOP_ZONE:
            return True

        # Texto muy corto en zonas extremas = botón / icono
        if len(text) <= UI_MAX_BLOCK_CHARS:
            in_edge = (y1 < img_height * 0.08) or (y1 > img_height * 0.88)
            if in_edge and _UI_TEXT_RE.match(text):
                return True

        return False

    # ─────────────────────────────────────────────────────────────────────────
    # Detección de regiones visuales (diagramas)
    # ─────────────────────────────────────────────────────────────────────────

    def _get_image_size(self, image_path: str) -> tuple[int, int]:
        try:
            with Image.open(image_path) as img:
                return img.size  # (width, height)
        except Exception:
            return 1280, 720

    def _get_image_height(self, image_path: str) -> int:
        return self._get_image_size(image_path)[1]

    def _detect_visual_regions(self, text_blocks: list[dict], img_height: int) -> list[dict]:
        """Detecta huecos grandes entre bloques de texto → posibles diagramas."""
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
                "diagramas, gráficas, fórmulas matemáticas, tablas, esquemas, figuras. "
                "Ignora botones de interfaz, controles del reproductor y elementos de navegación. "
                "Si no hay elementos visuales académicos, responde exactamente: Sin elementos visuales.\n"
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
