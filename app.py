"""
V_T_R - Video Transcriptor y Resumen
Servidor Flask Principal
"""
import os
import time
import base64
import glob as glob_mod
import threading
import subprocess
import logging
import logging.handlers
import collections
from datetime import datetime
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory, Response
from flask_cors import CORS
from werkzeug.utils import secure_filename

import config
from services import AudioExtractor, Transcriber, GeminiService, FileManager, SlideExtractor
from services.toon_encoder import dumps as toon_dumps

# Configurar logging (consola + archivo rotado por tamaño)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'
)

# Log a archivo con rotación por tamaño (5 MB, conservar 10 archivos)
_LOGS_DIR = Path(r"D:\Documentos\V_T_R\logs")
_LOGS_DIR.mkdir(parents=True, exist_ok=True)
_log_filename = _LOGS_DIR / f"vtr_{datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}.log"
_file_handler = logging.handlers.RotatingFileHandler(
    filename=str(_log_filename),
    maxBytes=5 * 1024 * 1024,   # 5 MB
    backupCount=10,
    encoding="utf-8",
)
_file_handler.setLevel(logging.INFO)
_file_handler.setFormatter(logging.Formatter('%(asctime)s | %(levelname)-8s | %(name)s | %(message)s'))
logging.getLogger().addHandler(_file_handler)

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Buffer de logs en memoria (solo sesión actual)
# ──────────────────────────────────────────────────────────

_log_buffer = collections.deque(maxlen=2000)

# ──────────────────────────────────────────────────────────
# Estado del procesamiento en curso (para la barra de progreso)
# ──────────────────────────────────────────────────────────

_proc_status = {"step": "Esperando...", "percent": 0, "detail": ""}
_server_start_time = time.time()
_cancel_flag = threading.Event()  # se activa cuando el usuario cancela el procesamiento


def _raise_if_cancelled():
    """Lanza InterruptedError si el usuario solicitó cancelar."""
    if _cancel_flag.is_set():
        raise InterruptedError("Procesamiento cancelado por el usuario")


def _set_status(step: str, percent: int, detail: str = "") -> None:
    """Actualiza el estado visible en la barra de progreso del frontend."""
    _proc_status["step"] = step
    _proc_status["percent"] = percent
    _proc_status["detail"] = detail
    logger.info(f"[Estado] {step}{(' — ' + detail) if detail else ''}")


class _MemoryLogHandler(logging.Handler):
    """Captura logs en memoria para exponerlos vía /api/logs."""
    def emit(self, record):
        try:
            if record.name == 'werkzeug':   # ignorar access logs HTTP
                return
            msg = record.getMessage()
            _log_buffer.append({
                "ts":  record.created,
                "lvl": record.levelname[0],          # I / W / E / C
                "src": record.name.split('.')[-1][:15],
                "msg": msg[:400] if len(msg) > 400 else msg,
            })
        except Exception:
            pass


_mem_handler = _MemoryLogHandler()
_mem_handler.setLevel(logging.DEBUG)
logging.getLogger().addHandler(_mem_handler)

# Inicializar Flask
app = Flask(__name__, static_folder='static')
app.config['MAX_CONTENT_LENGTH'] = config.MAX_CONTENT_LENGTH
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 0  # Sin caché en archivos estáticos
CORS(app)


