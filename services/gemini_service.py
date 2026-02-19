"""
Servicio de interacción con Google Gemini API
"""
import logging
from datetime import datetime
from typing import Optional
import google.generativeai as genai

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GeminiService:
    """Servicio para interactuar con Google Gemini API"""

    def __init__(self, api_key: str, model_name: str = "gemini-3-flash-preview"):
        """
        Inicializa el servicio de Gemini.

        Args:
            api_key: API key de Google Gemini
            model_name: Nombre del modelo a usar
        """
        if not api_key:
            raise ValueError("Se requiere una API key de Gemini")

        genai.configure(api_key=api_key)
        self._model_name = model_name  # guardado para crear instancias por sesión
        self.model = genai.GenerativeModel(model_name)
        self.chat_sessions = {}  # Almacena sesiones de chat por clase
        logger.info(f"Servicio Gemini inicializado con modelo: {model_name}")

    def generate_folder_name(self, transcription_text: str) -> str:
        """
        Genera un nombre corto de carpeta basado en el contenido de la clase.

        Args:
            transcription_text: Texto completo de la transcripción

        Returns:
            Nombre de carpeta en formato Materia_Tema
        """
        # Tomar solo los primeros 3000 caracteres para el análisis
        sample_text = transcription_text[:3000]

        prompt = f"""Analiza el siguiente texto de una clase académica y genera un nombre de carpeta corto pero descriptivo.

REGLAS ESTRICTAS:
1. Formato: Materia_Tema (usar guiones bajos, no espacios)
2. Máximo 50 caracteres en total
3. Solo letras, números y guiones bajos
4. Primera letra de cada palabra en mayúscula
5. Ser lo más específico posible sobre el tema

EJEMPLOS:
- Sistemas_Computacionales_Git_Control_Versiones
- Calculo_Integral_Derivadas_Parciales
- Historia_Mexico_Revolucion_1910
- Programacion_Python_Funciones_Lambda
- Fisica_Cinematica_Movimiento_Rectilineo

TEXTO DE LA CLASE:
{sample_text}

Responde SOLO con el nombre de la carpeta, sin explicaciones ni comillas."""

        try:
            response = self.model.generate_content(prompt)
            folder_name = response.text.strip()

            # Limpiar el nombre
            folder_name = folder_name.replace(" ", "_")
            folder_name = folder_name.replace("-", "_")
            folder_name = "".join(c for c in folder_name if c.isalnum() or c == "_")

            # Asegurar que no exceda el límite
            if len(folder_name) > 50:
                folder_name = folder_name[:50]

            # Si está vacío, usar un nombre por defecto
            if not folder_name:
                folder_name = f"Clase_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            logger.info(f"Nombre de carpeta generado: {folder_name}")
            return folder_name

        except Exception as e:
            logger.error(f"Error al generar nombre de carpeta: {e}")
            return f"Clase_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

    def generate_summary(self, transcription_text: str, folder_name: str) -> str:
        """
        Genera un resumen estructurado de la clase.

        Args:
            transcription_text: Texto completo de la transcripción
            folder_name: Nombre de la carpeta/clase

        Returns:
            Resumen en formato Markdown
        """
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        # Limitar el texto para no exceder los límites del modelo (~25k tokens)
        max_chars = 100000
        if len(transcription_text) > max_chars:
            transcription_text = transcription_text[:max_chars] + "\n\n[... Transcripción truncada por longitud ...]"
            logger.warning("Transcripción truncada para resumen por exceder el límite de caracteres")

        prompt = f"""Eres un asistente académico experto. Analiza la siguiente transcripción de una clase y genera un resumen estructurado.

TRANSCRIPCIÓN DE LA CLASE:
{transcription_text}

GENERA UN RESUMEN EN FORMATO MARKDOWN CON ESTA ESTRUCTURA EXACTA:

# {folder_name.replace('_', ' ')}

## Fecha de procesamiento
{current_date}

## Puntos principales
(Lista los puntos más importantes de la clase, en formato de viñetas)

## Lo más importante para estudiar
(Identifica los conceptos clave que el estudiante debe dominar, explica brevemente cada uno)

## Tareas o pendientes mencionadas
(Si el profesor menciona tareas, trabajos, fechas de examen o cualquier pendiente, listarlo aquí. Si no hay ninguno, indicar "No se mencionaron tareas o pendientes en esta clase.")

INSTRUCCIONES ADICIONALES:
- Sé conciso pero completo
- Usa viñetas para mejor legibilidad
- Destaca términos técnicos importantes con **negritas**
- Si hay fórmulas o conceptos técnicos, explícalos brevemente
- El resumen debe ser útil para estudiar antes de un examen"""

        try:
            response = self.model.generate_content(prompt)
            summary = response.text.strip()
            logger.info("Resumen generado exitosamente")
            return summary

        except Exception as e:
            logger.error(f"Error al generar resumen: {e}")
            # Retornar un resumen básico en caso de error
            return f"""# {folder_name.replace('_', ' ')}

## Fecha de procesamiento
{current_date}

## Error
No se pudo generar el resumen automáticamente. Por favor, revisa la transcripción directamente.
"""

    def start_chat_session(
        self,
        class_id: str,
        transcription_text: str,
        history: list = None
    ) -> None:
        """
        Inicia (o restaura) una sesión de chat para una clase.

        Args:
            class_id: Identificador único de la clase
            transcription_text: Texto completo de la transcripción
            history: Historial previo a restaurar (lista de {role, content}). Si es None se empieza vacío.
        """
        system_instruction = f"""Eres un asistente de estudio especializado. Tu trabajo es ayudar al estudiante a entender y estudiar el contenido de una clase grabada.

TRANSCRIPCIÓN DE LA CLASE:
{transcription_text}

INSTRUCCIONES:
1. Responde ÚNICAMENTE basándote en el contenido de la transcripción
2. Si algo no está en la transcripción, di claramente "Eso no se menciona en esta clase"
3. Sé claro y didáctico en tus explicaciones
4. Si el estudiante pregunta sobre un tema, proporciona ejemplos de la clase si los hay
5. Puedes ayudar a resumir secciones específicas, explicar conceptos, o preparar para exámenes
6. Usa un tono amigable pero académico"""

        # Modelo con system_instruction por sesión — la transcripción se envía UNA sola vez
        # y Gemini Flash la cachea implícitamente, reduciendo tokens en turnos siguientes
        session_model = genai.GenerativeModel(
            self._model_name,
            system_instruction=system_instruction
        )

        # Convertir historial guardado al formato nativo del SDK
        sdk_history = [
            {"role": msg["role"], "parts": [msg["content"]]}
            for msg in (history or [])
        ]

        self.chat_sessions[class_id] = {
            "chat": session_model.start_chat(history=sdk_history),
            "history": list(history) if history else [],
        }
        action = "restaurada" if history else "iniciada"
        logger.info(f"Sesión de chat {action} para clase: {class_id} ({len(self.chat_sessions[class_id]['history'])} mensajes previos)")

    def chat(self, class_id: str, user_message: str) -> str:
        """
        Envía un mensaje en la sesión de chat de una clase.

        Args:
            class_id: Identificador de la clase
            user_message: Mensaje del usuario

        Returns:
            Respuesta de Gemini
        """
        if class_id not in self.chat_sessions:
            raise ValueError(f"No hay sesión de chat activa para la clase: {class_id}")

        session = self.chat_sessions[class_id]

        try:
            # Enviar solo el nuevo mensaje; el historial y system_instruction
            # ya viven en el objeto chat del SDK (no se reenvían desde cero)
            response = session["chat"].send_message(user_message)
            assistant_message = response.text.strip()

            # Guardar en historial local (para persistencia en disco)
            session["history"].append({"role": "user", "content": user_message})
            session["history"].append({"role": "model", "content": assistant_message})

            logger.info(f"Chat respondido para clase: {class_id}")
            return assistant_message

        except Exception as e:
            logger.error(f"Error en chat: {e}")
            return f"Lo siento, hubo un error al procesar tu pregunta. Por favor, intenta de nuevo."

    def clear_chat_history(self, class_id: str) -> bool:
        """
        Limpia el historial de chat de una clase.

        Args:
            class_id: Identificador de la clase

        Returns:
            True si se limpió exitosamente
        """
        if class_id in self.chat_sessions:
            self.chat_sessions[class_id]["history"] = []
            logger.info(f"Historial de chat limpiado para clase: {class_id}")
            return True
        return False

    def get_chat_history(self, class_id: str) -> list:
        """
        Obtiene el historial de chat de una clase.

        Args:
            class_id: Identificador de la clase

        Returns:
            Lista de mensajes del historial
        """
        if class_id in self.chat_sessions:
            return self.chat_sessions[class_id]["history"]
        return []

    def end_chat_session(self, class_id: str) -> None:
        """
        Termina una sesión de chat.

        Args:
            class_id: Identificador de la clase
        """
        if class_id in self.chat_sessions:
            del self.chat_sessions[class_id]
            logger.info(f"Sesión de chat terminada para clase: {class_id}")
