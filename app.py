"""
V_T_R - Video Transcriptor y Resumen
Servidor Flask Principal
"""
import os
import time
import threading
import subprocess
import logging
import collections
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import config
from services import AudioExtractor, Transcriber, GeminiService, FileManager, SlideExtractor

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────
# Buffer de logs en memoria (solo sesión actual)
# ──────────────────────────────────────────────────────────

_log_buffer = collections.deque(maxlen=2000)

# ──────────────────────────────────────────────────────────
# Estado del procesamiento en curso (para la barra de progreso)
# ──────────────────────────────────────────────────────────

_proc_status = {"step": "Esperando...", "percent": 0, "detail": ""}


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
CORS(app)

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

# SlideExtractor se inicializa si hay GOOGLE_VISION_API_KEY y está habilitado
slide_extractor = None
if config.GOOGLE_VISION_API_KEY and config.SLIDE_EXTRACTION_ENABLED:
    try:
        slide_extractor = SlideExtractor(
            vision_api_key=config.GOOGLE_VISION_API_KEY,
            gemini_api_key=config.GEMINI_API_KEY or None,
        )
        logger.info("SlideExtractor listo (Cloud Vision + Gemini Vision)")
    except Exception as e:
        logger.error(f"Error inicializando SlideExtractor: {e}")


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


@app.route('/static/<path:filename>')
def serve_static(filename):
    """Sirve archivos estáticos"""
    return send_from_directory('static', filename)


@app.route('/api/status', methods=['GET'])
def get_status():
    """Obtiene el estado del sistema"""
    gpu_available = False
    gpu_info = None

    try:
        import torch
        gpu_available = torch.cuda.is_available()
        if gpu_available:
            gpu_info = {
                "name": torch.cuda.get_device_name(0),
                "memory_total_gb": round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 2)
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
        # 1. Guardar video temporal
        _set_status("Guardando video...", 5)
        video_path = file_manager.save_video_to_temp(video_file, filename)

        # 2. Extraer audio
        _set_status("Extrayendo audio...", 15)
        audio_path = audio_extractor.extract_audio(video_path)

        # 3. Transcribir (proceso más pesado)
        _set_status(f"Transcribiendo con Whisper ({whisper_model})...", 22)
        trans = get_transcriber(whisper_model)
        try:
            result = trans.transcribe(audio_path)
        except Exception as transcribe_error:
            logger.error(f"Error en transcripción con modelo '{whisper_model}': {transcribe_error}")
            _set_status("Error en transcripción", 0)
            file_manager.cleanup_temp_files(video_path, audio_path)
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

        # 4. Extraer contenido de slides (proceso medio, requiere GOOGLE_VISION_API_KEY)
        slides_markdown = ""
        if slide_extractor:
            try:
                _set_status("Detectando cambios de escena...", 65)

                def _slides_progress(current, total, msg):
                    pct = 65 + round(20 * current / total) if total else 65
                    _set_status(
                        f"Analizando imagen {current} de {total}",
                        pct,
                        "Cloud Vision + Gemini Vision" if "visual" in msg.lower() else "Cloud Vision",
                    )

                slides = slide_extractor.extract_slides(
                    video_path=video_path,
                    temp_dir=str(config.TEMP_DIR),
                    progress_callback=_slides_progress,
                )
                slides_markdown = slide_extractor.format_slides_for_context(slides)
                n_useful = len([s for s in slides if s.get("text") or s.get("visual_description")])
                if slides_markdown:
                    logger.info(f"Slides extraídos: {n_useful} con contenido")
                else:
                    logger.info("No se encontró contenido en los slides del video")
            except Exception as e:
                logger.warning(f"Error extrayendo slides (continuando sin slides): {e}")

        # 5. Generar nombre de carpeta
        _set_status("Generando nombre de carpeta...", 87)
        context_for_naming = result["text"] + (slides_markdown[:2000] if slides_markdown else "")
        folder_name = gemini_service.generate_folder_name(context_for_naming)

        # 6. Crear carpeta y guardar archivos
        _set_status("Guardando transcripción e imágenes...", 91)
        class_folder = file_manager.create_class_folder(folder_name, parent_path=folder_path)
        file_manager.save_transcription(result["segments"], class_folder)
        if slides_markdown:
            file_manager.save_slides(slides_markdown, class_folder)

        # 7. Generar resumen con transcripción + slides (proceso ligero)
        _set_status("Generando resumen con Gemini...", 94)
        full_context = result["text"] + slides_markdown
        summary = gemini_service.generate_summary(full_context, folder_name)
        file_manager.save_summary(summary, class_folder)

        # 8. Limpiar y finalizar
        _set_status("¡Listo!", 100)
        file_manager.cleanup_temp_files(video_path, audio_path)

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

    except Exception as e:
        logger.error(f"Error procesando video: {e}")
        _set_status("Esperando...", 0)
        if video_path:
            file_manager.cleanup_temp_files(video_path, audio_path)
        return jsonify({
            "error": str(e),
            "message": "Error al procesar el video"
        }), 500