@app.after_request
def _no_cache(response):
    """Evita que el WebEngine cachee archivos JS/CSS para que siempre cargue la versión actual."""
    if response.content_type and any(
        response.content_type.startswith(t)
        for t in ("application/javascript", "text/css", "text/html")
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# Inicializar servicios
file_manager = FileManager(
    base_dir=str(config.BASE_DIR),
    clases_dir=str(config.CLASES_DIR),
    temp_dir=str(config.TEMP_DIR)
)

audio_extractor = AudioExtractor(sample_rate=config.AUDIO_SAMPLE_RATE)

# Transcriber se inicializa lazy (cuando se necesita)
transcriber = None

# GeminiService se inicializa si hay API key
gemini_service = None
if config.GEMINI_API_KEY:
    try:
        gemini_service = GeminiService(
            api_key=config.GEMINI_API_KEY,
            model_name=config.GEMINI_MODEL
        )
    except Exception as e:
        logger.error(f"Error inicializando Gemini: {e}")

# SlideExtractor se inicializa si hay GEMINI_API_KEY y está habilitado
slide_extractor = None
if config.GEMINI_API_KEY and config.SLIDE_EXTRACTION_ENABLED:
    try:
        slide_extractor = SlideExtractor(
            gemini_api_key=config.GEMINI_API_KEY,
            gemini_model=config.GEMINI_MODEL,
        )
        logger.info("SlideExtractor listo (Gemini Vision)")
    except Exception as e:
        logger.error(f"Error inicializando SlideExtractor: {e}")


def _get_extra_knowledge_content() -> str:
    """Lee el contenido de la carpeta global extra_knowledge/."""
    return file_manager.get_extra_knowledge_content()


def get_transcriber(model_name: str = None) -> Transcriber:
    """Obtiene o crea una instancia del transcriber"""
    global transcriber
    model = model_name or config.DEFAULT_WHISPER_MODEL

    if transcriber is None or transcriber.model_name != model:
        transcriber = Transcriber(
            model_name=model,
            openai_api_key=config.OPENAI_API_KEY
        )

    return transcriber


# ============== RUTAS DE LA API ==============

@app.route('/')
def index():
    """Sirve la página principal"""
    return send_from_directory('static', 'index.html')


@app.route('/api/status', methods=['GET'])
def get_status():
    """Obtiene el estado del sistema"""
    gpu_available = False
    gpu_info = None

    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            props = torch.cuda.get_device_properties(0)
            total = props.total_memory
            free, _ = torch.cuda.mem_get_info(0)
            used = total - free
            gpu_info = {
                "name": torch.cuda.get_device_name(0),
                "vram_total_gb": round(total / (1024**3), 2),
                "vram_used_gb":  round(used  / (1024**3), 2),
                "vram_free_gb":  round(free  / (1024**3), 2),
                "vram_used_pct": round(used  / total * 100, 1),
            }
    except ImportError:
        logger.warning("PyTorch no está instalado. No se puede verificar GPU.")

    return jsonify({
        "status": "ok",
        "gemini_configured": gemini_service is not None,
        "openai_configured": config.OPENAI_API_KEY is not None,
        "vision_configured": slide_extractor is not None,
        "gpu_available": gpu_available,
        "gpu_info": gpu_info,
        "whisper_models": list(config.WHISPER_MODELS.keys()),
        "default_model": config.DEFAULT_WHISPER_MODEL
    })


@app.route('/api/classes', methods=['GET'])
def get_classes():
    """Obtiene lista de todas las clases"""
    classes = file_manager.get_all_classes()
    return jsonify({"classes": classes})


@app.route('/api/classes/<path:class_id>', methods=['GET'])
def get_class(class_id):
    """Obtiene información de una clase específica"""
    class_info = file_manager.get_class_by_id(class_id)

    if not class_info:
        return jsonify({"error": "Clase no encontrada"}), 404

    # Agregar resumen si existe
    summary = file_manager.get_summary(class_id)
    if summary:
        class_info["summary"] = summary

    return jsonify(class_info)


@app.route('/api/classes/<path:class_id>/transcription', methods=['GET'])
def get_transcription(class_id):
    """Obtiene la transcripción de una clase"""
    segments = file_manager.get_transcription(class_id)

    if segments is None:
        return jsonify({"error": "Transcripción no encontrada"}), 404

    return jsonify({
        "class_id": class_id,
        "segments": segments,
        "total_segments": len(segments)
    })


@app.route('/api/classes/<path:class_id>/slides', methods=['GET'])
def get_slides_content(class_id):
    """Devuelve el contenido de slides y el documento generado por IA."""
    content = file_manager.get_slides(class_id)
    document = file_manager.get_slides_document(class_id)
    if content is None and document is None:
        return jsonify({"error": "No hay slides para esta clase"}), 404
    return jsonify({
        "class_id": class_id,
        "content": content or "",
        "document": document or "",
    })


@app.route('/api/classes/<path:class_id>/slide_images/<path:filename>')
def serve_slide_image(class_id, filename):
    """Sirve las imágenes de slides guardadas en la carpeta de la clase."""
    images_dir = file_manager.clases_dir / class_id / "slide_images"
    if not images_dir.exists():
        return jsonify({"error": "No hay imágenes de slides"}), 404
    return send_from_directory(str(images_dir), filename)


def _build_image_map(class_id: str) -> dict:
    """
    Construye un mapa {slide_num: [rutas relativas de imágenes]} a partir de
    los archivos en slide_images/ de la carpeta de la clase.
    Incluye imágenes principales (slide_NNN.jpg) y sub-imágenes (slide_NNN_sub_M.jpg).
    """
    import re as _r
    images_dir = file_manager.clases_dir / class_id / "slide_images"
    if not images_dir.exists():
        return {}
    image_map = {}
    for fp in sorted(list(images_dir.glob("slide_*.jpg")) + list(images_dir.glob("slide_*.png"))):
        m = _r.match(r'slide_(\d+)(?:_sub_\d+)?\.(jpg|png)', fp.name)
        if m:
            slide_num = int(m.group(1))
            image_map.setdefault(slide_num, []).append(f"slide_images/{fp.name}")
    return image_map


@app.route('/api/classes/<path:class_id>/slides/regenerate', methods=['POST'])
def regenerate_slides_document(class_id):
    """
    Borra el documento IA de slides, regenera desde slides.md y limpia caché.
    Usa Server-Sent Events (SSE) para enviar progreso en tiempo real.
    """
    raw_slides = file_manager.get_slides(class_id)
    if not raw_slides:
        return jsonify({"error": "No hay slides crudos para esta clase"}), 404

    class_info = file_manager.get_class_by_id(class_id)
    if not class_info:
        return jsonify({"error": "Clase no encontrada"}), 404

    def _generate_sse():
        import json as _json

        def _send(event, data):
            return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        yield _send("progress", {"step": "Eliminando versión anterior...", "percent": 10, "eta": ""})

        # Borrar documento previo
        doc_path = file_manager.clases_dir / class_id / "slides_document.md"
        if doc_path.exists():
            doc_path.unlink()
            logger.info(f"Documento de slides anterior eliminado: {class_id}")

        yield _send("progress", {"step": "Limpiando caché de chat...", "percent": 20, "eta": ""})

        # Borrar caché de chat
        gemini_service.clear_chat_history(class_id)
        file_manager.delete_chat_history(class_id)
        cache_path = file_manager.clases_dir / class_id / "gemini_cache.txt"
        if cache_path.exists():
            cache_path.unlink()

        yield _send("progress", {"step": "Filtrando slides de UI/navegación...", "percent": 30, "eta": "~15-30s"})

        folder_name = class_id.split('/')[-1] if '/' in class_id else class_id

        # Construir mapa de imágenes desde la carpeta de clase
        yield _send("progress", {"step": "Indexando imágenes de slides...", "percent": 35, "eta": "~15-25s"})
        image_map = _build_image_map(class_id)

        try:
            yield _send("progress", {"step": "Enviando a Gemini para generación...", "percent": 45, "eta": "~10-25s"})

            t0 = time.time()
            new_doc = gemini_service.generate_slides_document(raw_slides, folder_name, image_map=image_map)
            elapsed = time.time() - t0

            if new_doc:
                yield _send("progress", {"step": "Guardando documento...", "percent": 90, "eta": "<2s"})
                class_folder = file_manager.clases_dir / class_id
                file_manager.save_slides_document(new_doc, class_folder)
                logger.info(f"Documento de slides regenerado en {elapsed:.1f}s: {class_id}")

                yield _send("progress", {"step": "¡Listo!", "percent": 100, "eta": ""})
                yield _send("done", {"success": True, "document": new_doc, "elapsed": round(elapsed, 1)})
            else:
                yield _send("error", {"error": "Gemini no generó contenido"})
        except Exception as e:
            logger.error(f"Error regenerando documento de slides: {e}")
            yield _send("error", {"error": str(e)})

    return Response(
        _generate_sse(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route('/api/classes/<path:class_id>/slides/regenerate-from-video', methods=['POST'])
def regenerate_slides_from_video(class_id):
    """
    Reprocesa slides desde el video original preservado.
    NO toca transcripcion.jsonl ni resumen.md.
    Usa Server-Sent Events (SSE) para enviar progreso en tiempo real.
    """
    if not slide_extractor:
        return jsonify({"error": "SlideExtractor no está configurado"}), 500

    class_info = file_manager.get_class_by_id(class_id)
    if not class_info:
        return jsonify({"error": "Clase no encontrada"}), 404

    video_path = file_manager.get_preserved_video(class_id)
    if not video_path:
        return jsonify({"error": "Video original no encontrado en videos_originales/"}), 404

    def _generate_sse():
        import json as _json

        def _send(event, data):
            return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        yield _send("progress", {"step": "Eliminando slides anteriores...", "percent": 5, "eta": ""})

        try:
            t0 = time.time()
            result = file_manager.regenerate_slides(
                class_id, slide_extractor, gemini_service=gemini_service
            )
            elapsed = time.time() - t0

            if result["success"]:
                yield _send("progress", {"step": "¡Listo!", "percent": 100, "eta": ""})

                # Limpiar caché de chat
                if gemini_service:
                    gemini_service.clear_chat_history(class_id)
                file_manager.delete_chat_history(class_id)
                cache_path = file_manager.clases_dir / class_id / "gemini_cache.txt"
                if cache_path.exists():
                    cache_path.unlink()

                yield _send("done", {
                    "success": True,
                    "message": result["message"],
                    "slides_count": result.get("slides_count", 0),
                    "elapsed": round(elapsed, 1),
                })
            else:
                yield _send("error", {"error": result["message"]})
        except Exception as e:
            logger.error(f"Error regenerando slides desde video: {e}")
            yield _send("error", {"error": str(e)})

    return Response(
        _generate_sse(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route('/api/classes/<path:class_id>/summary', methods=['GET'])
def get_summary(class_id):
    """Obtiene el resumen de una clase"""
    summary = file_manager.get_summary(class_id)

    if summary is None:
        return jsonify({"error": "Resumen no encontrado"}), 404

    return jsonify({
        "class_id": class_id,
        "summary": summary
    })


@app.route('/api/classes/<path:class_id>/summary/regenerate', methods=['POST'])
def regenerate_summary(class_id):
    """
    Regenera el resumen de una clase usando Gemini.
    Usa Server-Sent Events (SSE) para enviar progreso en tiempo real.
    """
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    transcription_text = file_manager.get_transcription_text(class_id)
    if not transcription_text:
        return jsonify({"error": "No se encontró la transcripción"}), 404

    class_info = file_manager.get_class_by_id(class_id)
    if not class_info:
        return jsonify({"error": "Clase no encontrada"}), 404

    def _generate_sse():
        import json as _json

        def _send(event, data):
            return f"event: {event}\ndata: {_json.dumps(data, ensure_ascii=False)}\n\n"

        yield _send("progress", {"step": "Eliminando resumen anterior...", "percent": 10, "eta": ""})

        # Borrar resumen previo
        summary_path = file_manager.clases_dir / class_id / "resumen.md"
        if summary_path.exists():
            summary_path.unlink()
            logger.info(f"Resumen anterior eliminado: {class_id}")

        yield _send("progress", {"step": "Limpiando caché de chat...", "percent": 20, "eta": ""})

        # Borrar caché de chat
        gemini_service.clear_chat_history(class_id)
        file_manager.delete_chat_history(class_id)
        cache_path = file_manager.clases_dir / class_id / "gemini_cache.txt"
        if cache_path.exists():
            cache_path.unlink()

        yield _send("progress", {"step": "Generando nuevo resumen con IA...", "percent": 40, "eta": "~10-30s"})

        folder_name = class_id.split('/')[-1] if '/' in class_id else class_id

        try:
            t0 = time.time()
            new_summary = gemini_service.generate_summary(transcription_text, folder_name)
            elapsed = time.time() - t0

            if new_summary:
                yield _send("progress", {"step": "Guardando resumen...", "percent": 90, "eta": "<2s"})
                class_folder = file_manager.clases_dir / class_id
                file_manager.save_summary(new_summary, class_folder)
                logger.info(f"Resumen regenerado en {elapsed:.1f}s: {class_id}")

                yield _send("progress", {"step": "¡Listo!", "percent": 100, "eta": ""})
                yield _send("done", {"success": True, "summary": new_summary, "elapsed": round(elapsed, 1)})
            else:
                yield _send("error", {"error": "Gemini no generó contenido"})
        except Exception as e:
            logger.error(f"Error regenerando resumen: {e}")
            yield _send("error", {"error": str(e)})

    return Response(
        _generate_sse(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.route('/api/classes/<path:class_id>', methods=['PATCH'])
def rename_class(class_id):
    """Renombra una clase guardando el nuevo nombre en nombre.txt"""
    data = request.get_json()
    if not data or 'name' not in data:
        return jsonify({"error": "Nombre requerido"}), 400
    new_name = data['name'].strip()
    if not new_name:
        return jsonify({"error": "El nombre no puede estar vacío"}), 400
    success = file_manager.rename_class(class_id, new_name)
    if not success:
        return jsonify({"error": "Clase no encontrada"}), 404
    return jsonify({"success": True})


@app.route('/api/classes/<path:class_id>', methods=['DELETE'])
def delete_class(class_id):
    """Elimina una clase y libera su caché de Gemini si existe"""
    # Liberar caché de Gemini antes de borrar los archivos
    if gemini_service:
        cache_name = file_manager.get_cache_name(class_id)
        if cache_name:
            try:
                import google.generativeai as genai_mod
                cache = genai_mod.caching.CachedContent.get(cache_name)
                cache.delete()
                logger.info(f"Caché de Gemini eliminado: {cache_name}")
            except Exception:
                pass  # Ya expiró o no existe; no es crítico

    success = file_manager.delete_class(class_id)

    if not success:
        return jsonify({"error": "No se pudo eliminar la clase"}), 404

    return jsonify({"message": "Clase eliminada exitosamente"})


@app.route('/api/folders', methods=['GET'])
def get_folders():
    """Obtiene el árbol plano de carpetas de organización"""
    folders = file_manager.get_folder_tree()
    return jsonify({"folders": folders})


@app.route('/api/folders', methods=['POST'])
def create_folder():
    """Crea una carpeta de organización"""
    data = request.get_json()
    if not data or not data.get('path', '').strip():
        return jsonify({"error": "Se requiere el campo 'path'"}), 400
    try:
        folder = file_manager.create_folder(data['path'].strip())
        return jsonify({"success": True, "folder": folder})
    except Exception as e:
        logger.error(f"Error creando carpeta: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/process', methods=['POST'])
def process_video():
    """
    Procesa un video: extrae audio, transcribe, extrae slides y genera resumen
    """
    if 'video' not in request.files:
        return jsonify({"error": "No se proporcionó archivo de video"}), 400

    video_file = request.files['video']

    if video_file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    filename = secure_filename(video_file.filename)
    ext = Path(filename).suffix.lower()

    if ext not in config.SUPPORTED_VIDEO_FORMATS:
        return jsonify({
            "error": f"Formato no soportado: {ext}",
            "supported": config.SUPPORTED_VIDEO_FORMATS
        }), 400

    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    whisper_model = request.form.get('model', config.DEFAULT_WHISPER_MODEL)
    if whisper_model not in config.WHISPER_MODELS:
        whisper_model = config.DEFAULT_WHISPER_MODEL

    folder_path = request.form.get('folder_path', '').strip()

    if whisper_model == "openai" and not config.OPENAI_API_KEY:
        return jsonify({"error": "Se seleccionó OpenAI API pero OPENAI_API_KEY no está configurada en el servidor"}), 400

    video_path = None
    audio_path = None

    try:
        _cancel_flag.clear()  # limpiar cualquier cancelación anterior

        # 1. Guardar video temporal
        _set_status("Guardando video...", 5)
        video_path = file_manager.save_video_to_temp(video_file, filename)
        _raise_if_cancelled()

        # 2. Extraer audio
        _set_status("Extrayendo audio...", 15)
        audio_path = audio_extractor.extract_audio(video_path)
        _raise_if_cancelled()

        # 3. Transcribir (proceso más pesado)
        _set_status(f"Transcribiendo con Whisper ({whisper_model})...", 22)
        trans = get_transcriber(whisper_model)
        try:
            result = trans.transcribe(audio_path)
        except Exception as transcribe_error:
            logger.error(f"Error en transcripción con modelo '{whisper_model}': {transcribe_error}")
            _set_status("Error en transcripción", 0)
            file_manager.cleanup_temp_files(video_path, audio_path, delete_video=True)
            video_path = None
            audio_path = None
            error_response = {
                "error": str(transcribe_error),
                "message": "Error al transcribir el audio"
            }
            if whisper_model != "openai" and config.OPENAI_API_KEY:
                error_response["gpu_failed"] = True
                error_response["openai_available"] = True
            return jsonify(error_response), 500

        _raise_if_cancelled()

        # 4. Generar nombre de carpeta (antes de slides para tener persist_dir)
        _set_status("Generando nombre de carpeta...", 60)
        context_for_naming = result["text"][:5000]
        folder_name = gemini_service.generate_folder_name(context_for_naming)

        # 5. Crear carpeta para guardar archivos
        _set_status("Creando carpeta de clase...", 62)
        class_folder = file_manager.create_class_folder(folder_name, parent_path=folder_path)
        file_manager.save_transcription(result["segments"], class_folder)

        # 6. Extraer contenido de slides (persiste imágenes en la carpeta de clase)
        slides_markdown = ""
        slides_storage_md = ""
        if slide_extractor:
            try:
                _set_status("Detectando cambios de escena...", 65)

                def _slides_progress(current, total, msg):
                    pct = 65 + round(20 * current / total) if total else 65
                    _set_status(
                        f"Analizando imagen {current} de {total}",
                        pct,
                        "Gemini Vision",
                    )

                slides = slide_extractor.extract_slides(
                    video_path=video_path,
                    temp_dir=str(config.TEMP_DIR),
                    progress_callback=_slides_progress,
                    persist_dir=str(class_folder),
                )
                slides_markdown = slide_extractor.format_slides_for_context(slides)
                slides_storage_md = slide_extractor.format_slides_for_storage(slides)
                n_useful = len([s for s in slides if s.get("text") or s.get("visual_description")])
                if slides_storage_md:
                    logger.info(f"Slides extraídos: {n_useful} con contenido")
                else:
                    logger.info("No se encontró contenido en los slides del video")
            except Exception as e:
                logger.warning(f"Error extrayendo slides (continuando sin slides): {e}")

        if slides_storage_md:
            file_manager.save_slides(slides_storage_md, class_folder)

        # 7. Generar resumen con transcripción + slides (proceso ligero, texto puro para IA)
        _set_status("Generando resumen con Gemini...", 93)
        full_context = result["text"] + slides_markdown
        summary = gemini_service.generate_summary(full_context, folder_name)
        file_manager.save_summary(summary, class_folder)

        # 8. Generar documento de slides (IA estructura el contenido OCR)
        if slides_storage_md:
            _set_status("Generando documento de presentación...", 97)
            try:
                class_id_tmp = class_folder.relative_to(file_manager.clases_dir).as_posix()
                img_map = _build_image_map(class_id_tmp)
                slides_document = gemini_service.generate_slides_document(
                    slides_storage_md, folder_name, image_map=img_map
                )
                if slides_document:
                    file_manager.save_slides_document(slides_document, class_folder)
                    logger.info("Documento de slides generado y guardado")
            except Exception as e:
                logger.warning(f"Error generando documento de slides (continuando): {e}")

        # 9. Preservar video original y limpiar temporales
        _set_status("Guardando video original...", 99)
        file_manager.preserve_video(video_path, folder_name, folder_path)
        file_manager.cleanup_temp_files(video_path, audio_path)
        _set_status("¡Listo!", 100)

        class_id = class_folder.relative_to(file_manager.clases_dir).as_posix()
        class_info = file_manager.get_class_by_id(class_id)
        class_info["summary"] = summary

        logger.info(f"Procesamiento completado: {class_folder.name}")
        _set_status("Esperando...", 0)   # resetear para el próximo video
        return jsonify({
            "success": True,
            "message": "Video procesado exitosamente",
            "class": class_info
        })

    except InterruptedError as e:
        logger.info(f"Procesamiento cancelado: {e}")
        _set_status("Esperando...", 0)
        if video_path:
            file_manager.cleanup_temp_files(video_path, audio_path, delete_video=True)
        return jsonify({"error": str(e), "cancelled": True}), 499

    except Exception as e:
        logger.error(f"Error procesando video: {e}")
        _set_status("Esperando...", 0)
        if video_path:
            file_manager.cleanup_temp_files(video_path, audio_path, delete_video=True)
        return jsonify({
            "error": str(e),
            "message": "Error al procesar el video"
        }), 500


# ============== ESTADO DEL PROCESAMIENTO ==============

@app.route('/api/process/status', methods=['GET'])
def get_process_status():
    """Devuelve el paso actual del procesamiento para la barra de progreso."""
    return jsonify(_proc_status)


@app.route('/api/system/status', methods=['GET'])
def get_system_status():
    """Estado combinado: procesamiento + GPU + servidor. Optimizado para polling remoto."""
    result = {
        "process": dict(_proc_status),
        "server_uptime_s": round(time.time() - _server_start_time),
        "gpu": {"gpu_available": False},
    }
    try:
        import torch
        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            total = props.total_memory
            free, _ = torch.cuda.mem_get_info(0)
            used = total - free
            result["gpu"] = {
                "gpu_available": True,
                "name": torch.cuda.get_device_name(0),
                "vram_total_gb": round(total / (1024**3), 2),
                "vram_used_gb": round(used / (1024**3), 2),
                "vram_free_gb": round(free / (1024**3), 2),
                "vram_used_pct": round(used / total * 100, 1),
                "gpu_util_pct": _get_gpu_util_pct(),
                "gpu_temp_c": _get_gpu_temp(),
            }
    except Exception:
        pass
    return jsonify(result)


@app.route('/api/process/cancel', methods=['POST'])
def cancel_process():
    """Solicita la cancelación del procesamiento en curso."""
    _cancel_flag.set()
    _set_status("Cancelando...", 0)
    return jsonify({"ok": True, "message": "Cancelación solicitada"})


@app.route('/api/stop', methods=['POST'])
def stop_server():
    """Detiene el servidor Flask y cierra la aplicación."""
    def _do_stop():
        time.sleep(0.8)
        logger.info("Servidor detenido por solicitud del usuario.")
        os._exit(0)
    threading.Thread(target=_do_stop, daemon=True).start()
    return jsonify({"ok": True, "message": "Cerrando aplicación..."})


def _nvidia_smi(*query_fields: str) -> list[str] | None:
    """
    Ejecuta nvidia-smi y devuelve los valores solicitados, o None si falla.
    Busca nvidia-smi en PATH y también en la ruta típica de Windows.
    """
    import shutil
    smi = shutil.which("nvidia-smi")
    if not smi and os.name == "nt":
        # Ruta común en Windows con drivers DCH / CUDA Toolkit
        candidates = [
            r"C:\Windows\System32\nvidia-smi.exe",
            r"C:\Program Files\NVIDIA Corporation\NVSMI\nvidia-smi.exe",
        ]
        smi = next((p for p in candidates if os.path.isfile(p)), None)
    if not smi:
        return None
    try:
        flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
        result = subprocess.run(
            [smi, f"--query-gpu={','.join(query_fields)}", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=4,
            creationflags=flags,
        )
        if result.returncode == 0:
            return [v.strip() for v in result.stdout.strip().split(",")]
    except Exception:
        pass
    return None


def _get_gpu_util_pct() -> int | None:
    """Utilización de cómputo GPU (0-100). Usa nvidia-smi y pynvml como fallback."""
    vals = _nvidia_smi("utilization.gpu")
    if vals:
        try:
            return int(vals[0])
        except ValueError:
            pass
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        return pynvml.nvmlDeviceGetUtilizationRates(handle).gpu
    except Exception:
        return None


def _get_gpu_temp() -> int | None:
    """Temperatura GPU en °C. Usa nvidia-smi y pynvml como fallback."""
    vals = _nvidia_smi("temperature.gpu")
    if vals:
        try:
            return int(vals[0])
        except ValueError:
            pass
    try:
        import pynvml
        pynvml.nvmlInit()
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        return pynvml.nvmlDeviceGetTemperature(handle, pynvml.NVML_TEMPERATURE_GPU)
    except Exception:
        return None


@app.route('/api/gpu-stats', methods=['GET'])
def get_gpu_stats():
    """Devuelve estadísticas en tiempo real de VRAM/GPU para el panel de estado."""
    try:
        import torch
        if not torch.cuda.is_available():
            return jsonify({"gpu_available": False})

        props = torch.cuda.get_device_properties(0)
        total = props.total_memory
        # mem_get_info devuelve (libre, total) a nivel de driver — incluye todos los procesos
        free, _ = torch.cuda.mem_get_info(0)
        used = total - free

        return jsonify({
            "gpu_available":  True,
            "name":           torch.cuda.get_device_name(0),
            "vram_total_gb":  round(total / (1024**3), 2),
            "vram_used_gb":   round(used  / (1024**3), 2),
            "vram_free_gb":   round(free  / (1024**3), 2),
            "vram_used_pct":  round(used  / total * 100, 1),
            "gpu_util_pct":   _get_gpu_util_pct(),   # % carga de cómputo GPU (None si pynvml no disponible)
            "gpu_temp_c":     _get_gpu_temp(),        # °C (None si pynvml no disponible)
        })
    except ImportError:
        return jsonify({"gpu_available": False})
    except Exception as e:
        logger.warning(f"Error obteniendo stats de GPU: {e}")
        return jsonify({"gpu_available": False})


@app.route('/api/shutdown', methods=['POST'])
def shutdown_machine():
    """Apaga el equipo 3 segundos después de responder (da tiempo al frontend)."""
    def do_shutdown():
        time.sleep(3)
        logger.info("Apagando el equipo por solicitud del usuario...")
        os.system("shutdown /s /f /t 0")

    threading.Thread(target=do_shutdown, daemon=True).start()
    return jsonify({"ok": True, "message": "El equipo se apagará en breve."})


@app.route('/api/shutdown-delayed', methods=['POST'])
def shutdown_machine_delayed():
    """Apaga el equipo con 60 segundos de margen (post-procesamiento masivo)."""
    logger.info("Apagado programado en 60 segundos (post-procesamiento).")
    os.system("shutdown /s /t 60")
    return jsonify({"ok": True, "message": "El equipo se apagará en 60 segundos."})


# ============== TÚNEL REMOTO (cloudflared) ==============

_tunnel_process = None

@app.route('/api/tunnel/start', methods=['POST'])
def start_tunnel():
    """Inicia un túnel cloudflared para acceso remoto seguro."""
    global _tunnel_process
    if _tunnel_process and _tunnel_process.poll() is None:
        return jsonify({"ok": False, "message": "El túnel ya está activo."})
    try:
        _tunnel_process = subprocess.Popen(
            ['cloudflared', 'tunnel', '--url', f'http://127.0.0.1:{config.FLASK_PORT}'],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8', errors='replace'
        )
        # Leer la URL generada por cloudflared
        url = None
        import re as _re
        for _ in range(40):
            line = _tunnel_process.stdout.readline()
            if not line:
                break
            m = _re.search(r'(https://[a-z0-9\-]+\.trycloudflare\.com)', line)
            if m:
                url = m.group(1)
                break
        if url:
            logger.info(f"Túnel cloudflared activo: {url}")
            return jsonify({"ok": True, "url": url})
        else:
            return jsonify({"ok": True, "url": None, "message": "Túnel iniciado, URL no detectada aún. Revisa los logs."})
    except FileNotFoundError:
        return jsonify({"ok": False, "message": "cloudflared no encontrado. Instálalo desde https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/"})
    except Exception as e:
        return jsonify({"ok": False, "message": str(e)})


@app.route('/api/tunnel/stop', methods=['POST'])
def stop_tunnel():
    """Detiene el túnel cloudflared activo."""
    global _tunnel_process
    if _tunnel_process and _tunnel_process.poll() is None:
        _tunnel_process.terminate()
        _tunnel_process.wait(timeout=5)
        _tunnel_process = None
        logger.info("Túnel cloudflared detenido.")
        return jsonify({"ok": True, "message": "Túnel detenido."})
    _tunnel_process = None
    return jsonify({"ok": False, "message": "No hay túnel activo."})


@app.route('/api/tunnel/status', methods=['GET'])
def tunnel_status():
    """Devuelve si el túnel está activo."""
    active = _tunnel_process is not None and _tunnel_process.poll() is None
    return jsonify({"active": active})


# ============== LOGS EN MEMORIA ==============

@app.route('/api/logs', methods=['GET'])
def get_logs():
    """Devuelve los logs capturados en memoria desde el inicio de la sesión."""
    since = request.args.get('since', 0.0, type=float)
    entries = [e for e in _log_buffer if e['ts'] > since]
    return jsonify({"logs": entries, "server_time": time.time()})


# ============== DESCARGA DE SLIDES (PDF / MARKDOWN) ==============

def _build_slides_pdf(class_id: str, class_name: str, slides_md: str) -> bytes:
    """
    Genera un PDF limpio y estético a partir del contenido Markdown de slides.
    Usa fpdf2 (puro Python, sin dependencias de sistema).
    """
    from fpdf import FPDF
    import re as _re
    from datetime import datetime

    # ── Paleta ──────────────────────────────────────────────────────────────
    C_BG       = (248, 249, 250)   # fondo de página
    C_HEADER   = (30, 58, 138)     # azul oscuro: cabecera de slide
    C_WHITE    = (255, 255, 255)
    C_TEXT     = (31, 41, 55)      # gris oscuro: texto principal
    C_CAPTION  = (107, 114, 128)   # gris medio: pie de página
    C_VISUAL   = (234, 179, 8)     # amarillo: caja de diagrama

    def _s(txt: str) -> str:
        """Sanitiza texto a latin-1 para fpdf core fonts."""
        return txt.encode("latin-1", errors="replace").decode("latin-1")

    _hdr_txt = _s(f"V_T_R  {class_name.replace('_', ' ')}")

    class SlidesPDF(FPDF):
        def header(self):
            if self.page_no() == 1:
                return
            # Fondo claro de página
            self.set_fill_color(*C_BG)
            self.rect(0, 0, self.w, self.h, "F")
            # Franja de cabecera
            ew = self.w - self.l_margin - self.r_margin
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(*C_CAPTION)
            self.set_xy(self.l_margin, 6)
            self.cell(ew, 4, _hdr_txt, align="L", ln=True)
            self.set_x(self.l_margin)
            self.set_draw_color(*C_CAPTION)
            self.set_line_width(0.2)
            self.line(10, self.get_y(), self.w - 10, self.get_y())
            self.set_xy(self.l_margin, self.get_y() + 2)

        def footer(self):
            if self.page_no() == 1:
                return
            ew = self.w - self.l_margin - self.r_margin
            self.set_y(-12)
            self.set_x(self.l_margin)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*C_CAPTION)
            self.cell(ew, 4, f"Pag. {self.page_no() - 1}", align="C")

    pdf = SlidesPDF()
    pdf.set_margins(left=14, top=14, right=14)
    pdf.set_auto_page_break(auto=True, margin=16)
    # Ancho efectivo de contenido (no usar 0 en cell/multi_cell para evitar errores de posición)
    EW = pdf.w - pdf.l_margin - pdf.r_margin  # ≈ 182 mm en A4

    # ── Portada ──────────────────────────────────────────────────────────────
    pdf.add_page()
    # Fondo de portada
    pdf.set_fill_color(*C_BG)
    pdf.rect(0, 0, pdf.w, pdf.h, "F")
    # Banda azul superior
    pdf.set_fill_color(*C_HEADER)
    pdf.rect(0, 0, pdf.w, 50, "F")

    pdf.set_xy(pdf.l_margin, 10)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*C_WHITE)
    pdf.cell(EW, 10, "V_T_R", align="C", ln=True)
    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 10)
    pdf.cell(EW, 6, "Video Transcriptor y Resumen", align="C", ln=True)

    pdf.set_xy(pdf.l_margin, 62)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*C_TEXT)
    pdf.multi_cell(EW, 8, _s(class_name.replace("_", " ")), align="C")

    pdf.set_x(pdf.l_margin)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_CAPTION)
    pdf.multi_cell(EW, 5, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", align="C")

    n_slides = len(_re.findall(r"^## Slide \d+", slides_md, flags=_re.MULTILINE))
    pdf.set_x(pdf.l_margin)
    pdf.multi_cell(EW, 5, f"Total slides con contenido: {n_slides}", align="C")

    # ── Parsear secciones del Markdown ───────────────────────────────────────
    _img_re = _re.compile(r'^!\[.*?\]\((.+?)\)')
    sections = []
    current = None
    for line in slides_md.splitlines():
        if line.startswith("## Slide "):
            if current:
                sections.append(current)
            current = {"header": line[3:], "text_lines": [], "visual": "", "images": []}
        elif current is not None:
            stripped = line.strip()
            img_m = _img_re.match(stripped)
            if img_m:
                current["images"].append(img_m.group(1))
            elif stripped.startswith("> "):
                current["visual"] = stripped[2:].strip()
            elif stripped not in ("---", "**Texto en pantalla:**", "**Elemento visual detectado:**") and stripped:
                current["text_lines"].append(stripped)
    if current:
        sections.append(current)

    # Resolver directorio de imágenes de la clase
    _class_images_dir = file_manager.clases_dir / class_id

    # ── Páginas de slides ─────────────────────────────────────────────────
    for sec in sections:
        try:
            pdf.add_page()

            # Cabecera del slide (banda azul)
            pdf.set_fill_color(*C_HEADER)
            pdf.set_text_color(*C_WHITE)
            pdf.set_font("Helvetica", "B", 11)
            pdf.set_x(pdf.l_margin)
            pdf.cell(EW, 8, _s(sec["header"]), fill=True, ln=True, align="L")
            pdf.set_xy(pdf.l_margin, pdf.get_y() + 3)

            # Imagen del slide (si existe) — aspect-ratio contain, max-height
            for img_ref in sec.get("images", []):
                img_path = _class_images_dir / img_ref
                if img_path.exists():
                    try:
                        from PIL import Image as _PILImage
                        with _PILImage.open(str(img_path)) as _pil_img:
                            iw_px, ih_px = _pil_img.size

                        # Convertir px a mm (asumiendo 96 DPI)
                        iw_mm = iw_px * 25.4 / 96
                        ih_mm = ih_px * 25.4 / 96

                        # Espacio disponible en la página
                        avail_w = EW
                        avail_h = pdf.h - pdf.get_y() - pdf.b_margin - 8
                        max_h = min(avail_h, 110)  # máximo 110mm de alto

                        if max_h < 20:
                            # No hay espacio suficiente, saltar a nueva página
                            pdf.add_page()
                            pdf.set_xy(pdf.l_margin, pdf.get_y() + 2)
                            avail_h = pdf.h - pdf.get_y() - pdf.b_margin - 8
                            max_h = min(avail_h, 110)

                        # Calcular dimensiones manteniendo aspect ratio (contain)
                        aspect = iw_mm / ih_mm if ih_mm > 0 else 1
                        # Ajustar por ancho
                        render_w = avail_w
                        render_h = render_w / aspect
                        # Si excede max_h, ajustar por alto
                        if render_h > max_h:
                            render_h = max_h
                            render_w = render_h * aspect
                        # Centrar horizontalmente si es más estrecha que el ancho disponible
                        x_offset = pdf.l_margin + (avail_w - render_w) / 2

                        pdf.image(str(img_path), x=x_offset, w=render_w, h=render_h)
                        pdf.ln(3)
                    except Exception as img_err:
                        logger.warning(f"PDF: no se pudo insertar imagen {img_ref}: {img_err}")

            # Texto del slide
            if sec["text_lines"]:
                pdf.set_font("Helvetica", "", 10)
                pdf.set_text_color(*C_TEXT)
                for tl in sec["text_lines"]:
                    safe = _s(tl)
                    if not safe.strip():
                        continue
                    pdf.set_x(pdf.l_margin)
                    pdf.multi_cell(EW, 5, safe, align="L")
                    pdf.set_x(pdf.l_margin)
                    pdf.ln(1)

            # Caja de diagrama / elemento visual
            if sec["visual"]:
                pdf.set_xy(pdf.l_margin, pdf.get_y() + 3)
                y0 = pdf.get_y()
                # Borde izquierdo amarillo
                pdf.set_draw_color(*C_VISUAL)
                pdf.set_line_width(0.8)
                pdf.line(pdf.l_margin, y0, pdf.l_margin, y0 + 18)
                # Etiqueta
                vis_w = EW - 4
                pdf.set_xy(pdf.l_margin + 4, y0)
                pdf.set_font("Helvetica", "B", 8)
                pdf.set_text_color(*[int(c * 0.6) for c in C_VISUAL])
                pdf.cell(vis_w, 5, "ELEMENTO VISUAL / DIAGRAMA", ln=True)
                # Descripción
                pdf.set_x(pdf.l_margin + 4)
                pdf.set_font("Helvetica", "I", 9)
                pdf.set_text_color(*C_TEXT)
                pdf.multi_cell(vis_w, 5, _s(sec["visual"]), align="L")
                pdf.set_xy(pdf.l_margin, pdf.get_y() + 2)

        except Exception as slide_err:
            logger.warning(f"PDF: omitiendo slide '{sec.get('header', '?')}': {slide_err}")
            continue

    return bytes(pdf.output())


@app.route('/api/classes/<path:class_id>/slides/download', methods=['GET'])
def download_slides(class_id):
    """
    Descarga el contenido de slides en PDF o Markdown.
    ?format=pdf  (default) · ?format=markdown
    """
    fmt = request.args.get("format", "pdf").lower()

    slides_md = file_manager.get_slides(class_id)
    if not slides_md:
        return jsonify({"error": "No hay slides para esta clase"}), 404

    class_info = file_manager.get_class_by_id(class_id)
    class_name = class_info.get("name", class_id) if class_info else class_id
    # Nombre seguro para el archivo
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in class_name)[:60].strip()

    if fmt == "markdown":
        return Response(
            slides_md,
            mimetype="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}_slides.md"'
            },
        )

    # PDF
    try:
        pdf_bytes = _build_slides_pdf(class_id, safe_name, slides_md)
        return Response(
            pdf_bytes,
            mimetype="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}_slides.pdf"'
            },
        )
    except ImportError:
        return jsonify({
            "error": "fpdf2 no está instalado. Ejecuta: pip install fpdf2"
        }), 500
    except Exception as e:
        logger.error(f"Error generando PDF de slides: {e}")
        return jsonify({"error": f"Error generando PDF: {str(e)}"}), 500


@app.route('/api/classes/<path:class_id>/toon/download', methods=['GET'])
def download_toon(class_id):
    """Exporta la transcripción completa de una clase en formato TOON."""
    segments = file_manager.get_transcription(class_id)
    if not segments:
        return jsonify({"error": "No hay transcripción para esta clase"}), 404

    class_info = file_manager.get_class_by_id(class_id)
    class_name = class_info.get("name", class_id) if class_info else class_id
    safe_name = "".join(c if c.isalnum() or c in "-_ " else "_" for c in class_name)[:60].strip()

    toon_data = {
        "clase": class_name,
        "segmentos": segments,
    }

    # Añadir resumen si existe
    summary = file_manager.get_summary(class_id)
    if summary:
        toon_data["resumen"] = summary

    # Añadir slides si existen
    slides = file_manager.get_slides(class_id)
    if slides:
        toon_data["slides"] = slides

    toon_text = toon_dumps(toon_data)

    return Response(
        toon_text,
        mimetype="text/plain; charset=utf-8",
        headers={
            "Content-Disposition": f'attachment; filename="{safe_name}.toon"'
        },
    )


# ============== RUTAS DE CHAT ==============

@app.route('/api/chat/<path:class_id>/start', methods=['POST'])
def start_chat(class_id):
    """Inicia (o restaura) una sesión de chat para una clase, cargando el historial guardado"""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    transcription_text = file_manager.get_transcription_text(class_id)
    if not transcription_text:
        return jsonify({"error": "No se encontró la transcripción"}), 404

    # Enriquecer con contenido de slides si existe (preferir documento IA)
    slides_content = file_manager.get_slides_document(class_id) \
        or file_manager.get_slides(class_id) or ""

    # Restaurar historial y nombre de caché desde disco
    saved_history = file_manager.get_chat_history(class_id) or []
    saved_cache_name = file_manager.get_cache_name(class_id)

    # Leer conocimiento extra, rúbricas e imágenes de contexto para RAM
    knowledge_text = file_manager.get_knowledge_text(class_id) or ""
    rubricas_text = file_manager.get_rubricas_text(class_id) or ""
    context_images = file_manager.get_context_images_data(class_id)

    extra_knowledge = _get_extra_knowledge_content()

    new_cache_name = gemini_service.start_chat_session(
        class_id, transcription_text,
        slides_content=slides_content,
        history=saved_history,
        cached_content_name=saved_cache_name,
        knowledge_text=knowledge_text,
        rubricas_text=rubricas_text,
        context_images=context_images,
        extra_knowledge_text=extra_knowledge,
    )

    # Guardar el nuevo nombre de caché si cambió (caché creado o renovado)
    if new_cache_name and new_cache_name != saved_cache_name:
        file_manager.save_cache_name(class_id, new_cache_name)

    return jsonify({
        "success": True,
        "message": "Sesión de chat iniciada",
        "class_id": class_id,
        "restored_messages": len(saved_history),
        "cached": new_cache_name is not None,
    })


@app.route('/api/chat/<path:class_id>/message', methods=['POST'])
def send_chat_message(class_id):
    """Envía un mensaje en el chat de una clase"""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    data = request.get_json()

    if not data or ('message' not in data and 'images' not in data):
        return jsonify({"error": "Se requiere un mensaje o imagen"}), 400

    user_message = (data.get('message') or '').strip()
    has_images = bool(data.get('images'))

    if not user_message and not has_images:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    try:
        extra_knowledge = _get_extra_knowledge_content()

        # Si no hay sesión activa en memoria, restaurar desde disco
        if class_id not in gemini_service.chat_sessions:
            transcription_text = file_manager.get_transcription_text(class_id)
            if not transcription_text:
                return jsonify({"error": "No se encontró la transcripción"}), 404
            slides_content = file_manager.get_slides_document(class_id) \
                or file_manager.get_slides(class_id) or ""
            saved_history = file_manager.get_chat_history(class_id) or []
            saved_cache_name = file_manager.get_cache_name(class_id)

            knowledge_text = file_manager.get_knowledge_text(class_id) or ""
            rubricas_text = file_manager.get_rubricas_text(class_id) or ""
            context_images = file_manager.get_context_images_data(class_id)

            new_cache_name = gemini_service.start_chat_session(
                class_id, transcription_text,
                slides_content=slides_content,
                history=saved_history,
                cached_content_name=saved_cache_name,
                knowledge_text=knowledge_text,
                rubricas_text=rubricas_text,
                context_images=context_images,
                extra_knowledge_text=extra_knowledge,
            )
            if new_cache_name and new_cache_name != saved_cache_name:
                file_manager.save_cache_name(class_id, new_cache_name)

        # Procesar imágenes inline si vienen en el payload
        inline_images = []
        for img_data in data.get('images', []):
            raw = base64.b64decode(img_data['base64'])
            inline_images.append({'mime_type': img_data['mime_type'], 'data': raw})

        # Enviar mensaje (con file_manager para auto-recovery de caché)
        response = gemini_service.chat(
            class_id, user_message, file_manager=file_manager,
            extra_knowledge_text=extra_knowledge, inline_images=inline_images,
        )

        # Persistir historial actualizado en disco
        updated_history = gemini_service.get_chat_history(class_id)
        file_manager.save_chat_history(class_id, updated_history)

        return jsonify({
            "success": True,
            "response": response,
            "class_id": class_id
        })

    except Exception as e:
        logger.error(f"Error en chat: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat/<path:class_id>/history', methods=['GET'])
def get_chat_history(class_id):
    """Obtiene el historial de chat de una clase (primero memoria, luego disco)"""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    # Si hay sesión en memoria usarla; si no, leer desde disco
    if class_id in gemini_service.chat_sessions:
        history = gemini_service.get_chat_history(class_id)
    else:
        history = file_manager.get_chat_history(class_id) or []

    return jsonify({
        "class_id": class_id,
        "history": history
    })


@app.route('/api/chat/<path:class_id>/clear', methods=['POST'])
def clear_chat(class_id):
    """Limpia el historial de chat de una clase (memoria y disco)"""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    gemini_service.clear_chat_history(class_id)
    file_manager.delete_chat_history(class_id)

    # Limpiar imágenes temporales de chat
    for f in glob_mod.glob(str(config.TEMP_DIR / "chat_img_*")):
        try:
            os.remove(f)
        except OSError:
            pass

    return jsonify({
        "success": True,
        "message": "Historial de chat limpiado"
    })


# ============== RUTAS DE CHAT DE CARPETA ==============

@app.route('/api/folder-chat/<path:folder_path>/start', methods=['POST'])
def start_folder_chat(folder_path):
    """Inicia (o restaura) una sesión de chat para una carpeta completa."""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    classes_content = file_manager.get_folder_all_content(folder_path)
    if not classes_content:
        return jsonify({"error": "No se encontraron clases en esta carpeta"}), 404

    folder_name = folder_path.split("/")[-1].replace("_", " ")

    saved_history = file_manager.get_folder_chat_history(folder_path) or []
    saved_cache_name = file_manager.get_folder_cache_name(folder_path)

    # Usamos folder_path como session key (prefijado para no colisionar con clases)
    session_key = f"__folder__{folder_path}"

    context_images = file_manager.get_context_images_data(folder_path)
    extra_knowledge = _get_extra_knowledge_content()

    new_cache_name = gemini_service.start_folder_chat_session(
        folder_id=session_key,
        folder_name=folder_name,
        classes_content=classes_content,
        history=saved_history,
        cached_content_name=saved_cache_name,
        context_images=context_images,
        extra_knowledge_text=extra_knowledge,
    )

    if new_cache_name and new_cache_name != saved_cache_name:
        file_manager.save_folder_cache_name(folder_path, new_cache_name)

    return jsonify({
        "success": True,
        "message": "Sesión de chat de carpeta iniciada",
        "folder_path": folder_path,
        "class_count": len(classes_content),
        "restored_messages": len(saved_history),
        "cached": new_cache_name is not None,
    })


@app.route('/api/folder-chat/<path:folder_path>/message', methods=['POST'])
def send_folder_chat_message(folder_path):
    """Envía un mensaje en el chat general de una carpeta."""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    data = request.get_json()
    if not data or ('message' not in data and 'images' not in data):
        return jsonify({"error": "Se requiere un mensaje o imagen"}), 400

    user_message = (data.get('message') or '').strip()
    has_images = bool(data.get('images'))
    if not user_message and not has_images:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    session_key = f"__folder__{folder_path}"

    try:
        extra_knowledge = _get_extra_knowledge_content()

        # Si no hay sesión activa, restaurar desde disco
        if session_key not in gemini_service.chat_sessions:
            classes_content = file_manager.get_folder_all_content(folder_path)
            if not classes_content:
                return jsonify({"error": "No se encontraron clases en esta carpeta"}), 404

            folder_name = folder_path.split("/")[-1].replace("_", " ")
            saved_history = file_manager.get_folder_chat_history(folder_path) or []
            saved_cache_name = file_manager.get_folder_cache_name(folder_path)
            context_images = file_manager.get_context_images_data(folder_path)

            new_cache_name = gemini_service.start_folder_chat_session(
                folder_id=session_key,
                folder_name=folder_name,
                classes_content=classes_content,
                history=saved_history,
                cached_content_name=saved_cache_name,
                context_images=context_images,
                extra_knowledge_text=extra_knowledge,
            )
            if new_cache_name and new_cache_name != saved_cache_name:
                file_manager.save_folder_cache_name(folder_path, new_cache_name)

        # Procesar imágenes inline si vienen en el payload
        inline_images = []
        for img_data in data.get('images', []):
            raw = base64.b64decode(img_data['base64'])
            inline_images.append({'mime_type': img_data['mime_type'], 'data': raw})

        response = gemini_service.chat(
            session_key, user_message, file_manager=file_manager,
            extra_knowledge_text=extra_knowledge, inline_images=inline_images,
        )

        updated_history = gemini_service.get_chat_history(session_key)
        file_manager.save_folder_chat_history(folder_path, updated_history)

        return jsonify({
            "success": True,
            "response": response,
            "folder_path": folder_path,
        })

    except Exception as e:
        logger.error(f"Error en chat de carpeta: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/folder-chat/<path:folder_path>/history', methods=['GET'])
def get_folder_chat_history_route(folder_path):
    """Obtiene el historial del chat general de una carpeta."""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    session_key = f"__folder__{folder_path}"

    if session_key in gemini_service.chat_sessions:
        history = gemini_service.get_chat_history(session_key)
    else:
        history = file_manager.get_folder_chat_history(folder_path) or []

    return jsonify({"folder_path": folder_path, "history": history})


@app.route('/api/folder-chat/<path:folder_path>/clear', methods=['POST'])
def clear_folder_chat(folder_path):
    """Limpia el historial del chat general de una carpeta."""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    session_key = f"__folder__{folder_path}"
    gemini_service.clear_chat_history(session_key)
    file_manager.delete_folder_chat_history(folder_path)

    # Limpiar imágenes temporales de chat
    for f in glob_mod.glob(str(config.TEMP_DIR / "chat_img_*")):
        try:
            os.remove(f)
        except OSError:
            pass

    return jsonify({"success": True, "message": "Historial de chat de carpeta limpiado"})


@app.route('/api/folder-chat/<path:folder_path>/extract_activity', methods=['POST'])
def extract_activity_folder(folder_path):
    """Extrae información de una actividad buscando en todas las clases de la carpeta."""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    classes_content = file_manager.get_folder_all_content(folder_path)
    if not classes_content:
        return jsonify({"error": "No se encontraron clases en esta carpeta"}), 404

    data = request.get_json(silent=True) or {}
    activity_name = data.get('activity_name', '').strip()
    if not activity_name:
        return jsonify({"error": "Debe proporcionar el nombre de la actividad"}), 400

    folder_name = folder_path.split("/")[-1].replace("_", " ")

    try:
        result = gemini_service.extract_activity_from_folder(
            classes_content, folder_name, activity_name
        )
        return jsonify({"activity": result})
    except Exception as e:
        logger.error(f"Error extrayendo actividad de carpeta: {e}")
        return jsonify({"error": str(e)}), 500


# ============== RUTAS DE EXTRA KNOWLEDGE GLOBAL ==============

@app.route('/api/extra-knowledge', methods=['GET'])
def list_extra_knowledge():
    """Lista archivos en la carpeta global extra_knowledge/."""
    files = file_manager.list_extra_knowledge_files()
    return jsonify({"files": files})


@app.route('/api/extra-knowledge', methods=['POST'])
def upload_extra_knowledge():
    """Sube un archivo a la carpeta global extra_knowledge/ y refresca caché."""
    if 'file' in request.files and request.files['file'].filename:
        f = request.files['file']
        try:
            saved_name = file_manager.save_extra_knowledge_file(f.filename, f)
            if gemini_service:
                gemini_service.refresh_cache()
            return jsonify({"success": True, "filename": saved_name})
        except Exception as e:
            logger.error(f"Error subiendo extra knowledge: {e}")
            return jsonify({"error": str(e)}), 500
    elif request.is_json:
        data = request.get_json()
        text = data.get('text', '').strip()
        if not text:
            return jsonify({"error": "Texto vacío"}), 400
        from datetime import datetime as _dt
        filename = f"knowledge_{_dt.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            saved_name = file_manager.save_extra_knowledge_text(filename, text)
            if gemini_service:
                gemini_service.refresh_cache()
            return jsonify({"success": True, "filename": saved_name})
        except Exception as e:
            logger.error(f"Error guardando extra knowledge: {e}")
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "No se envió archivo ni texto"}), 400


@app.route('/api/extra-knowledge/<filename>', methods=['DELETE'])
def delete_extra_knowledge(filename):
    """Elimina un archivo de extra_knowledge/ global y refresca caché."""
    success = file_manager.delete_extra_knowledge_file(filename)
    if success:
        if gemini_service:
            gemini_service.refresh_cache()
        return jsonify({"success": True})
    return jsonify({"error": "Archivo no encontrado"}), 404


# ============== RUTAS DE CONOCIMIENTO EXTRA Y RÚBRICAS ==============

@app.route('/api/chat/<path:class_id>/knowledge', methods=['POST'])
def upload_knowledge(class_id):
    """Sube un archivo de conocimiento extra para el chat de una clase."""
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400

    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    try:
        saved_name = file_manager.save_knowledge_file(class_id, f.filename, f)

        # Actualizar texto de conocimiento en RAM (sin invalidar caché ni historial)
        if class_id in gemini_service.chat_sessions:
            gemini_service.chat_sessions[class_id]["knowledge_text"] = \
                file_manager.get_knowledge_text(class_id) or ""

        return jsonify({"success": True, "filename": saved_name})
    except Exception as e:
        logger.error(f"Error subiendo archivo de conocimiento: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat/<path:class_id>/knowledge', methods=['GET'])
def list_knowledge(class_id):
    """Lista archivos de conocimiento extra de una clase."""
    files = file_manager.get_knowledge_files(class_id)
    return jsonify({"files": files})


@app.route('/api/chat/<path:class_id>/knowledge/<filename>', methods=['DELETE'])
def delete_knowledge(class_id, filename):
    """Elimina un archivo de conocimiento extra."""
    success = file_manager.delete_knowledge_file(class_id, filename)
    if success:
        # Actualizar texto de conocimiento en RAM
        if class_id in gemini_service.chat_sessions:
            gemini_service.chat_sessions[class_id]["knowledge_text"] = \
                file_manager.get_knowledge_text(class_id) or ""
        return jsonify({"success": True})
    return jsonify({"error": "Archivo no encontrado"}), 404


@app.route('/api/chat/<path:class_id>/rubrica', methods=['POST'])
def upload_rubrica(class_id):
    """Sube o guarda una rúbrica para el chat de una clase."""
    try:
        if 'file' in request.files and request.files['file'].filename:
            f = request.files['file']
            saved_name = file_manager.save_rubrica_file(class_id, f.filename, f)
        elif request.is_json:
            data = request.get_json()
            text = data.get('text', '').strip()
            if not text:
                return jsonify({"error": "Texto de rúbrica vacío"}), 400
            from datetime import datetime
            filename = f"rubrica_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
            saved_name = file_manager.save_rubrica(class_id, filename, text)
        else:
            return jsonify({"error": "No se envió archivo ni texto"}), 400

        # Actualizar texto de rúbricas en RAM (sin invalidar caché ni historial)
        if class_id in gemini_service.chat_sessions:
            gemini_service.chat_sessions[class_id]["rubricas_text"] = \
                file_manager.get_rubricas_text(class_id) or ""

        return jsonify({"success": True, "filename": saved_name})
    except Exception as e:
        logger.error(f"Error guardando rúbrica: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat/<path:class_id>/rubricas', methods=['GET'])
def list_rubricas(class_id):
    """Lista archivos de rúbricas de una clase."""
    files = file_manager.get_rubrica_files(class_id)
    return jsonify({"files": files})


@app.route('/api/chat/<path:class_id>/rubrica/<filename>', methods=['DELETE'])
def delete_rubrica(class_id, filename):
    """Elimina un archivo de rúbrica."""
    success = file_manager.delete_rubrica_file(class_id, filename)
    if success:
        # Actualizar texto de rúbricas en RAM
        if class_id in gemini_service.chat_sessions:
            gemini_service.chat_sessions[class_id]["rubricas_text"] = \
                file_manager.get_rubricas_text(class_id) or ""
        return jsonify({"success": True})
    return jsonify({"error": "Archivo no encontrado"}), 404


# ============== RUTAS DE IMÁGENES DE CONTEXTO ==============

@app.route('/api/chat/<path:class_id>/image', methods=['POST'])
def upload_context_image(class_id):
    """Sube una imagen de contexto para el chat de una clase."""
    if 'file' not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    f = request.files['file']
    if not f.filename:
        return jsonify({"error": "Nombre de archivo vacío"}), 400
    try:
        saved_name = file_manager.save_context_image(class_id, f.filename, f)
        # Actualizar imágenes de contexto en RAM
        if gemini_service and class_id in gemini_service.chat_sessions:
            gemini_service.chat_sessions[class_id]["context_images"] = \
                file_manager.get_context_images_data(class_id)
        return jsonify({"success": True, "filename": saved_name})
    except Exception as e:
        logger.error(f"Error subiendo imagen de contexto: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/chat/<path:class_id>/images', methods=['GET'])
def list_context_images(class_id):
    """Lista imágenes de contexto de una clase."""
    files = file_manager.get_context_images(class_id)
    return jsonify({"files": files})


@app.route('/api/chat/<path:class_id>/image/<filename>', methods=['DELETE'])
def delete_context_image_route(class_id, filename):
    """Elimina una imagen de contexto."""
    success = file_manager.delete_context_image(class_id, filename)
    if success:
        if gemini_service and class_id in gemini_service.chat_sessions:
            gemini_service.chat_sessions[class_id]["context_images"] = \
                file_manager.get_context_images_data(class_id)
        return jsonify({"success": True})
    return jsonify({"error": "Archivo no encontrado"}), 404


# ============== HERRAMIENTAS DE ESTUDIO ==============

@app.route('/api/classes/<path:class_id>/flashcards', methods=['POST'])
def generate_flashcards(class_id):
    """Genera flashcards en formato Anki y devuelve el archivo."""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    transcription_text = file_manager.get_transcription_text(class_id)
    if not transcription_text:
        return jsonify({"error": "No se encontró la transcripción"}), 404

    summary = file_manager.get_summary(class_id) or ""
    slides = file_manager.get_slides_document(class_id) or file_manager.get_slides(class_id) or ""
    class_name = class_id.split('/')[-1] if '/' in class_id else class_id

    try:
        result = gemini_service.generate_flashcards(transcription_text, summary, slides, class_name)
        from flask import Response
        return Response(
            result,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename="flashcards_{class_name}.txt"'
            }
        )
    except Exception as e:
        logger.error(f"Error generando flashcards: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/classes/<path:class_id>/exam', methods=['POST'])
def generate_exam(class_id):
    """Genera un examen simulado y devuelve el markdown."""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    transcription_text = file_manager.get_transcription_text(class_id)
    if not transcription_text:
        return jsonify({"error": "No se encontró la transcripción"}), 404

    summary = file_manager.get_summary(class_id) or ""
    slides = file_manager.get_slides_document(class_id) or file_manager.get_slides(class_id) or ""
    class_name = class_id.split('/')[-1] if '/' in class_id else class_id

    data = request.get_json(silent=True) or {}
    topic = data.get('topic', '').strip()

    try:
        result = gemini_service.generate_exam(transcription_text, summary, slides, class_name, topic)
        return jsonify({"exam": result})
    except Exception as e:
        logger.error(f"Error generando examen: {e}")
        return jsonify({"error": str(e)}), 500


@app.route('/api/classes/<path:class_id>/extract_activity', methods=['POST'])
def extract_activity(class_id):
    """Extrae información de una actividad específica."""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    transcription_text = file_manager.get_transcription_text(class_id)
    if not transcription_text:
        return jsonify({"error": "No se encontró la transcripción"}), 404

    data = request.get_json(silent=True) or {}
    activity_name = data.get('activity_name', '').strip()
    if not activity_name:
        return jsonify({"error": "Debe proporcionar el nombre de la actividad"}), 400

    summary = file_manager.get_summary(class_id) or ""
    slides = file_manager.get_slides_document(class_id) or file_manager.get_slides(class_id) or ""
    knowledge_text = file_manager.get_knowledge_text(class_id) or ""
    rubricas_text = file_manager.get_rubricas_text(class_id) or ""
    class_name = class_id.split('/')[-1] if '/' in class_id else class_id

    try:
        result = gemini_service.extract_activity(
            transcription_text, summary, slides,
            knowledge_text, rubricas_text, class_name, activity_name
        )
        return jsonify({"activity": result})
    except Exception as e:
        logger.error(f"Error extrayendo actividad: {e}")
        return jsonify({"error": str(e)}), 500


# ============== MANEJO DE ERRORES ==============

@app.errorhandler(413)
def request_entity_too_large(error):
    """Maneja errores de archivo muy grande"""
    max_mb = config.MAX_CONTENT_LENGTH / (1024 * 1024)
    return jsonify({
        "error": f"El archivo es demasiado grande. Máximo permitido: {max_mb:.0f} MB"
    }), 413


@app.errorhandler(500)
def internal_server_error(error):
    """Maneja errores internos del servidor"""
    return jsonify({
        "error": "Error interno del servidor",
        "message": str(error)
    }), 500


# ============== PUNTO DE ENTRADA ==============

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("V_T_R - Video Transcriptor y Resumen")
    logger.info("=" * 50)

    # Verificar configuración
    if not config.GEMINI_API_KEY:
        logger.warning("GEMINI_API_KEY no configurada. Algunas funciones no estarán disponibles.")

    if not config.OPENAI_API_KEY:
        logger.info("OPENAI_API_KEY no configurada. El respaldo de Whisper API no estará disponible.")

    try:
        import torch
        if torch.cuda.is_available():
            gpu_name = torch.cuda.get_device_name(0)
            logger.info(f"GPU detectada: {gpu_name}")
        else:
            logger.warning("CUDA no disponible. Whisper usará CPU (más lento).")
    except ImportError:
        logger.warning("PyTorch no está instalado. La transcripción local no estará disponible.")

    # Detectar IP de red local para mostrar acceso remoto
    import socket as _socket
    try:
        _s = _socket.socket(_socket.AF_INET, _socket.SOCK_DGRAM)
        _s.connect(("8.8.8.8", 80))
        _local_ip = _s.getsockname()[0]
        _s.close()
    except Exception:
        _local_ip = "127.0.0.1"

    logger.info(f"Servidor iniciando en http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    logger.info(f"Acceso red local: http://{_local_ip}:{config.FLASK_PORT}")
    logger.info("GPU local procesa todas las subidas (locales y remotas)")
    logger.info("=" * 50)

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        threaded=True,           # permite atender /api/process/status mientras procesa
        use_reloader=False       # evita la segunda ventana del reloader de Flask
    )
