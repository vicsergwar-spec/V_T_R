"""
Servicio de extracción de contenido de slides en videos.

Flujo:
  1. ffmpeg detecta cambios de escena y extrae un frame por slide
     - Umbral bajo (0.15) + fallback cada 30s garantizan cobertura mínima
  2. Filtros de eficiencia (sin llamadas API):
       a) Frame en blanco → descartado (sin coste)
       b) Frame duplicado del anterior → descartado (sin coste)
  3. Recorte automático de bordes negros/blancos con OpenCV
  4. Gemini Vision analiza cada frame:
       - Extrae todo el texto visible
       - Describe diagramas o figuras si los hay
       - Descarta frames con solo rostro humano (respuesta SKIP)
  5. Devuelve lista estructurada de slides para enriquecer el resumen y el chat
"""

import logging
import os
import subprocess
import time
from pathlib import Path
from statistics import stdev

from PIL import Image

logger = logging.getLogger(__name__)

# ─── Parámetros de detección de escenas ─────────────────────────────────────
SCENE_THRESHOLD = 0.15      # Sensibilidad (0-1, menor = más sensible)
MIN_FRAME_INTERVAL_S = 30   # Garantizar al menos 1 frame cada 30s
MAX_SLIDES = 80             # Máximo de slides a procesar por video
MAX_FRAME_WIDTH = 1280      # Reducir frames grandes para ahorrar ancho de banda

# ─── Eficiencia: blancos y duplicados ────────────────────────────────────────
BLANK_STD_THRESHOLD = 12    # Desviación estándar < 12 → frame en blanco
PHASH_DIFF_THRESHOLD = 8    # Bits distintos ≤ 8 → frame duplicado del anterior

# ─────────────────────────────────────────────────────────────────────────────
_SUBPROCESS_FLAGS = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0


