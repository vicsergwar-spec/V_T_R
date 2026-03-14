"""
Servicio de interacción con Google Gemini API
"""
import logging
from datetime import datetime, timedelta
from typing import Optional
import google.generativeai as genai
from google.generativeai.protos import (
    Tool as _ProtoTool,
    GoogleSearchRetrieval as _GoogleSearchRetrieval,
)
from services.rate_limiter import gemini_rate_limiter
from services.toon_encoder import dumps as toon_dumps

logger = logging.getLogger(__name__)

# Herramienta de Google Search Grounding reutilizable
_GOOGLE_SEARCH_TOOL = _ProtoTool(
    google_search_retrieval=_GoogleSearchRetrieval()
)


class GeminiService:
    """Servicio para interactuar con Google Gemini API"""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash"):
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
        self._cached_session_ids: set = set()
        logger.info(f"Servicio Gemini inicializado con modelo: {model_name}")

    # ── TOON conversion helpers ───────────────────────────────────────

    @staticmethod
    def _to_toon(text: str, label: str = "") -> str:
        """Convierte texto plano a TOON wrapping: {label: text}."""
        if not text or not text.strip():
            return ""
        return toon_dumps({label: text}) if label else text

    @staticmethod
    def _transcription_to_toon(transcription_text: str) -> str:
        """Convierte texto de transcripción (JSONL de segmentos o texto plano) a TOON."""
        import json
        lines = transcription_text.strip().splitlines()
        segments = []
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                seg = json.loads(line)
                segments.append(seg)
            except (json.JSONDecodeError, ValueError):
                # No es JSONL, devolver el texto wrapeado
                return toon_dumps({"transcripcion": transcription_text})
        if not segments:
            return toon_dumps({"transcripcion": transcription_text})
        return toon_dumps({"segmentos": segments})

    @staticmethod
    def _history_to_toon(history: list) -> str:
        """Convierte historial de chat a TOON compacto."""
        if not history:
            return ""
        return toon_dumps({"historial": history})

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
            gemini_rate_limiter.acquire()
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

    # ── Chunked summarization constants ─────────────────────────────────
    _CHUNK_MAX_CHARS = 400_000      # ~100k tokens por chunk (Gemini 2.5 Flash context)
    _CHUNK_OVERLAP_CHARS = 2_000    # ~500 tokens de solapamiento

    def _split_into_chunks(self, text: str) -> list[str]:
        """Divide texto largo en chunks con solapamiento."""
        if len(text) <= self._CHUNK_MAX_CHARS:
            return [text]

        chunks = []
        start = 0
        while start < len(text):
            end = start + self._CHUNK_MAX_CHARS
            # Cortar en un salto de línea o espacio cercano al límite
            if end < len(text):
                cut = text.rfind('\n', start + self._CHUNK_MAX_CHARS - 500, end)
                if cut == -1:
                    cut = text.rfind(' ', start + self._CHUNK_MAX_CHARS - 500, end)
                if cut > start:
                    end = cut
            chunks.append(text[start:end])
            start = end - self._CHUNK_OVERLAP_CHARS
        return chunks

    def generate_summary(self, transcription_text: str, folder_name: str) -> str:
        """
        Genera un resumen estructurado de la clase.
        Si la transcripción es larga, la divide en chunks, resume cada uno
        y luego genera un resumen final consolidado.

        Args:
            transcription_text: Texto completo de la transcripción
            folder_name: Nombre de la carpeta/clase

        Returns:
            Resumen en formato Markdown
        """
        current_date = datetime.now().strftime("%Y-%m-%d %H:%M")

        try:
            chunks = self._split_into_chunks(transcription_text)

            if len(chunks) == 1:
                # Transcripción corta: resumen directo
                summary_text = self._summarize_single(chunks[0], folder_name, current_date)
            else:
                # Transcripción larga: resumir por chunks y consolidar
                logger.info(f"Transcripción dividida en {len(chunks)} chunks para resumen")
                partial_summaries = []
                for i, chunk in enumerate(chunks, 1):
                    logger.info(f"Resumiendo chunk {i}/{len(chunks)}...")
                    partial = self._summarize_chunk(chunk, i, len(chunks))
                    partial_summaries.append(partial)

                combined = "\n\n---\n\n".join(partial_summaries)
                summary_text = self._summarize_final(combined, folder_name, current_date)

            logger.info("Resumen generado exitosamente")
            return summary_text

        except Exception as e:
            logger.error(f"Error al generar resumen: {e}")
            return f"""# {folder_name.replace('_', ' ')}

## Fecha de procesamiento
{current_date}

## Error
No se pudo generar el resumen automáticamente. Por favor, revisa la transcripción directamente.
"""

    def _summarize_single(self, text: str, folder_name: str, current_date: str) -> str:
        """Resumen directo de un texto corto."""
        prompt = f"""Eres un asistente académico experto. Analiza la siguiente transcripción de una clase y genera un resumen estructurado.

TRANSCRIPCIÓN DE LA CLASE:
{text}

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

        gemini_rate_limiter.acquire()
        response = self.model.generate_content(prompt)
        return response.text.strip()

    def _summarize_chunk(self, chunk_text: str, chunk_num: int, total_chunks: int) -> str:
        """Resume un chunk individual de la transcripción."""
        prompt = f"""Eres un asistente académico experto. Estás analizando la PARTE {chunk_num} de {total_chunks} \
