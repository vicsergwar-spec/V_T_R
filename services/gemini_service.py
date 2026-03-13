"""
Servicio de interacción con Google Gemini API
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
import google.generativeai as genai

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

    def generate_slides_document(
        self,
        slides_raw: str,
        class_name: str,
        image_map: dict = None,
    ) -> str:
        """
        Genera un documento de estudio estructurado a partir del contenido
        en crudo de los slides (OCR + descripciones visuales).

        Args:
            slides_raw: Contenido de slides.md (formato ## Slide N [MM:SS])
            class_name: Nombre de la clase
            image_map: Dict {slide_num: [rutas relativas de imágenes]} para vincular

        Returns:
            Documento Markdown estructurado y optimizado para lectura y chat IA
        """
        if not slides_raw or not slides_raw.strip():
            return ""

        # Filtrar slides con contenido de UI/navegación (campus virtual, menús, etc.)
        slides_raw = self._filter_ui_slides(slides_raw)
        if not slides_raw.strip():
            return ""

        max_chars = 80000
        if len(slides_raw) > max_chars:
            slides_raw = slides_raw[:max_chars] + "\n\n[... contenido truncado ...]"

        readable_name = class_name.replace('_', ' ')

        # Construir catálogo de imágenes para el prompt
        image_catalog = ""
        if image_map:
            img_lines = ["## CATÁLOGO DE IMÁGENES DISPONIBLES",
                         "Usa estas rutas exactas al referenciar figuras en el documento:"]
            for slide_num, paths in sorted(image_map.items()):
                for p in paths:
                    img_lines.append(f"- Slide {slide_num}: `{p}`")
            image_catalog = "\n".join(img_lines) + "\n\n"

        prompt = f"""Eres un asistente académico experto. Se te proporcionan los slides \
extraídos automáticamente de un video de clase mediante OCR y análisis visual.

CONTENIDO DE LOS SLIDES (datos en crudo):
{slides_raw}

{image_catalog}Tu tarea es transformar estos datos en un **documento de estudio denso y optimizado** \
en formato Markdown. Sigue estas reglas ESTRICTAS:

## FORMATO DE SALIDA OBLIGATORIO

Empieza el documento con un bloque YAML frontmatter:
```
---
title: "{readable_name}"
date: (fecha actual YYYY-MM-DD)
type: slides
tokens_hint: dense
---
```

## REGLAS DE ESTRUCTURA

1. **Organiza el contenido por temas**, NO por número de slide. Agrupa slides relacionados.
2. **Limpia artefactos de OCR**: corrige errores tipográficos evidentes, elimina texto repetido \
o fragmentos de interfaz (botones, menús, etc.).
3. **Estructura con encabezados claros**: usa ## para secciones principales y ### para subsecciones.
4. **Conserva TODO el contenido académico**: no omitas información.
5. **Usa viñetas y listas** para información que se preste a ello.
6. **Destaca conceptos clave** con **negritas**.
7. NO agregues contenido inventado. Solo organiza y limpia lo que ya existe.
8. NO incluyas los números de slide ni timestamps en el documento final.
9. **ELIMINA datos flotantes**: NO dejes años sueltos (ej: "1946", "1837"), siglas aisladas \
(ej: "BLUEGENE/L", "IBM") ni fragmentos sin contexto. Todo dato DEBE estar dentro de \
una tabla, lista con viñetas, o párrafo con oración completa.
10. **NO dejes líneas huérfanas**: cada dato numérico, nombre o sigla debe estar integrado \
en una estructura lógica (tabla, lista o párrafo). Si un fragmento no encaja en ninguna, \
descártalo como artefacto de OCR.

## TABLAS DENSAS (OBLIGATORIO)

Cuando haya datos tabulares, comparaciones, listas de características, líneas de tiempo \
o cualquier información que se pueda estructurar como tabla, USA TABLAS MARKDOWN:

| Columna1 | Columna2 | Columna3 |
|----------|----------|----------|
| dato     | dato     | dato     |

Ejemplo para líneas de tiempo históricas:
| Año | Hito | Descripción |
|-----|------|-------------|

## DIAGRAMAS MERMAID (OBLIGATORIO para elementos visuales)

Cuando un slide contenga diagramas, flujos, líneas de tiempo, esquemas o relaciones \
(marcados con > en los datos), GENERA un bloque de código Mermaid equivalente.

Usa estos tipos de diagrama según corresponda:
- `timeline` para líneas de tiempo
- `graph TD` o `graph LR` para flujos y esquemas
- `flowchart` para procesos
- `classDiagram` para relaciones entre entidades

Ejemplo:
```mermaid
timeline
    title Evolución de la computación
    1837 : Máquina Analítica (Babbage)
    1946 : ENIAC
```

## FIGURAS CON IMÁGENES (OBLIGATORIO)

Para cada fotografía o imagen relevante del catálogo de imágenes, inserta una figura \
con descripción técnica usando esta sintaxis EXACTA:

<figure class="slide-figure" data-src="RUTA_DE_IMAGEN">
<figcaption>📷 Descripción técnica breve de la imagen</figcaption>
</figure>

Donde RUTA_DE_IMAGEN es la ruta exacta del catálogo (ej: slide_images/slide_001.jpg).
Incluye TODAS las imágenes relevantes del catálogo en el punto temático donde correspondan.
NO uses el formato *[Diagrama: ...]* ni *[Figura: ...]*

NOMBRE DE LA CLASE: {readable_name}

Responde SOLO con el documento Markdown (incluyendo el frontmatter YAML), sin explicaciones adicionales."""

        try:
            response = self.model.generate_content(prompt)
            document = response.text.strip()
            # Filtro post-generación: eliminar líneas basura flotantes
            document = self._clean_floating_fragments(document)
            logger.info("Documento de slides generado exitosamente")
            return document
        except Exception as e:
            logger.error(f"Error al generar documento de slides: {e}")
            return ""

    @staticmethod
    def _clean_floating_fragments(document: str) -> str:
        """
        Elimina fragmentos de texto flotante que no pertenecen a ninguna
        estructura lógica (tabla, lista, párrafo, bloque de código, figure).
        Ejemplos: años sueltos como '1946', siglas como 'BLUEGENE/L',
        palabras truncadas como 'es de compu'.
        """
        import re

        lines = document.split('\n')
        cleaned = []
        in_code_block = False
        in_table = False
        in_figure = False

        for i, line in enumerate(lines):
            stripped = line.strip()

            # Rastrear bloques de código
            if stripped.startswith('```'):
                in_code_block = not in_code_block
                cleaned.append(line)
                continue
            if in_code_block:
                cleaned.append(line)
                continue

            # Rastrear figures HTML
            if '<figure' in stripped:
                in_figure = True
            if '</figure>' in stripped:
                in_figure = False
                cleaned.append(line)
                continue
            if in_figure:
                cleaned.append(line)
                continue

            # Rastrear tablas
            if stripped.startswith('|') and '|' in stripped[1:]:
                in_table = True
                cleaned.append(line)
                continue
            if in_table and not stripped.startswith('|'):
                in_table = False

            # Preservar siempre: encabezados, listas, frontmatter, separadores, vacías
            if (stripped.startswith('#') or stripped.startswith('-')
                    or stripped.startswith('*') or stripped.startswith('>')
                    or stripped.startswith('|') or stripped == '---'
                    or stripped == '' or re.match(r'^\d+\.\s+', stripped)):
                cleaned.append(line)
                continue

            # Detectar líneas basura flotantes:
            # - Solo un año (4 dígitos)
            # - Solo una sigla corta (1-3 palabras, < 30 chars, sin verbo)
            # - Fragmentos truncados muy cortos sin puntuación final
            if re.match(r'^\d{4}$', stripped):
                # Año suelto
                continue
            if re.match(r'^[A-Z0-9_/\s\.\-]{1,30}$', stripped) and len(stripped.split()) <= 3:
                # Sigla o nombre aislado en mayúsculas (ej: "IBM", "BLUEGENE / L")
                # Verificar que no sea un encabezado legítimo sin #
                if not any(c.islower() for c in stripped):
                    continue
            if (len(stripped) < 40 and not stripped.endswith('.')
                    and not stripped.endswith(':') and not stripped.endswith(')')
                    and not stripped.startswith('<') and not stripped.startswith('!')
                    and re.match(r'^[a-záéíóúñ\s,]+$', stripped, re.IGNORECASE)
                    and len(stripped.split()) <= 5):
                # Fragmento truncado corto sin contexto (ej: "es de compu", "ones de computac")
                continue

            cleaned.append(line)

        return '\n'.join(cleaned)

    @staticmethod
    def _filter_ui_slides(slides_raw: str) -> str:
        """
        Filtra slides que contienen primariamente contenido de UI/navegación
        (campus virtual, menús, listados de pestañas, etc.) y no contenido académico.
        """
        import re

        # Palabras clave que indican contenido de UI/navegación de campus virtual
        ui_keywords = [
            'campusvirtual', 'mod/lti/view', 'Mis cursos', 'Servicios para estudiantes',
            'Tutorías Atención Técnica', 'Envío de actividades', 'Resultado de actividades',
            'Calificaciones finales', 'Exámenes finales', 'Revisiones y citas',
            'Herramienta externa', 'Configuración', 'Unirse a la clase',
            'Filtrar por', 'Próximas clases', 'Clases grabadas',
            'Calificar asistencia', 'Sin comenzar', 'En progreso',
        ]
        ui_pattern = re.compile('|'.join(re.escape(kw) for kw in ui_keywords), re.IGNORECASE)

        sections = re.split(r'(?=^## Slide \d+)', slides_raw, flags=re.MULTILINE)
        kept = []
        for section in sections:
            if not section.strip():
                continue
            # Si la sección tiene más de 3 coincidencias de UI, es navegación
            matches = ui_pattern.findall(section)
            if len(matches) >= 3:
                # Extraer número de slide para log
                m = re.match(r'## Slide (\d+)', section)
                num = m.group(1) if m else '?'
                logger.info(f"Slide {num} filtrado: contenido de UI/navegación ({len(matches)} coincidencias)")
                continue
            kept.append(section)

        return '\n'.join(kept)

    def _build_cached_model(self, system_instruction: str, existing_cache_name: str = None):
        """
        Intenta crear/recuperar un caché de Gemini para la transcripción.
        Devuelve (model, cache_name | None).
        Si el caché no está disponible o la transcripción es muy corta, hace fallback
        a system_instruction estándar y devuelve cache_name=None.
        """
        # 1. Intentar recuperar caché existente
        if existing_cache_name:
            try:
                cache = genai.caching.CachedContent.get(existing_cache_name)
                model = genai.GenerativeModel.from_cached_content(cached_content=cache)
                logger.info(f"Caché de Gemini reutilizado: {existing_cache_name}")
                return model, existing_cache_name
            except Exception:
                logger.info("Caché anterior expirado o inválido, creando uno nuevo")

        # 2. Crear nuevo caché
        try:
            cache = genai.caching.CachedContent.create(
                model=f"models/{self._model_name}",
                system_instruction=system_instruction,
                ttl=timedelta(hours=1),
            )
            model = genai.GenerativeModel.from_cached_content(cached_content=cache)
            logger.info(f"Caché de Gemini creado: {cache.name}")
            return model, cache.name
        except Exception as e:
            # Fallback: transcripción muy corta (< mínimo tokens), API sin soporte, etc.
            logger.warning(
                f"Context caching no disponible ({type(e).__name__}), "
                "usando system_instruction estándar"
            )
            model = genai.GenerativeModel(
                self._model_name,
                system_instruction=system_instruction,
            )
            return model, None

    def start_chat_session(
        self,
        class_id: str,
        transcription_text: str,
        slides_content: str = "",
        history: list = None,
        cached_content_name: str = None,
        knowledge_text: str = "",
        rubricas_text: str = "",
        context_images: list = None,
    ) -> Optional[str]:
        """
        Inicia (o restaura) una sesión de chat para una clase.

        Args:
            class_id:             Identificador único de la clase
            transcription_text:   Texto completo de la transcripción (audio)
            slides_content:       Contenido extraído de los slides (visual), opcional
            history:              Historial previo a restaurar. Si es None se empieza vacío.
            cached_content_name:  Nombre de caché de Gemini guardado previamente.
            knowledge_text:       Texto de archivos de conocimiento extra (se guarda en RAM).
            rubricas_text:        Texto de rúbricas (se guarda en RAM).

        Returns:
            El nombre del caché usado/creado (para persistirlo), o None si no se usó caché.
        """
        if slides_content.strip():
            system_instruction = f"""Eres un asistente de estudio especializado. \
Tu trabajo es ayudar al estudiante a entender y estudiar el contenido de una clase grabada.

Tienes acceso a DOS fuentes de información de la misma clase:

═══════════════════════════════════════════
 FUENTE 1 · TRANSCRIPCIÓN DE AUDIO
 (lo que se DIJO durante la clase)
═══════════════════════════════════════════
{transcription_text}

═══════════════════════════════════════════
 FUENTE 2 · CONTENIDO DE SLIDES / PANTALLA
 (lo que se MOSTRÓ en el video)
═══════════════════════════════════════════
{slides_content}

INSTRUCCIONES:
1. Responde ÚNICAMENTE basándote en las fuentes anteriores.
2. Si algo no aparece en ninguna de las dos fuentes, di claramente \
"Eso no se menciona en esta clase".
3. SIEMPRE indica de dónde viene la información:
   - Si se DIJO en clase → añade al final: *(📢 mencionado en clase)*
   - Si se VIO en los slides → añade al final: *(📊 visto en slides)*
   - Si aparece en ambas → menciona ambas fuentes.
4. Sé claro y didáctico. Usa ejemplos de la clase si los hay.
5. Puedes resumir secciones, explicar conceptos o preparar al estudiante para exámenes.
6. Usa un tono amigable pero académico."""
        else:
            system_instruction = f"""Eres un asistente de estudio especializado. \
Tu trabajo es ayudar al estudiante a entender y estudiar el contenido de una clase grabada.

TRANSCRIPCIÓN DE LA CLASE:
{transcription_text}

INSTRUCCIONES:
1. Responde ÚNICAMENTE basándote en el contenido de la transcripción.
2. Si algo no está en la transcripción, di claramente "Eso no se menciona en esta clase".
3. Sé claro y didáctico en tus explicaciones.
4. Si el estudiante pregunta sobre un tema, proporciona ejemplos de la clase si los hay.
5. Puedes ayudar a resumir secciones específicas, explicar conceptos, o preparar para exámenes.
6. Usa un tono amigable pero académico."""

        session_model, cache_name = self._build_cached_model(system_instruction, cached_content_name)

        sdk_history = [
            {"role": msg["role"], "parts": [msg["content"]]}
            for msg in (history or [])
        ]

        self.chat_sessions[class_id] = {
            "chat": session_model.start_chat(history=sdk_history),
            "history": list(history) if history else [],
            "knowledge_text": knowledge_text or "",
            "rubricas_text": rubricas_text or "",
            "context_images": context_images or [],
        }
        action = "restaurada" if history else "iniciada"
        logger.info(
            f"Sesión de chat {action} para clase: {class_id} "
            f"({len(self.chat_sessions[class_id]['history'])} mensajes previos, "
            f"caché: {'sí' if cache_name else 'no'}, "
            f"imágenes: {len(self.chat_sessions[class_id]['context_images'])})"
        )
        return cache_name

    def _is_cache_not_found_error(self, error: Exception) -> bool:
        """Detecta si el error es un 403 CachedContent not found."""
        err_str = str(error).lower()
        return (
            "cachedcontent" in err_str
            or "cached_content" in err_str
            or ("403" in err_str and "not found" in err_str)
        )

    def _rebuild_session(self, session_key: str, file_manager) -> None:
        """
        Reconstruye una sesión de chat tras un error de caché expirado.
        Detecta si es clase o carpeta por el prefijo __folder__.
        """
        # Preservar historial actual antes de limpiar
        old_history = self.chat_sessions.get(session_key, {}).get("history", [])

        # Limpiar sesión en memoria
        if session_key in self.chat_sessions:
            del self.chat_sessions[session_key]

        is_folder = session_key.startswith("__folder__")

        if is_folder:
            folder_path = session_key[len("__folder__"):]

            # Limpiar caché en disco
            file_manager.delete_folder_cache_name(folder_path)

            # Reconstruir sesión de carpeta
            classes_content = file_manager.get_folder_all_content(folder_path)
            folder_name = folder_path.split("/")[-1].replace("_", " ")
            context_images = file_manager.get_context_images_data(folder_path)

            new_cache_name = self.start_folder_chat_session(
                folder_id=session_key,
                folder_name=folder_name,
                classes_content=classes_content,
                history=old_history,
                cached_content_name=None,  # Forzar nuevo caché
                context_images=context_images,
            )
            if new_cache_name:
                file_manager.save_folder_cache_name(folder_path, new_cache_name)

        else:
            class_id = session_key

            # Limpiar caché en disco
            file_manager.delete_cache_name(class_id)

            # Reconstruir sesión de clase
            transcription_text = file_manager.get_transcription_text(class_id) or ""
            slides_content = file_manager.get_slides_document(class_id) \
                or file_manager.get_slides(class_id) or ""
            knowledge_text = file_manager.get_knowledge_text(class_id) or ""
            rubricas_text = file_manager.get_rubricas_text(class_id) or ""
            context_images = file_manager.get_context_images_data(class_id)

            new_cache_name = self.start_chat_session(
                class_id,
                transcription_text,
                slides_content=slides_content,
                history=old_history,
                cached_content_name=None,  # Forzar nuevo caché
                knowledge_text=knowledge_text,
                rubricas_text=rubricas_text,
                context_images=context_images,
            )
            if new_cache_name:
                file_manager.save_cache_name(class_id, new_cache_name)

        logger.info(f"Sesión reconstruida tras error de caché: {session_key}")

    def chat(self, class_id: str, user_message: str, file_manager=None) -> str:
        """
        Envía un mensaje en la sesión de chat de una clase.

        Args:
            class_id: Identificador de la clase (o session_key para carpetas)
            user_message: Mensaje del usuario
            file_manager: Referencia al FileManager para auto-recovery de caché

        Returns:
            Respuesta de Gemini
        """
        if class_id not in self.chat_sessions:
            raise ValueError(f"No hay sesión de chat activa para la clase: {class_id}")

        session = self.chat_sessions[class_id]

        try:
            return self._send_chat_message(class_id, session, user_message)

        except Exception as e:
            # Si es error de CachedContent y tenemos file_manager, auto-recovery
            if file_manager and self._is_cache_not_found_error(e):
                logger.warning(
                    f"CachedContent expirado para {class_id}, reconstruyendo sesión..."
                )
                try:
                    self._rebuild_session(class_id, file_manager)
                    session = self.chat_sessions[class_id]
                    return self._send_chat_message(class_id, session, user_message)
                except Exception as retry_err:
                    logger.error(f"Error en retry tras reconstruir sesión: {retry_err}")
                    return "Lo siento, hubo un error al procesar tu pregunta. Por favor, intenta de nuevo."

            logger.error(f"Error en chat: {e}")
            return "Lo siento, hubo un error al procesar tu pregunta. Por favor, intenta de nuevo."

    def _send_chat_message(self, class_id: str, session: dict, user_message: str) -> str:
        """Envía el mensaje y actualiza el historial. Lanza excepciones sin capturar."""
        enriched_message = self._prepend_extra_context(
            user_message,
            session.get("knowledge_text", ""),
            session.get("rubricas_text", ""),
        )

        context_images = session.get("context_images", [])
        if context_images:
            message_parts = [enriched_message]
            for img in context_images:
                message_parts.append({
                    "mime_type": img["mime_type"],
                    "data": img["data"],
                })
            response = session["chat"].send_message(message_parts)
        else:
            response = session["chat"].send_message(enriched_message)

        assistant_message = response.text.strip()

        session["history"].append({"role": "user", "content": user_message})
        session["history"].append({"role": "model", "content": assistant_message})

        logger.info(f"Chat respondido para clase: {class_id}")
        return assistant_message

    @staticmethod
    def _prepend_extra_context(user_message: str, knowledge_text: str, rubricas_text: str) -> str:
        """Prepend knowledge and rubrics blocks to the user message if they exist."""
        parts = []
        if knowledge_text and knowledge_text.strip():
            parts.append(f"[CONOCIMIENTO EXTRA]\n{knowledge_text}\n[/CONOCIMIENTO EXTRA]")
        if rubricas_text and rubricas_text.strip():
            parts.append(f"[RÚBRICAS]\n{rubricas_text}\n[/RÚBRICAS]")
        if parts:
            parts.append(user_message)
            return "\n\n".join(parts)
        return user_message

    def clear_chat_history(self, class_id: str) -> bool:
        """
        Limpia el historial de chat de una clase.
        Elimina la sesión completa para que se re-inicialice limpia en el
        próximo mensaje (el objeto chat del SDK mantiene historial interno).

        Args:
            class_id: Identificador de la clase

        Returns:
            True si se limpió exitosamente
        """
        if class_id in self.chat_sessions:
            del self.chat_sessions[class_id]
            logger.info(f"Sesión de chat eliminada para clase: {class_id}")
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

    # ──────────────────────────────────────────────────────────
    # Chat general de carpeta
    # ──────────────────────────────────────────────────────────

    def start_folder_chat_session(
        self,
        folder_id: str,
        folder_name: str,
        classes_content: list,
        history: list = None,
        cached_content_name: str = None,
        knowledge_text: str = "",
        rubricas_text: str = "",
        context_images: list = None,
    ) -> Optional[str]:
        """
        Inicia (o restaura) una sesión de chat para una carpeta completa.
        El contexto incluye toda la información de todas las clases de la carpeta.

        Args:
            folder_id:            ID único de la carpeta (su ruta relativa)
            folder_name:          Nombre legible de la carpeta
            classes_content:      Lista de dicts {"name", "transcription", "summary", "slides"}
            history:              Historial previo a restaurar
            cached_content_name:  Nombre de caché existente a reutilizar

        Returns:
            El nombre del caché usado/creado, o None si no se usó caché
        """
        MAX_TRANSCRIPTION = 30_000
        MAX_SUMMARY = 3_000
        MAX_SLIDES = 8_000

        parts = [
            f"Eres un asistente académico especializado. Tienes acceso al contenido "
            f"COMPLETO de la carpeta «{folder_name}» que contiene "
            f"{len(classes_content)} clase(s) grabada(s).\n",
            "INSTRUCCIONES IMPORTANTES:",
            "1. Responde ÚNICAMENTE basándote en el contenido de las clases mostradas.",
            "2. Indica siempre de qué clase proviene la información: *(📚 Clase: Nombre)*",
            "3. Si algo no aparece en ninguna clase, di: "
            "\"Eso no se menciona en las clases de esta carpeta\".",
            "4. Puedes comparar y relacionar conceptos entre distintas clases.",
            "5. Sé claro y didáctico. Usa ejemplos del contenido cuando los haya.",
            "6. Usa un tono amigable pero académico.\n",
        ]

        for i, cls in enumerate(classes_content, 1):
            sep = "═" * 60
            parts.append(sep)
            parts.append(f"CLASE {i}: {cls['name']}")
            parts.append(sep)

            if cls.get("summary"):
                summary = cls["summary"][:MAX_SUMMARY]
                parts.append("\n📋 RESUMEN:")
                parts.append(summary)
                if len(cls["summary"]) > MAX_SUMMARY:
                    parts.append("[... resumen truncado ...]")

            if cls.get("transcription"):
                transcription = cls["transcription"][:MAX_TRANSCRIPTION]
                parts.append("\n📢 TRANSCRIPCIÓN (lo que se DIJO en clase):")
                parts.append(transcription)
                if len(cls["transcription"]) > MAX_TRANSCRIPTION:
                    parts.append("[... transcripción truncada por longitud ...]")

            if cls.get("slides"):
                slides = cls["slides"][:MAX_SLIDES]
                parts.append("\n📊 SLIDES / PANTALLA (lo que se MOSTRÓ):")
                parts.append(slides)
                if len(cls["slides"]) > MAX_SLIDES:
                    parts.append("[... slides truncados por longitud ...]")

            parts.append("")

        system_instruction = "\n".join(parts)

        session_model, cache_name = self._build_cached_model(system_instruction, cached_content_name)

        sdk_history = [
            {"role": msg["role"], "parts": [msg["content"]]}
            for msg in (history or [])
        ]

        self.chat_sessions[folder_id] = {
            "chat": session_model.start_chat(history=sdk_history),
            "history": list(history) if history else [],
            "knowledge_text": knowledge_text or "",
            "rubricas_text": rubricas_text or "",
            "context_images": context_images or [],
        }

        action = "restaurada" if history else "iniciada"
        logger.info(
            f"Sesión de chat de carpeta {action}: {folder_id} "
            f"({len(classes_content)} clases, "
            f"{len(self.chat_sessions[folder_id]['history'])} mensajes previos, "
            f"caché: {'sí' if cache_name else 'no'})"
        )
        return cache_name
