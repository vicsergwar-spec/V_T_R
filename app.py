"""
V_T_R - Video Transcriptor y Resumen
Servidor Flask Principal
"""
import os
import logging
from pathlib import Path
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.utils import secure_filename

import config
from services import AudioExtractor, Transcriber, GeminiService, FileManager

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

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
    Procesa un video: extrae audio, transcribe, genera nombre y resumen
    """
    # Verificar que hay archivo
    if 'video' not in request.files:
        return jsonify({"error": "No se proporcionó archivo de video"}), 400

    video_file = request.files['video']

    if video_file.filename == '':
        return jsonify({"error": "Nombre de archivo vacío"}), 400

    # Verificar extensión
    filename = secure_filename(video_file.filename)
    ext = Path(filename).suffix.lower()

    if ext not in config.SUPPORTED_VIDEO_FORMATS:
        return jsonify({
            "error": f"Formato no soportado: {ext}",
            "supported": config.SUPPORTED_VIDEO_FORMATS
        }), 400

    # Verificar Gemini
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    # Obtener modelo de Whisper
    whisper_model = request.form.get('model', config.DEFAULT_WHISPER_MODEL)
    if whisper_model not in config.WHISPER_MODELS:
        whisper_model = config.DEFAULT_WHISPER_MODEL

    # Carpeta destino (opcional)
    folder_path = request.form.get('folder_path', '').strip()

    # Verificar que si se usa OpenAI, la key esté disponible
    if whisper_model == "openai" and not config.OPENAI_API_KEY:
        return jsonify({"error": "Se seleccionó OpenAI API pero OPENAI_API_KEY no está configurada en el servidor"}), 400

    video_path = None
    audio_path = None

    try:
        # 1. Guardar video temporal
        logger.info(f"Procesando video: {filename}")
        video_path = file_manager.save_video_to_temp(video_file, filename)

        # 2. Extraer audio
        logger.info("Extrayendo audio...")
        audio_path = audio_extractor.extract_audio(video_path)

        # 3. Transcribir
        logger.info(f"Transcribiendo con modelo {whisper_model}...")
        trans = get_transcriber(whisper_model)
        try:
            result = trans.transcribe(audio_path)
        except Exception as transcribe_error:
            logger.error(f"Error en transcripción con modelo '{whisper_model}': {transcribe_error}")
            file_manager.cleanup_temp_files(video_path, audio_path)
            video_path = None
            audio_path = None
            error_response = {
                "error": str(transcribe_error),
                "message": "Error al transcribir el audio"
            }
            # Si falló un modelo local y OpenAI está disponible, ofrecer la opción al usuario
            if whisper_model in ("small", "medium") and config.OPENAI_API_KEY:
                error_response["gpu_failed"] = True
                error_response["openai_available"] = True
            return jsonify(error_response), 500

        # 4. Generar nombre de carpeta
        logger.info("Generando nombre de carpeta...")
        folder_name = gemini_service.generate_folder_name(result["text"])

        # 5. Crear carpeta y guardar transcripción
        class_folder = file_manager.create_class_folder(folder_name, parent_path=folder_path)
        file_manager.save_transcription(result["segments"], class_folder)

        # 6. Generar y guardar resumen
        logger.info("Generando resumen...")
        summary = gemini_service.generate_summary(result["text"], folder_name)
        file_manager.save_summary(summary, class_folder)

        # 7. Limpiar archivos temporales
        logger.info("Limpiando archivos temporales...")
        file_manager.cleanup_temp_files(video_path, audio_path)

        # 8. Obtener información de la clase creada
        class_info = file_manager.get_class_by_id(class_folder.name)
        class_info["summary"] = summary

        logger.info(f"Procesamiento completado: {class_folder.name}")

        return jsonify({
            "success": True,
            "message": "Video procesado exitosamente",
            "class": class_info
        })

    except Exception as e:
        logger.error(f"Error procesando video: {e}")

        # Limpiar archivos temporales en caso de error
        if video_path:
            file_manager.cleanup_temp_files(video_path, audio_path)

        return jsonify({
            "error": str(e),
            "message": "Error al procesar el video"
        }), 500


# ============== RUTAS DE CHAT ==============

@app.route('/api/chat/<path:class_id>/start', methods=['POST'])
def start_chat(class_id):
    """Inicia (o restaura) una sesión de chat para una clase, cargando el historial guardado"""
    if not gemini_service:
        return jsonify({"error": "Gemini API no está configurado"}), 500

    transcription_text = file_manager.get_transcription_text(class_id)
    if not transcription_text:
        return jsonify({"error": "No se encontró la transcripción"}), 404

    # Restaurar historial y nombre de caché desde disco
    saved_history = file_manager.get_chat_history(class_id) or []
    saved_cache_name = file_manager.get_cache_name(class_id)

    new_cache_name = gemini_service.start_chat_session(
        class_id, transcription_text,
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
            saved_history = file_manager.get_chat_history(class_id) or []
            saved_cache_name = file_manager.get_cache_name(class_id)
            new_cache_name = gemini_service.start_chat_session(
                class_id, transcription_text,
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
        debug=config.FLASK_DEBUG
    )