de una transcripción de clase.

FRAGMENTO DE LA TRANSCRIPCIÓN (parte {chunk_num}/{total_chunks}):
{chunk_text}

Resume este fragmento extrayendo:
- Puntos principales tratados
- Conceptos clave explicados
- Tareas o pendientes mencionados (si los hay)
- Fórmulas o datos técnicos importantes

Sé conciso pero no omitas información académica relevante. Usa viñetas."""

        gemini_rate_limiter.acquire()
        response = self.model.generate_content(prompt)
        return response.text.strip()

    def _summarize_final(self, combined_summaries: str, folder_name: str, current_date: str) -> str:
        """Genera el resumen final consolidado a partir de resúmenes parciales."""
        prompt = f"""Eres un asistente académico experto. Se te proporcionan resúmenes parciales de \
distintas partes de una misma clase. Combínalos en un resumen final único, coherente y sin repeticiones.

RESÚMENES PARCIALES:
{combined_summaries}

GENERA UN RESUMEN FINAL EN FORMATO MARKDOWN CON ESTA ESTRUCTURA EXACTA:

# {folder_name.replace('_', ' ')}

## Fecha de procesamiento
{current_date}

## Puntos principales
(Lista los puntos más importantes de la clase completa, en formato de viñetas, sin repetir)

## Lo más importante para estudiar
(Identifica los conceptos clave que el estudiante debe dominar, explica brevemente cada uno)

## Tareas o pendientes mencionadas
(Consolida todas las tareas o pendientes de todas las partes. Si no hay ninguno, indicar \
"No se mencionaron tareas o pendientes en esta clase.")

INSTRUCCIONES ADICIONALES:
- Elimina redundancias entre partes
- Sé conciso pero completo
- Usa viñetas para mejor legibilidad
- Destaca términos técnicos importantes con **negritas**
- El resumen debe ser útil para estudiar antes de un examen"""

        gemini_rate_limiter.acquire()
        response = self.model.generate_content(prompt)
        return response.text.strip()

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
            gemini_rate_limiter.acquire()
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
                return model, existing_cache_name, True
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
            return model, cache.name, True
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
            return model, None, False

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
        extra_knowledge_text: str = "",
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
        # ── Convertir contenido a TOON (compacto, menos tokens) ──
        toon_transcription = self._transcription_to_toon(transcription_text)
        toon_slides = toon_dumps({"slides": slides_content}) if slides_content.strip() else ""
        toon_ek = toon_dumps({"extra_knowledge": extra_knowledge_text}) if extra_knowledge_text and extra_knowledge_text.strip() else ""

        # Bloque de extra knowledge
        _ek_block = ""
        if toon_ek:
            _ek_block = (
                "\n\n═══════════════════════════════════════════\n"
                " === CONOCIMIENTO EXTRA (TOON) ===\n"
                "═══════════════════════════════════════════\n"
                f"{toon_ek}\n"
            )

        _anti_hallucination = (
            "\n\nIMPORTANTE: Responde únicamente con información presente en la "
            "transcripción, slides o extra knowledge proporcionado. Si no tienes "
            "la información, dilo explícitamente."
        )

        if slides_content.strip():
            system_instruction = f"""Eres un asistente de estudio especializado. \
Tu trabajo es ayudar al estudiante a entender y estudiar el contenido de una clase grabada.
{_ek_block}
Tienes acceso a DOS fuentes de información de la misma clase (formato TOON):