# ============== ESTADO DEL PROCESAMIENTO ==============

@app.route('/api/process/status', methods=['GET'])
def get_process_status():
    """Devuelve el paso actual del procesamiento para la barra de progreso."""
    return jsonify(_proc_status)


@app.route('/api/shutdown', methods=['POST'])
def shutdown_machine():
    """Apaga el equipo 3 segundos después de responder (da tiempo al frontend)."""
    def do_shutdown():
        time.sleep(3)
        logger.info("Apagando el equipo por solicitud del usuario...")
        subprocess.run(['shutdown', '-h', 'now'], check=False)

    threading.Thread(target=do_shutdown, daemon=True).start()
    return jsonify({"ok": True, "message": "El equipo se apagará en breve."})


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

    # ── Paleta ──────────────────────────────────────────────────────────────
    C_BG       = (248, 249, 250)   # fondo de página
    C_HEADER   = (30, 58, 138)     # azul oscuro: cabecera de slide
    C_WHITE    = (255, 255, 255)
    C_TEXT     = (31, 41, 55)      # gris oscuro: texto principal
    C_CAPTION  = (107, 114, 128)   # gris medio: pie de página
    C_VISUAL   = (234, 179, 8)     # amarillo: caja de diagrama
    C_VISUAL_BG= (255, 251, 235)   # fondo caja diagrama

    class SlidesPDF(FPDF):
        def header(self):
            if self.page_no() == 1:
                return
            self.set_font("Helvetica", "I", 7)
            self.set_text_color(*C_CAPTION)
            self.set_y(6)
            self.cell(0, 4, f"V_T_R · {class_name.replace('_', ' ')}", align="L")
            self.ln(3)
            self.set_draw_color(*C_CAPTION)
            self.set_line_width(0.2)
            self.line(10, self.get_y(), 200, self.get_y())
            self.ln(2)

        def footer(self):
            if self.page_no() == 1:
                return
            self.set_y(-12)
            self.set_font("Helvetica", "", 7)
            self.set_text_color(*C_CAPTION)
            self.cell(0, 4, f"Pág. {self.page_no() - 1}", align="C")

    pdf = SlidesPDF()
    pdf.set_margins(left=14, top=14, right=14)
    pdf.set_auto_page_break(auto=True, margin=16)
    pdf.set_page_background(C_BG)  # only in fpdf2

    # ── Portada ──────────────────────────────────────────────────────────────
    pdf.add_page()
    # Banda azul superior
    pdf.set_fill_color(*C_HEADER)
    pdf.rect(0, 0, 210, 50, "F")
    pdf.set_y(10)
    pdf.set_font("Helvetica", "B", 22)
    pdf.set_text_color(*C_WHITE)
    pdf.multi_cell(0, 10, "V_T_R", align="C")
    pdf.set_font("Helvetica", "", 10)
    pdf.multi_cell(0, 6, "Video Transcriptor y Resumen", align="C")

    pdf.set_y(60)
    pdf.set_font("Helvetica", "B", 16)
    pdf.set_text_color(*C_TEXT)
    clean_name = class_name.replace("_", " ")
    pdf.multi_cell(0, 8, clean_name, align="C")

    from datetime import datetime
    pdf.set_y(pdf.get_y() + 6)
    pdf.set_font("Helvetica", "", 9)
    pdf.set_text_color(*C_CAPTION)
    pdf.multi_cell(0, 5, f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}", align="C")

    # Contar slides con contenido (secciones ## Slide N)
    import re as _re
    n_slides = len(_re.findall(r"^## Slide \d+", slides_md, flags=_re.MULTILINE))
    pdf.set_y(pdf.get_y() + 4)
    pdf.multi_cell(0, 5, f"Total slides con contenido: {n_slides}", align="C")

    # ── Parsear secciones del Markdown ───────────────────────────────────────
    sections = []
    current = None
    for line in slides_md.splitlines():
        if line.startswith("## Slide "):
            if current:
                sections.append(current)
            current = {"header": line[3:], "text_lines": [], "visual": ""}
        elif current is not None:
            stripped = line.strip()
            if stripped.startswith("> "):          # cita → descripción visual
                current["visual"] = stripped[2:].strip()
            elif stripped in ("---", "**Texto en pantalla:**", "**Elemento visual detectado:**"):
                pass
            elif stripped:
                current["text_lines"].append(stripped)
    if current:
        sections.append(current)

    # ── Páginas de slides ─────────────────────────────────────────────────
    for sec in sections:
        pdf.add_page()

        # Cabecera del slide (banda azul)
        hdr_y = pdf.get_y()
        pdf.set_fill_color(*C_HEADER)
        pdf.set_text_color(*C_WHITE)
        pdf.set_font("Helvetica", "B", 11)
        pdf.cell(0, 8, sec["header"], fill=True, ln=True, align="L")
        pdf.ln(3)

        # Texto del slide
        if sec["text_lines"]:
            pdf.set_font("Helvetica", "", 10)
            pdf.set_text_color(*C_TEXT)
            for tl in sec["text_lines"]:
                # Sanitizar a latin-1 para fpdf core fonts
                safe = tl.encode("latin-1", errors="replace").decode("latin-1")
                pdf.multi_cell(0, 5, safe, align="L")
                pdf.ln(1)

        # Caja de diagrama / elemento visual
        if sec["visual"]:
            pdf.ln(3)
            x0 = pdf.get_x()
            y0 = pdf.get_y()
            pdf.set_fill_color(*C_VISUAL_BG)
            pdf.set_draw_color(*C_VISUAL)
            pdf.set_line_width(0.6)
            # Dibujar borde izquierdo amarillo
            pdf.line(x0, y0, x0, y0 + 20)

            pdf.set_x(x0 + 4)
            pdf.set_font("Helvetica", "B", 8)
            pdf.set_text_color(*[int(c * 0.6) for c in C_VISUAL])
            pdf.cell(0, 5, "ELEMENTO VISUAL / DIAGRAMA", ln=True)

            pdf.set_x(x0 + 4)
            pdf.set_font("Helvetica", "I", 9)
            pdf.set_text_color(*C_TEXT)
            safe_v = sec["visual"].encode("latin-1", errors="replace").decode("latin-1")
            pdf.multi_cell(0, 5, safe_v, align="L")
            pdf.ln(2)

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
        from flask import Response
        # Generar Markdown enriquecido usando format_slides_for_download
        from services.slide_extractor import SlideExtractor as _SE  # solo para el formatter
        # Parsear slides desde el markdown guardado para re-formatear
        md_content = slides_md  # usar directamente el slides.md guardado
        return Response(
            md_content,
            mimetype="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{safe_name}_slides.md"'
            },
        )

    # PDF
    try:
        pdf_bytes = _build_slides_pdf(class_id, safe_name, slides_md)
        from flask import Response
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