class SlideExtractor:
    """
    Extrae y analiza slides de un video de clase.

    Estrategia:
      - Pillow (local, gratis): filtro de blancos y duplicados
      - Gemini Vision: OCR + descripción visual + filtro de rostros
    """

    def __init__(
        self,
        gemini_api_key: str,
        gemini_model: str = "gemini-2.5-flash",
    ):
        if not gemini_api_key:
            raise ValueError("Se requiere GEMINI_API_KEY para SlideExtractor")

        import google.generativeai as genai
        genai.configure(api_key=gemini_api_key)
        self._gemini_model = genai.GenerativeModel(gemini_model)
        logger.info(f"SlideExtractor inicializado (Gemini Vision: {gemini_model})")

    # ─────────────────────────────────────────────────────────────────────────
    # API pública
    # ─────────────────────────────────────────────────────────────────────────

    def extract_slides(
        self,
        video_path: str,
        temp_dir: str,
        progress_callback=None,
        persist_dir: str = None,
    ) -> list[dict]:
        """
        Extrae y analiza todos los slides del video.

        Args:
            video_path: Ruta al video
            temp_dir: Directorio temporal para frames
            progress_callback: Callback(current, total, msg)
            persist_dir: Si se indica, guarda las imágenes en esta carpeta

        Returns:
            Lista de dicts:
                frame_num (int), timestamp (float), text (str),
                visual_description (str), has_visual (bool),
                image_file (str) — nombre del archivo guardado (si persist_dir)
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

        logger.info(f"[I] Frames capturados por ffmpeg: {len(frame_pairs)}")

        # ── Filtros locales sin coste de API ──────────────────────────────
        frame_pairs = self._filter_blank_and_duplicates(frame_pairs)
        logger.info(f"[I] {len(frame_pairs)} slides después de filtrar blancos/duplicados")

        if not frame_pairs:
            return []

        # ── Recortar bordes negros/blancos con OpenCV ─────────────────────
        frame_pairs = self._autocrop_frames(frame_pairs)

        # Preparar directorio de imágenes persistentes
        images_dir = None
        if persist_dir:
            images_dir = Path(persist_dir) / "slide_images"
            images_dir.mkdir(exist_ok=True)

        slides = []
        total = len(frame_pairs)
        skipped = 0

        for i, (frame_path, timestamp) in enumerate(frame_pairs, start=1):
            if progress_callback:
                progress_callback(i, total, f"Analizando slide {i}/{total}…")
            try:
                slide = self._analyze_frame(frame_path, i, timestamp)

                # Gemini respondió SKIP → frame con solo rostro, descartar
                if slide is None:
                    skipped += 1
                    logger.debug(f"Frame {i} descartado: solo rostro (SKIP)")
                    continue

                # Persistir imagen en carpeta de la clase
                image_filename = ""
                if images_dir:
                    dest_name = f"slide_{i:03d}.png"
                    dest_path = images_dir / dest_name
                    with Image.open(frame_path) as img:
                        img.save(str(dest_path), "PNG", compress_level=1)
                    image_filename = f"slide_images/{dest_name}"

                    # Detectar sub-imágenes dentro del frame
                    sub_images = self._extract_sub_images(frame_path, i, images_dir)
                    if sub_images:
                        slide["sub_images"] = sub_images
                        logger.info(f"  Slide {i}: {len(sub_images)} sub-imagen(es) detectada(s)")

                slide["image_file"] = image_filename
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
                         text="", visual_description="", has_visual=False,
                         image_file="")
                )

        logger.info(f"[I] Frames descartados (solo rostro / SKIP): {skipped}")
        logger.info(f"[I] Slides finales con contenido: {len(slides)}")

        self._cleanup_frames(frames_dir)
        return slides

    def format_slides_for_context(self, slides: list[dict]) -> str:
        """
        Convierte la lista de slides a texto Markdown optimizado para IA.
        Solo texto académico, sin referencias a imágenes ni rutas de archivo.
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
            for sub in slide.get("sub_images", []):
                if sub.get("description"):
                    lines.append(f"\n*[Sub-imagen: {sub['description']}]*")

        return "\n".join(lines)

    def format_slides_for_storage(self, slides: list[dict]) -> str:
        """
        Genera Markdown para el frontend (pestaña 'Presentación') y PDF.
        Incluye referencias a imágenes para visualización.

        Formato: secciones ## Slide N [MM:SS] separadas por líneas ---
        Compatible con parseSlidesMarkdown() en app.js.
        """
        useful = [s for s in slides if s.get("text") or s.get("visual_description")]
        if not useful:
            return ""

        parts = []
        for slide in useful:
            mm, ss = divmod(int(slide.get("timestamp", 0)), 60)
            section_lines = [f"## Slide {slide['frame_num']} [{mm:02d}:{ss:02d}]"]
            if slide.get("image_file"):
                section_lines.append(f"![Slide {slide['frame_num']}]({slide['image_file']})")
            if slide.get("text"):
                section_lines.append(slide["text"])
            if slide.get("visual_description"):
                section_lines.append(f"> {slide['visual_description']}")
            for sub in slide.get("sub_images", []):
                if sub.get("file"):
                    section_lines.append(f"![Sub-imagen]({sub['file']})")
                if sub.get("description"):
                    section_lines.append(f"> Sub-imagen: {sub['description']}")
            parts.append("\n".join(section_lines))

        return "\n---\n".join(parts)

    # ─────────────────────────────────────────────────────────────────────────
    # Gemini Vision con reintentos
    # ─────────────────────────────────────────────────────────────────────────

    def _call_gemini_with_retry(self, content_parts: list, max_retries: int = 5) -> str:
        """Llama a Gemini Vision con reintentos exponenciales (2s, 4s, 8s, 16s, 32s)."""
        for attempt in range(max_retries):
            try:
                response = self._gemini_model.generate_content(content_parts)
                return response.text.strip()
            except Exception as e:
                if attempt == max_retries - 1:
                    raise
                wait = 2 ** (attempt + 1)
                logger.warning(f"Gemini Vision reintento {attempt+1}/{max_retries} en {wait}s: {e}")
                time.sleep(wait)
        return ""

    # ─────────────────────────────────────────────────────────────────────────
    # Análisis individual de un frame (Gemini Vision unificado)
    # ─────────────────────────────────────────────────────────────────────────

    def _analyze_frame(self, frame_path: str, frame_num: int, timestamp: float) -> dict | None:
        """
        Envía el frame a Gemini Vision para extraer texto y detectar elementos
        visuales. Si la respuesta es SKIP, retorna None (frame sin contenido).
        """
        prompt = (
            "Analiza esta imagen de un video de clase universitaria.\n\n"
            "1. Extrae TODO el texto visible en la imagen, preservando la estructura "
            "(títulos, viñetas, párrafos, tablas, fórmulas).\n"
            "2. Si contiene diagramas, gráficas, esquemas, figuras o fórmulas, "
            "descríbelos brevemente después del texto, en una línea que empiece con "
            "'> VISUAL: '.\n"
            "3. Ignora completamente botones de interfaz, controles del reproductor, "
            "barras de navegación, watermarks y elementos de UI del campus virtual.\n"
            "4. Si la imagen muestra SOLO un rostro humano (profesor/presentador) "
            "sin texto, diagramas ni contenido académico visible, responde "
            "exactamente: SKIP\n\n"
            "Responde SOLO con el contenido extraído (texto + descripción visual si aplica) "
            "o SKIP. Sin explicaciones adicionales."
        )

        with Image.open(frame_path) as img:
            answer = self._call_gemini_with_retry([prompt, img.copy()])

        # Frame con solo rostro → descartar
        if answer.strip().upper() == "SKIP":
            return None

        # Separar texto de descripción visual
        text_lines = []
        visual_lines = []
        for line in answer.split("\n"):
            stripped = line.strip()
            if stripped.lower().startswith("> visual:"):
                visual_lines.append(stripped[len("> visual:"):].strip())
            elif stripped.startswith("> VISUAL:"):
                visual_lines.append(stripped[len("> VISUAL:"):].strip())
            else:
                text_lines.append(line)

        text = "\n".join(text_lines).strip()
        visual_description = " ".join(visual_lines).strip()
        has_visual = bool(visual_description)

        return dict(
            frame_num=frame_num,
            timestamp=timestamp,
            text=text,
            visual_description=visual_description,
            has_visual=has_visual,
        )

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
            if self._is_blank(frame_path):
                blanks += 1
                logger.debug(f"Frame en blanco descartado: {frame_path}")
                continue

            h = self._phash(frame_path)
            if prev_hash is not None and self._hash_distance(h, prev_hash) <= PHASH_DIFF_THRESHOLD:
                dupes += 1
                logger.debug(f"Frame duplicado descartado: {frame_path}")
                continue

            prev_hash = h
            kept.append((frame_path, timestamp))

        if blanks or dupes:
            logger.info(f"[I] Filtros locales: {blanks} blancos + {dupes} duplicados descartados")
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
    # Recorte automático de bordes negros/blancos
    # ─────────────────────────────────────────────────────────────────────────

    def _autocrop_frames(
        self, frame_pairs: list[tuple[str, float]]
    ) -> list[tuple[str, float]]:
        """
        Recorta bordes negros/blancos de cada frame usando OpenCV.
        Sobrescribe el archivo original con la versión recortada.
        """
        try:
            import cv2
            import numpy as np
        except ImportError:
            logger.warning("OpenCV no disponible, omitiendo autocrop de bordes")
            return frame_pairs

        result = []
        for frame_path, timestamp in frame_pairs:
            try:
                img = cv2.imread(frame_path)
                if img is None:
                    result.append((frame_path, timestamp))
                    continue

                h, w = img.shape[:2]
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

                mask_not_black = gray > 15
                mask_not_white = gray < 240
                mask = (mask_not_black & mask_not_white).astype(np.uint8) * 255

                if cv2.countNonZero(mask) < (h * w * 0.05):
                    result.append((frame_path, timestamp))
                    continue

                coords = cv2.findNonZero(mask)
                x, y, rw, rh = cv2.boundingRect(coords)

                margin_x = w * 0.03
                margin_y = h * 0.03
                if x > margin_x or y > margin_y or (w - x - rw) > margin_x or (h - y - rh) > margin_y:
                    pad = 2
                    x = max(0, x - pad)
                    y = max(0, y - pad)
                    rw = min(w - x, rw + 2 * pad)
                    rh = min(h - y, rh + 2 * pad)

                    cropped = img[y:y+rh, x:x+rw]
                    crop_h, crop_w = cropped.shape[:2]
                    scale = min(w / crop_w, h / crop_h)
                    new_w = int(crop_w * scale)
                    new_h = int(crop_h * scale)
                    resized = cv2.resize(cropped, (new_w, new_h), interpolation=cv2.INTER_LANCZOS4)

                    cv2.imwrite(frame_path, resized)
                    logger.debug(f"Autocrop: {Path(frame_path).name} {w}x{h} → {new_w}x{new_h}")

                result.append((frame_path, timestamp))
            except Exception as e:
                logger.warning(f"Error en autocrop de {frame_path}: {e}")
                result.append((frame_path, timestamp))

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Extracción de frames con ffmpeg
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_keyframes(self, video_path: Path, frames_dir: Path) -> list[tuple[str, float]]:
        """
        Usa ffmpeg para extraer un frame por cada cambio de escena.
        Garantiza al menos 1 frame cada MIN_FRAME_INTERVAL_S segundos.
        Retorna lista de (ruta_frame, timestamp_segundos).
        """
        video_duration = self._get_video_duration(video_path)

        cmd_extract = [
            "ffmpeg", "-i", str(video_path),
            "-vf", (
                f"select='gt(scene,{SCENE_THRESHOLD})',"
                f"scale='if(gt(iw,{MAX_FRAME_WIDTH}),{MAX_FRAME_WIDTH},-2)':-2"
            ),
            "-vsync", "vfr",
            "-q:v", "2",
            str(frames_dir / "frame_%05d.jpg"),
            "-y",
        ]
        self._run_ffmpeg(cmd_extract, timeout=600)

        frame_files = sorted(frames_dir.glob("frame_*.jpg"))
        scene_timestamps = self._get_scene_timestamps(video_path)

        if video_duration > 0:
            covered_times = set()
            for i, ts in enumerate(scene_timestamps):
                bucket = int(ts // MIN_FRAME_INTERVAL_S)
                covered_times.add(bucket)

            total_buckets = int(video_duration // MIN_FRAME_INTERVAL_S) + 1
            missing_times = []
            for b in range(total_buckets):
                if b not in covered_times:
                    missing_times.append(b * MIN_FRAME_INTERVAL_S)

            if missing_times:
                logger.info(f"[I] Rellenando {len(missing_times)} gaps de cobertura (cada {MIN_FRAME_INTERVAL_S}s)")
                fill_dir = frames_dir / "fill"
                fill_dir.mkdir(exist_ok=True)
                for idx, ts in enumerate(missing_times):
                    out_path = fill_dir / f"fill_{idx:05d}.jpg"
                    cmd_fill = [
                        "ffmpeg", "-ss", str(ts),
                        "-i", str(video_path),
                        "-vf", f"scale='if(gt(iw,{MAX_FRAME_WIDTH}),{MAX_FRAME_WIDTH},-2)':-2",
                        "-frames:v", "1",
                        "-q:v", "2",
                        str(out_path),
                        "-y",
                    ]
                    try:
                        self._run_ffmpeg(cmd_fill, timeout=30)
                        if out_path.exists():
                            frame_files.append(out_path)
                            scene_timestamps.append(ts)
                    except Exception:
                        pass

        if not frame_files:
            logger.info("Sin cambios de escena, muestreo cada 30s como fallback")
            cmd_fallback = [
                "ffmpeg", "-i", str(video_path),
                "-vf", (
                    f"fps=1/{MIN_FRAME_INTERVAL_S},"
                    f"scale='if(gt(iw,{MAX_FRAME_WIDTH}),{MAX_FRAME_WIDTH},-2)':-2"
                ),
                "-q:v", "2",
                str(frames_dir / "frame_%05d.jpg"),
                "-y",
            ]
            self._run_ffmpeg(cmd_fallback, timeout=600)
            frame_files = sorted(frames_dir.glob("frame_*.jpg"))
            scene_timestamps = [i * MIN_FRAME_INTERVAL_S for i in range(len(frame_files))]

        paired = []
        for i, fp in enumerate(frame_files):
            ts = scene_timestamps[i] if i < len(scene_timestamps) else float(i * MIN_FRAME_INTERVAL_S)
            paired.append((ts, str(fp)))
        paired.sort(key=lambda x: x[0])

        if len(paired) > MAX_SLIDES:
            step = len(paired) / MAX_SLIDES
            paired = [paired[int(i * step)] for i in range(MAX_SLIDES)]

        return [(fp, ts) for ts, fp in paired]

    def _get_video_duration(self, video_path: Path) -> float:
        """Obtiene la duración del video en segundos."""
        cmd = [
            "ffprobe", "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "csv=p=0", str(video_path),
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=30, creationflags=_SUBPROCESS_FLAGS
            )
            duration_str = result.stdout.strip()
            if duration_str and duration_str != "N/A":
                return float(duration_str)
        except Exception as e:
            logger.warning(f"No se pudo obtener duración del video: {e}")
        return 0.0

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
                if line and line != "N/A":
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
    # Detección y extracción de sub-imágenes dentro de un frame
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_sub_images(
        self, frame_path: str, slide_num: int, images_dir: Path
    ) -> list[dict]:
        """
        Detecta sub-imágenes (fotos, diagramas incrustados) dentro de un frame
        usando detección de contornos con diferencia de color respecto al fondo.
        Guarda cada sub-imagen como archivo independiente.
        """
        try:
            with Image.open(frame_path) as img:
                w, h = img.size
                min_area = (w * h) * 0.02
                max_area = (w * h) * 0.85
                min_dim = 60

                gray = img.convert("L")

                border_pixels = []
                for x in range(w):
                    border_pixels.append(gray.getpixel((x, 0)))
                    border_pixels.append(gray.getpixel((x, h - 1)))
                for y in range(h):
                    border_pixels.append(gray.getpixel((0, y)))
                    border_pixels.append(gray.getpixel((w - 1, y)))

                from collections import Counter
                bg_val = Counter(border_pixels).most_common(1)[0][0]

                threshold = 40
                mask = Image.new("L", (w, h), 0)
                mask_pixels = mask.load()
                gray_pixels = gray.load()
                for y in range(h):
                    for x in range(w):
                        if abs(gray_pixels[x, y] - bg_val) > threshold:
                            mask_pixels[x, y] = 255

                visited = set()
                regions = []

                def _flood_fill(sx, sy):
                    stack = [(sx, sy)]
                    x_min, x_max, y_min, y_max = sx, sx, sy, sy
                    count = 0
                    while stack:
                        cx, cy = stack.pop()
                        if (cx, cy) in visited:
                            continue
                        if cx < 0 or cy < 0 or cx >= w or cy >= h:
                            continue
                        if mask_pixels[cx, cy] == 0:
                            continue
                        visited.add((cx, cy))
                        count += 1
                        x_min = min(x_min, cx)
                        x_max = max(x_max, cx)
                        y_min = min(y_min, cy)
                        y_max = max(y_max, cy)
                        for dx, dy in [(-2, 0), (2, 0), (0, -2), (0, 2)]:
                            nx, ny = cx + dx, cy + dy
                            if 0 <= nx < w and 0 <= ny < h and (nx, ny) not in visited:
                                stack.append((nx, ny))
                    return x_min, y_min, x_max, y_max, count

                step = max(4, min(w, h) // 100)
                for sy in range(0, h, step):
                    for sx in range(0, w, step):
                        if (sx, sy) in visited or mask_pixels[sx, sy] == 0:
                            continue
                        x1, y1, x2, y2, cnt = _flood_fill(sx, sy)
                        rw = x2 - x1
                        rh = y2 - y1
                        area = rw * rh
                        if area < min_area or area > max_area:
                            continue
                        if rw < min_dim or rh < min_dim:
                            continue
                        density = cnt / max(area / 4, 1)
                        if density < 0.05:
                            continue
                        regions.append((x1, y1, x2, y2))

                if not regions:
                    return []

                regions = self._merge_overlapping_regions(regions)

                sub_images = []
                for idx, (x1, y1, x2, y2) in enumerate(regions[:5]):
                    pad = 4
                    x1 = max(0, x1 - pad)
                    y1 = max(0, y1 - pad)
                    x2 = min(w, x2 + pad)
                    y2 = min(h, y2 + pad)

                    cropped = img.crop((x1, y1, x2, y2))
                    sub_name = f"slide_{slide_num:03d}_sub_{idx + 1}.png"
                    sub_path = images_dir / sub_name
                    cropped.save(str(sub_path), "PNG", compress_level=1)

                    # Describir sub-imagen con Gemini
                    description = self._describe_sub_image(str(sub_path))

                    sub_images.append({
                        "file": f"slide_images/{sub_name}",
                        "description": description,
                    })

                return sub_images

        except Exception as e:
            logger.warning(f"Error extrayendo sub-imágenes del slide {slide_num}: {e}")
            return []

    def _describe_sub_image(self, image_path: str) -> str:
        """Usa Gemini Vision para describir una sub-imagen extraída."""
        try:
            with Image.open(image_path) as img:
                prompt = (
                    "Describe brevemente el contenido académico de esta imagen "
                    "(diagrama, gráfica, fórmula, esquema, etc.). "
                    "Si no hay contenido académico, responde: Sin contenido. "
                    "Máximo 80 palabras."
                )
                description = self._call_gemini_with_retry([prompt, img.copy()])
            if "Sin contenido" in description:
                return ""
            return description
        except Exception as e:
            logger.warning(f"Error describiendo sub-imagen: {e}")
            return ""

    @staticmethod
    def _merge_overlapping_regions(regions: list[tuple]) -> list[tuple]:
        """Fusiona bounding boxes que se solapan."""
        if not regions:
            return []
        merged = list(regions)
        changed = True
        while changed:
            changed = False
            new_merged = []
            used = set()
            for i in range(len(merged)):
                if i in used:
                    continue
                x1, y1, x2, y2 = merged[i]
                for j in range(i + 1, len(merged)):
                    if j in used:
                        continue
                    ax1, ay1, ax2, ay2 = merged[j]
                    if x1 <= ax2 and x2 >= ax1 and y1 <= ay2 and y2 >= ay1:
                        x1 = min(x1, ax1)
                        y1 = min(y1, ay1)
                        x2 = max(x2, ax2)
                        y2 = max(y2, ay2)
                        used.add(j)
                        changed = True
                new_merged.append((x1, y1, x2, y2))
                used.add(i)
            merged = new_merged
        return merged

    # ─────────────────────────────────────────────────────────────────────────
    # Limpieza
    # ─────────────────────────────────────────────────────────────────────────

    def _cleanup_frames(self, frames_dir: Path) -> None:
        try:
            for fp in frames_dir.rglob("*.jpg"):
                fp.unlink(missing_ok=True)
            fill_dir = frames_dir / "fill"
            if fill_dir.exists():
                fill_dir.rmdir()
            frames_dir.rmdir()
        except Exception as e:
            logger.warning(f"No se pudo limpiar frames temporales: {e}")