═══════════════════════════════════════════
 FUENTE 1 · TRANSCRIPCIÓN DE AUDIO (TOON)
 (lo que se DIJO durante la clase)
═══════════════════════════════════════════
{toon_transcription}

═══════════════════════════════════════════
 FUENTE 2 · CONTENIDO DE SLIDES / PANTALLA (TOON)
 (lo que se MOSTRÓ en el video)
═══════════════════════════════════════════
{toon_slides}

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
6. Usa un tono amigable pero académico.{_anti_hallucination}"""
        else:
            system_instruction = f"""Eres un asistente de estudio especializado. \
Tu trabajo es ayudar al estudiante a entender y estudiar el contenido de una clase grabada.
{_ek_block}
TRANSCRIPCIÓN DE LA CLASE (TOON):
{toon_transcription}

INSTRUCCIONES:
1. Responde ÚNICAMENTE basándote en el contenido de la transcripción.
2. Si algo no está en la transcripción, di claramente "Eso no se menciona en esta clase".
3. Sé claro y didáctico en tus explicaciones.
4. Si el estudiante pregunta sobre un tema, proporciona ejemplos de la clase si los hay.
5. Puedes ayudar a resumir secciones específicas, explicar conceptos, o preparar para exámenes.
6. Usa un tono amigable pero académico.{_anti_hallucination}"""

        session_model, cache_name, is_cached = self._build_cached_model(system_instruction, cached_content_name)

        if is_cached:
            self._cached_session_ids.add(class_id)
        else:
            self._cached_session_ids.discard(class_id)

        # Historial previo en TOON para reducir tokens de contexto
        sdk_history = []
        for msg in (history or []):
            toon_content = toon_dumps({"msg": msg["content"]})
            sdk_history.append({"role": msg["role"], "parts": [toon_content]})

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

    def _rebuild_session(self, session_key: str, file_manager, extra_knowledge_text: str = "") -> None:
        """
        Reconstruye una sesión de chat tras un error de caché expirado.
        Detecta si es clase o carpeta por el prefijo __folder__.
        """
        # Preservar historial actual antes de limpiar
        old_history = self.chat_sessions.get(session_key, {}).get("history", [])

        # Limpiar sesión en memoria
        if session_key in self.chat_sessions:
            del self.chat_sessions[session_key]
        self._cached_session_ids.discard(session_key)

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
                extra_knowledge_text=extra_knowledge_text,
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
                extra_knowledge_text=extra_knowledge_text,
            )
            if new_cache_name:
                file_manager.save_cache_name(class_id, new_cache_name)

        logger.info(f"Sesión reconstruida tras error de caché: {session_key}")

    def chat(
        self, class_id: str, user_message: str, file_manager=None,
        extra_knowledge_text: str = "", use_grounding: bool = True,
        inline_images: Optional[list] = None,
    ) -> str:
        """
        Envía un mensaje en la sesión de chat de una clase.

        Args:
            class_id: Identificador de la clase (o session_key para carpetas)
            user_message: Mensaje del usuario
            file_manager: Referencia al FileManager para auto-recovery de caché
            use_grounding: Habilitar Google Search Grounding (por defecto True)
            inline_images: Lista de dicts {mime_type, data} con imágenes pegadas

        Returns:
            Respuesta de Gemini
        """
        if class_id not in self.chat_sessions:
            raise ValueError(f"No hay sesión de chat activa para la clase: {class_id}")

        session = self.chat_sessions[class_id]

        try:
            return self._send_chat_message(class_id, session, user_message, use_grounding=use_grounding, inline_images=inline_images)

        except Exception as e:
            # Si es error de CachedContent y tenemos file_manager, auto-recovery
            if file_manager and self._is_cache_not_found_error(e):
                logger.warning(
                    f"CachedContent expirado para {class_id}, reconstruyendo sesión..."
                )
                try:
                    self._rebuild_session(class_id, file_manager, extra_knowledge_text=extra_knowledge_text)
                    session = self.chat_sessions[class_id]
                    return self._send_chat_message(class_id, session, user_message, use_grounding=use_grounding, inline_images=inline_images)
                except Exception as retry_err:
                    logger.error(f"Error en retry tras reconstruir sesión: {retry_err}")
                    return "Lo siento, hubo un error al procesar tu pregunta. Por favor, intenta de nuevo."

            logger.error(f"Error en chat: {e}")
            return "Lo siento, hubo un error al procesar tu pregunta. Por favor, intenta de nuevo."

    def _send_chat_message(
        self, class_id: str, session: dict, user_message: str,
        use_grounding: bool = True, inline_images: list | None = None,
    ) -> str:
        """Envía el mensaje y actualiza el historial. Lanza excepciones sin capturar."""
        enriched_message = self._prepend_extra_context(
            user_message,
            session.get("knowledge_text", ""),
            session.get("rubricas_text", ""),
        )

        send_kwargs = {}
        if use_grounding and class_id not in self._cached_session_ids:
            send_kwargs["tools"] = [_GOOGLE_SEARCH_TOOL]

        context_images = session.get("context_images", [])
        all_images = list(context_images)
        if inline_images:
            all_images.extend(inline_images)

        gemini_rate_limiter.acquire()
        if all_images:
            message_parts = [enriched_message]
            for img in all_images:
                message_parts.append({
                    "mime_type": img["mime_type"],
                    "data": img["data"],
                })
            response = session["chat"].send_message(message_parts, **send_kwargs)
        else:
            response = session["chat"].send_message(enriched_message, **send_kwargs)

        assistant_message = response.text.strip()

        session["history"].append({"role": "user", "content": user_message})
        session["history"].append({"role": "model", "content": assistant_message})

        logger.info(f"Chat respondido para clase: {class_id}")
        return assistant_message

    @staticmethod
    def _prepend_extra_context(user_message: str, knowledge_text: str, rubricas_text: str) -> str:
        """Prepend knowledge and rubrics blocks (TOON) to the user message if they exist."""
        parts = []
        if knowledge_text and knowledge_text.strip():
            toon_k = toon_dumps({"conocimiento_extra": knowledge_text})
            parts.append(f"[CONOCIMIENTO EXTRA · TOON]\n{toon_k}\n[/CONOCIMIENTO EXTRA]")
        if rubricas_text and rubricas_text.strip():
            toon_r = toon_dumps({"rubricas": rubricas_text})
            parts.append(f"[RÚBRICAS · TOON]\n{toon_r}\n[/RÚBRICAS]")
        if parts:
            parts.append(user_message)
            return "\n\n".join(parts)
        return user_message

    def refresh_cache(self) -> None:
        """
        Invalida todas las sesiones de chat activas para que se recreen
        con el contenido actualizado (incluido extra knowledge) en el próximo mensaje.
        """
        session_keys = list(self.chat_sessions.keys())
        for key in session_keys:
            del self.chat_sessions[key]
        if session_keys:
            logger.info(f"Caché refrescado: {len(session_keys)} sesión(es) invalidada(s)")

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
            self._cached_session_ids.discard(class_id)
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
        extra_knowledge_text: str = "",
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
        MAX_TRANSCRIPTION = 80_000
        MAX_SUMMARY = 3_000
        MAX_SLIDES = 8_000

        parts = [
            f"Eres un asistente académico especializado. Tienes acceso al contenido "
            f"COMPLETO de la carpeta «{folder_name}» que contiene "
            f"{len(classes_content)} clase(s) grabada(s).\n",
        ]

        if extra_knowledge_text and extra_knowledge_text.strip():
            toon_ek = toon_dumps({"extra_knowledge": extra_knowledge_text})
            parts.append("═" * 60)
            parts.append("=== CONOCIMIENTO EXTRA (TOON) ===")
            parts.append("═" * 60)
            parts.append(toon_ek)
            parts.append("")

        parts += [
            "INSTRUCCIONES IMPORTANTES:",
            "Los contenidos de cada clase están en formato TOON (compacto).",
            "1. Responde ÚNICAMENTE basándote en el contenido de las clases mostradas.",
            "2. Indica siempre de qué clase proviene la información: *(📚 Clase: Nombre)*",
            "3. Si algo no aparece en ninguna clase, di: "
            "\"Eso no se menciona en las clases de esta carpeta\".",
            "4. Puedes comparar y relacionar conceptos entre distintas clases.",
            "5. Sé claro y didáctico. Usa ejemplos del contenido cuando los haya.",
            "6. Usa un tono amigable pero académico.",
            "",
            "IMPORTANTE: Responde únicamente con información presente en la "
            "transcripción, slides o extra knowledge proporcionado. Si no tienes "
            "la información, dilo explícitamente.\n",
        ]

        for i, cls in enumerate(classes_content, 1):
            sep = "═" * 60
            parts.append(sep)
            parts.append(f"CLASE {i}: {cls['name']}")
            parts.append(sep)

            if cls.get("summary"):
                summary = cls["summary"][:MAX_SUMMARY]
                toon_s = toon_dumps({"resumen": summary})
                parts.append(f"\n📋 RESUMEN (TOON):\n{toon_s}")
                if len(cls["summary"]) > MAX_SUMMARY:
                    parts.append("[... resumen truncado ...]")

            if cls.get("transcription"):
                transcription = cls["transcription"][:MAX_TRANSCRIPTION]
                toon_t = self._transcription_to_toon(transcription)
                parts.append(f"\n📢 TRANSCRIPCIÓN (TOON):\n{toon_t}")
                if len(cls["transcription"]) > MAX_TRANSCRIPTION:
                    parts.append("[... transcripción truncada por longitud ...]")

            if cls.get("slides"):
                slides = cls["slides"][:MAX_SLIDES]
                toon_sl = toon_dumps({"slides": slides})
                parts.append(f"\n📊 SLIDES (TOON):\n{toon_sl}")
                if len(cls["slides"]) > MAX_SLIDES:
                    parts.append("[... slides truncados por longitud ...]")

            parts.append("")

        system_instruction = "\n".join(parts)

        session_model, cache_name, is_cached = self._build_cached_model(system_instruction, cached_content_name)

        if is_cached:
            self._cached_session_ids.add(folder_id)
        else:
            self._cached_session_ids.discard(folder_id)

        sdk_history = []
        for msg in (history or []):
            toon_content = toon_dumps({"msg": msg["content"]})
            sdk_history.append({"role": msg["role"], "parts": [toon_content]})

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

    # ──────────────────────────────────────────────────────────
    # Herramientas de estudio
    # ──────────────────────────────────────────────────────────

    def generate_flashcards(self, transcription_text: str, summary: str, slides: str, class_name: str) -> str:
        """Genera flashcards en formato Anki (Pregunta\\tRespuesta) a partir del contenido de la clase."""
        context_parts = []
        if transcription_text:
            context_parts.append(f"TRANSCRIPCIÓN:\n{transcription_text[:60000]}")
        if summary:
            context_parts.append(f"RESUMEN:\n{summary[:5000]}")
        if slides:
            context_parts.append(f"SLIDES:\n{slides[:10000]}")
        context = "\n\n".join(context_parts)

        prompt = f"""Eres un experto en técnicas de estudio y memorización espaciada.