# ============== RUTAS DE CHAT ==============

@app.route('/api/chat/<path:class_id>/start', methods=['POST'])
def start_chat(class_id):
    """Inicia (o restaura) una sesión de chat para una clase, cargando el historial guardado"""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    transcription_text = file_manager.get_transcription_text(class_id)
    if not transcription_text:
        return jsonify({"error": "No se encontró la transcripción"}), 404

    # Enriquecer con contenido de slides si existe
    slides_content = file_manager.get_slides(class_id) or ""

    # Restaurar historial y nombre de caché desde disco
    saved_history = file_manager.get_chat_history(class_id) or []
    saved_cache_name = file_manager.get_cache_name(class_id)

    new_cache_name = gemini_service.start_chat_session(
        class_id, transcription_text,
        slides_content=slides_content,
        history=saved_history,
        cached_content_name=saved_cache_name,
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

    if not data or 'message' not in data:
        return jsonify({"error": "Se requiere un mensaje"}), 400

    user_message = data['message'].strip()

    if not user_message:
        return jsonify({"error": "El mensaje no puede estar vacío"}), 400

    try:
        # Si no hay sesión activa en memoria, restaurar desde disco
        if class_id not in gemini_service.chat_sessions:
            transcription_text = file_manager.get_transcription_text(class_id)
            if not transcription_text:
                return jsonify({"error": "No se encontró la transcripción"}), 404
            slides_content = file_manager.get_slides(class_id) or ""
            saved_history = file_manager.get_chat_history(class_id) or []
            saved_cache_name = file_manager.get_cache_name(class_id)
            new_cache_name = gemini_service.start_chat_session(
                class_id, transcription_text,
                slides_content=slides_content,
                history=saved_history,
                cached_content_name=saved_cache_name,
            )
            if new_cache_name and new_cache_name != saved_cache_name:
                file_manager.save_cache_name(class_id, new_cache_name)

        # Enviar mensaje
        response = gemini_service.chat(class_id, user_message)

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

    return jsonify({
        "success": True,
        "message": "Historial de chat limpiado"
    })


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

    logger.info(f"Servidor iniciando en http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    logger.info("=" * 50)

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=config.FLASK_DEBUG,
        use_reloader=False   # evita la segunda ventana del reloader de Flask
    )