A partir del siguiente contenido de la clase "{class_name.replace('_', ' ')}", genera entre 15 y 20 flashcards
en formato Anki (importación por texto).

CONTENIDO:
{context}

REGLAS ESTRICTAS:
1. Cada línea es una flashcard: Pregunta[TAB]Respuesta
2. Usa EXACTAMENTE un carácter tabulador (\\t) para separar pregunta de respuesta.
3. Las preguntas deben cubrir los conceptos más importantes de la clase.
4. Las respuestas deben ser concisas pero completas (1-3 oraciones).
5. Incluye preguntas de definición, comparación, aplicación y relación de conceptos.
6. NO uses comillas alrededor de las preguntas o respuestas.
7. NO numeres las flashcards.
8. NO incluyas encabezados ni texto adicional, SOLO las líneas pregunta\\trespuesta.

Responde SOLO con las líneas de flashcards, sin explicaciones."""

        try:
            gemini_rate_limiter.acquire()
            response = self.model.generate_content(prompt)
            result = response.text.strip()
            logger.info(f"Flashcards generadas para: {class_name}")
            return result
        except Exception as e:
            logger.error(f"Error generando flashcards: {e}")
            raise

    def generate_exam(self, transcription_text: str, summary: str, slides: str, class_name: str, topic: str = "") -> str:
        """Genera un examen simulado con preguntas de opción múltiple y desarrollo."""
        context_parts = []
        if transcription_text:
            context_parts.append(f"TRANSCRIPCIÓN:\n{transcription_text[:60000]}")
        if summary:
            context_parts.append(f"RESUMEN:\n{summary[:5000]}")
        if slides:
            context_parts.append(f"SLIDES:\n{slides[:10000]}")
        context = "\n\n".join(context_parts)

        topic_instruction = f'Enfócate ESPECÍFICAMENTE en el tema: "{topic}".' if topic else "Cubre los temas más importantes de la clase de forma general."

        prompt = f"""Eres un profesor universitario experto. Genera un examen simulado basado en el contenido
de la clase "{class_name.replace('_', ' ')}".

{topic_instruction}

CONTENIDO DE LA CLASE:
{context}

GENERA EL EXAMEN EN FORMATO MARKDOWN CON ESTA ESTRUCTURA EXACTA:

# Examen: {class_name.replace('_', ' ')}{(' — ' + topic) if topic else ''}

## Instrucciones
- Las preguntas 1-10 son de opción múltiple. Selecciona la respuesta correcta.
- Las preguntas 11-12 son de desarrollo. Responde de forma completa y argumentada.

---

## Sección I: Opción Múltiple

**1.** [Pregunta]

a) [Opción A]
b) [Opción B]
c) [Opción C]
d) [Opción D]

**Respuesta correcta:** [letra]) [texto de la respuesta]

(Repite para las 10 preguntas)

---

## Sección II: Preguntas de Desarrollo

**11.** [Pregunta de desarrollo que requiera análisis o síntesis]

**Guía de respuesta:** [Puntos clave que debe incluir una buena respuesta, en viñetas]

**12.** [Pregunta de desarrollo que requiera aplicación práctica]

**Guía de respuesta:** [Puntos clave que debe incluir una buena respuesta, en viñetas]

INSTRUCCIONES ADICIONALES:
- Basa TODAS las preguntas en el contenido real de la clase.
- Las opciones incorrectas deben ser plausibles (distractores buenos).
- Varía la dificultad: fácil, media y difícil.
- Las preguntas de desarrollo deben requerir pensamiento crítico."""

        try:
            gemini_rate_limiter.acquire()
            response = self.model.generate_content(prompt)
            result = response.text.strip()
            logger.info(f"Examen generado para: {class_name} (tema: {topic or 'general'})")
            return result
        except Exception as e:
            logger.error(f"Error generando examen: {e}")
            raise

    def extract_activity(
        self, transcription_text: str, summary: str, slides: str,
        knowledge_text: str, rubricas_text: str, class_name: str, activity_name: str
    ) -> str:
        """Extrae toda la información relacionada con una actividad específica."""
        context_parts = []
        if transcription_text:
            context_parts.append(f"TRANSCRIPCIÓN DE LA CLASE:\n{transcription_text[:60000]}")
        if summary:
            context_parts.append(f"RESUMEN:\n{summary[:5000]}")
        if slides:
            context_parts.append(f"SLIDES:\n{slides[:10000]}")
        if knowledge_text:
            context_parts.append(f"ARCHIVOS DE CONOCIMIENTO EXTRA:\n{knowledge_text[:10000]}")
        if rubricas_text:
            context_parts.append(f"RÚBRICAS:\n{rubricas_text[:10000]}")
        context = "\n\n".join(context_parts)

        prompt = f"""Eres un asistente académico experto. Busca TODA la información relacionada con la actividad
"{activity_name}" en el siguiente contenido de la clase "{class_name.replace('_', ' ')}".

CONTENIDO DISPONIBLE:
{context}

Tu tarea es extraer y estructurar TODA la información que encuentres sobre la actividad "{activity_name}"
en un documento Markdown completo y organizado.

GENERA EL DOCUMENTO CON ESTA ESTRUCTURA EXACTA:

# {activity_name}

**Clase:** {class_name.replace('_', ' ')}
**Extraído el:** (fecha actual)

## Descripción
(Describe de qué trata la actividad según lo mencionado en clase)

## Objetivos
(Lista los objetivos o propósitos de la actividad)

## Instrucciones
(Detalla paso a paso qué debe hacer el estudiante. Si hay instrucciones específicas del profesor, inclúyelas textualmente)

## Criterios de evaluación
(Si hay rúbrica o criterios de calificación, estructúralos aquí. Si no hay información, indicar "No se mencionaron criterios específicos")

## Fechas mencionadas
(Fechas de entrega, presentación, etc. Si no hay, indicar "No se mencionaron fechas específicas")

## Material necesario
(Herramientas, software, libros, etc. que se necesitan)

## Notas del profesor
(Comentarios adicionales, consejos, advertencias o aclaraciones que haya hecho el profesor sobre esta actividad)

## Fuentes de información
(Indica de dónde se extrajo cada pieza de información: transcripción, slides, rúbrica, etc.)

INSTRUCCIONES:
- Extrae SOLO información que realmente aparezca en el contenido proporcionado.
- Si una sección no tiene información, escribe "No se encontró información sobre este punto en el material disponible."
- Sé exhaustivo: incluye TODO lo que el profesor haya dicho sobre esta actividad.
- Conserva citas textuales relevantes del profesor entre comillas.
- El documento debe ser útil para que el estudiante complete la actividad sin necesidad de revisar la grabación."""

        try:
            gemini_rate_limiter.acquire()
            response = self.model.generate_content(prompt)
            result = response.text.strip()
            logger.info(f"Actividad extraída: '{activity_name}' de {class_name}")
            return result
        except Exception as e:
            logger.error(f"Error extrayendo actividad: {e}")
            raise

    def extract_activity_from_folder(
        self, classes_content: list, folder_name: str, activity_name: str
    ) -> str:
        """Extrae información de una actividad buscando en todas las clases de una carpeta."""
        classes_blocks = []
        for cls in classes_content:
            parts = []
            if cls.get("transcription"):
                parts.append(f"Transcripción:\n{cls['transcription'][:30000]}")
            if cls.get("summary"):
                parts.append(f"Resumen:\n{cls['summary'][:3000]}")
            if cls.get("slides"):
                parts.append(f"Slides:\n{cls['slides'][:5000]}")
            if parts:
                classes_blocks.append(
                    f"### CLASE: {cls['name']}\n\n" + "\n\n".join(parts)
                )

        context = "\n\n---\n\n".join(classes_blocks)

        prompt = f"""Eres un asistente académico experto. Busca TODA la información relacionada con la actividad
"{activity_name}" en el contenido de TODAS las clases de la carpeta "{folder_name}".

CONTENIDO DE LAS CLASES:
{context}

Tu tarea es consolidar TODA la información que encuentres sobre la actividad "{activity_name}"
en un único documento Markdown organizado. Indica SIEMPRE de qué clase proviene cada dato.

GENERA EL DOCUMENTO CON ESTA ESTRUCTURA EXACTA:

# {activity_name}

**Carpeta:** {folder_name}
**Extraído el:** (fecha actual)
**Clases analizadas:** (lista las clases donde se encontró información)

## Descripción
(Describe de qué trata la actividad consolidando lo mencionado en las distintas clases. Indica entre paréntesis la clase de origen de cada dato, ej: *(Clase 3 - Tema X)*)

## Objetivos
(Lista los objetivos o propósitos de la actividad, indicando la clase fuente)

## Instrucciones
(Detalla paso a paso qué debe hacer el estudiante. Si hay instrucciones específicas del profesor, inclúyelas textualmente con la clase de origen)

## Criterios de evaluación
(Si hay rúbrica o criterios de calificación en alguna clase, estructúralos aquí indicando la fuente. Si no hay información, indicar "No se mencionaron criterios específicos")

## Fechas mencionadas
(Fechas de entrega, presentación, etc. encontradas en cualquier clase. Si no hay, indicar "No se mencionaron fechas específicas")

## Material necesario
(Herramientas, software, libros, etc. mencionados en cualquier clase)

## Notas del profesor
(Comentarios adicionales, consejos, advertencias o aclaraciones del profesor sobre esta actividad, con la clase de origen)

## Fuentes de información
(Tabla o lista que indique exactamente de qué clase y sección —transcripción, slides, resumen— se extrajo cada pieza de información relevante)

INSTRUCCIONES:
- Extrae SOLO información que realmente aparezca en el contenido proporcionado.
- SIEMPRE indica de qué clase proviene cada dato (entre paréntesis o en la sección de fuentes).
- Si una sección no tiene información en ninguna clase, escribe "No se encontró información sobre este punto en el material disponible."
- Sé exhaustivo: revisa TODAS las clases y consolida la información sin repetir datos.
- Si la misma información aparece en varias clases, consolídala e indica todas las fuentes.
- Conserva citas textuales relevantes del profesor entre comillas con la clase de origen.
- El documento debe ser útil para que el estudiante complete la actividad sin revisar las grabaciones."""

        try:
            gemini_rate_limiter.acquire()
            response = self.model.generate_content(prompt)
            result = response.text.strip()
            logger.info(
                f"Actividad extraída de carpeta: '{activity_name}' "
                f"de {folder_name} ({len(classes_content)} clases)"
            )
            return result
        except Exception as e:
            logger.error(f"Error extrayendo actividad de carpeta: {e}")
            raise
