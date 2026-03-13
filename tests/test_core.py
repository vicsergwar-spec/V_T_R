"""
Tests unitarios para funciones core de V_T_R.
Ejecutar con: pytest tests/test_core.py -v
"""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Asegurar que el directorio raíz del proyecto esté en sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# ────────────────────────────────────────────────────────────
# a) _transcription_to_toon
# ────────────────────────────────────────────────────────────

class TestTranscriptionToToon:
    """Tests para GeminiService._transcription_to_toon()."""

    @staticmethod
    def _call(text: str) -> str:
        from services.gemini_service import GeminiService
        return GeminiService._transcription_to_toon(text)

    def test_jsonl_valido(self):
        """JSONL con segmentos válidos produce TOON con clave 'segmentos'."""
        seg1 = json.dumps({"inicio": "00:00", "texto": "Hola"})
        seg2 = json.dumps({"inicio": "00:05", "texto": "Mundo"})
        jsonl = f"{seg1}\n{seg2}"
        result = self._call(jsonl)
        assert "segmentos" in result
        assert "Hola" in result
        assert "Mundo" in result

    def test_texto_plano(self):
        """Texto plano (no JSONL) produce TOON con clave 'transcripcion'."""
        result = self._call("Esta es una transcripción normal sin JSON.")
        assert "transcripcion" in result
        assert "normal" in result

    def test_string_vacio(self):
        """String vacío produce TOON con clave 'transcripcion'."""
        result = self._call("")
        assert "transcripcion" in result

    def test_string_solo_espacios(self):
        """String con solo espacios/newlines produce TOON con clave 'transcripcion'."""
        result = self._call("   \n  \n  ")
        assert "transcripcion" in result


# ────────────────────────────────────────────────────────────
# b) _history_to_toon
# ────────────────────────────────────────────────────────────

class TestHistoryToToon:
    """Tests para GeminiService._history_to_toon()."""

    @staticmethod
    def _call(history: list) -> str:
        from services.gemini_service import GeminiService
        return GeminiService._history_to_toon(history)

    def test_historial_vacio(self):
        """Historial vacío retorna string vacío."""
        assert self._call([]) == ""

    def test_historial_none(self):
        """Historial None retorna string vacío (list falsy)."""
        assert self._call(None) == ""

    def test_historial_con_mensajes(self):
        """Historial con mensajes produce TOON con clave 'historial'."""
        history = [
            {"role": "user", "content": "Hola"},
            {"role": "model", "content": "Buenos días"},
        ]
        result = self._call(history)
        assert "historial" in result
        assert "Hola" in result
        assert "Buenos" in result


# ────────────────────────────────────────────────────────────
# c) _filter_blank_and_duplicates
# ────────────────────────────────────────────────────────────

class TestFilterBlankAndDuplicates:
    """Tests para SlideExtractor._filter_blank_and_duplicates()."""

    def _make_extractor(self):
        """Crea un SlideExtractor sin inicializar Gemini."""
        from services.slide_extractor import SlideExtractor
        ext = SlideExtractor.__new__(SlideExtractor)
        return ext

    def test_descarta_blancos(self):
        """Frames en blanco son descartados."""
        ext = self._make_extractor()
        frames = [("frame1.jpg", 0.0), ("frame2.jpg", 5.0), ("frame3.jpg", 10.0)]

        # Hashes muy diferentes (hamming distance > 8) para que no se filtren como duplicados
        with patch.object(ext, '_is_blank', side_effect=[True, False, False]), \
             patch.object(ext, '_phash', side_effect=[0x0000, 0xFFFF]):
            result = ext._filter_blank_and_duplicates(frames)

        assert len(result) == 2
        assert result[0][0] == "frame2.jpg"
        assert result[1][0] == "frame3.jpg"

    def test_descarta_duplicados(self):
        """Frames duplicados (phash cercano) son descartados."""
        ext = self._make_extractor()
        frames = [("frame1.jpg", 0.0), ("frame2.jpg", 5.0), ("frame3.jpg", 10.0)]

        # frame1 y frame2 tienen hash idéntico (distancia 0), frame3 es muy diferente
        with patch.object(ext, '_is_blank', return_value=False), \
             patch.object(ext, '_phash', side_effect=[100, 100, 0xFFFF0000]):
            result = ext._filter_blank_and_duplicates(frames)

        assert len(result) == 2
        assert result[0][0] == "frame1.jpg"
        assert result[1][0] == "frame3.jpg"

    def test_sin_filtrados(self):
        """Si no hay blancos ni duplicados, se conservan todos."""
        ext = self._make_extractor()
        frames = [("f1.jpg", 0.0), ("f2.jpg", 5.0)]

        with patch.object(ext, '_is_blank', return_value=False), \
             patch.object(ext, '_phash', side_effect=[0, 0xFFFFFFFF]):
            result = ext._filter_blank_and_duplicates(frames)

        assert len(result) == 2

    def test_lista_vacia(self):
        """Lista vacía retorna lista vacía."""
        ext = self._make_extractor()
        assert ext._filter_blank_and_duplicates([]) == []


# ────────────────────────────────────────────────────────────
# d) _merge_overlapping_regions
# ────────────────────────────────────────────────────────────

class TestMergeOverlappingRegions:
    """Tests para SlideExtractor._merge_overlapping_regions()."""

    @staticmethod
    def _call(regions):
        from services.slide_extractor import SlideExtractor
        return SlideExtractor._merge_overlapping_regions(regions)

    def test_sin_solapamiento(self):
        """Regiones que no se solapan permanecen intactas."""
        regions = [(0, 0, 10, 10), (20, 20, 30, 30)]
        result = self._call(regions)
        assert len(result) == 2

    def test_con_solapamiento(self):
        """Regiones que se solapan se fusionan en una."""
        regions = [(0, 0, 15, 15), (10, 10, 25, 25)]
        result = self._call(regions)
        assert len(result) == 1
        merged = result[0]
        assert merged[0] == 0    # x_min
        assert merged[1] == 0    # y_min
        assert merged[2] == 25   # x_max
        assert merged[3] == 25   # y_max

    def test_lista_vacia(self):
        """Lista vacía retorna lista vacía."""
        assert self._call([]) == []

    def test_una_sola_region(self):
        """Una sola región se retorna sin cambios."""
        result = self._call([(5, 5, 50, 50)])
        assert len(result) == 1
        assert result[0] == (5, 5, 50, 50)

    def test_tres_regiones_cadena(self):
        """Tres regiones que se solapan en cadena se fusionan en una."""
        regions = [(0, 0, 10, 10), (8, 8, 20, 20), (18, 18, 30, 30)]
        result = self._call(regions)
        assert len(result) == 1
        assert result[0] == (0, 0, 30, 30)


# ────────────────────────────────────────────────────────────
# e) _adjust_for_vram
# ────────────────────────────────────────────────────────────

class TestAdjustForVram:
    """Tests para Transcriber._adjust_for_vram()."""

    def _make_transcriber(self, model_name="large-v3"):
        """Crea un Transcriber sin detectar GPU real."""
        from services.transcriber import Transcriber
        t = Transcriber.__new__(Transcriber)
        t.model_name = model_name
        t.openai_api_key = None
        t.model = None
        t.device = "cuda"
        t._COMPUTE_TYPES = dict(Transcriber._COMPUTE_TYPES)
        return t

    def test_vram_2gb_baja_a_medium(self):
        """Con 2.0 GB de VRAM, large-v3 baja a medium."""
        t = self._make_transcriber("large-v3")
        with patch.object(t, '_get_free_vram_gb', return_value=2.0):
            t._adjust_for_vram()
        assert t.model_name == "medium"

    def test_vram_4gb_large_a_int8(self):
        """Con 4.0 GB de VRAM, large-v3 se fuerza a int8 puro."""
        t = self._make_transcriber("large-v3")
        with patch.object(t, '_get_free_vram_gb', return_value=4.0):
            t._adjust_for_vram()
        assert t.model_name == "large-v3"
        assert t._COMPUTE_TYPES["large-v3"]["cuda"] == "int8"

    def test_vram_8gb_sin_cambios(self):
        """Con 8.0 GB de VRAM, large-v3 no cambia."""
        t = self._make_transcriber("large-v3")
        with patch.object(t, '_get_free_vram_gb', return_value=8.0):
            t._adjust_for_vram()
        assert t.model_name == "large-v3"

    def test_medium_no_baja_con_poca_vram(self):
        """Medium no baja a otro modelo con poca VRAM."""
        t = self._make_transcriber("medium")
        with patch.object(t, '_get_free_vram_gb', return_value=2.0):
            t._adjust_for_vram()
        assert t.model_name == "medium"


# ────────────────────────────────────────────────────────────
# f) _clean_floating_fragments
# ────────────────────────────────────────────────────────────

class TestCleanFloatingFragments:
    """Tests para GeminiService._clean_floating_fragments()."""

    @staticmethod
    def _call(doc: str) -> str:
        from services.gemini_service import GeminiService
        return GeminiService._clean_floating_fragments(doc)

    def test_elimina_anio_suelto(self):
        """Un año suelto como línea independiente se elimina."""
        doc = "## Título\n\nContenido normal.\n\n1946\n\nMás contenido."
        result = self._call(doc)
        assert "1946" not in result
        assert "Contenido normal." in result
        assert "Más contenido." in result

    def test_elimina_sigla_flotante(self):
        """Sigla en mayúsculas aislada se elimina."""
        doc = "## Sección\n\nTexto válido aquí.\n\nIBM\n\nOtro texto."
        result = self._call(doc)
        assert "\nIBM\n" not in result

    def test_preserva_encabezados(self):
        """Los encabezados Markdown se preservan siempre."""
        doc = "# Título principal\n\n## Subtítulo\n\n### Nivel 3"
        result = self._call(doc)
        assert "# Título principal" in result
        assert "## Subtítulo" in result
        assert "### Nivel 3" in result

    def test_preserva_listas(self):
        """Listas con viñetas se preservan."""
        doc = "- Primer item\n- Segundo item\n* Tercero"
        result = self._call(doc)
        assert "- Primer item" in result
        assert "- Segundo item" in result
        assert "* Tercero" in result

    def test_preserva_tablas(self):
        """Tablas Markdown se preservan."""
        doc = "| Col1 | Col2 |\n|------|------|\n| A    | B    |"
        result = self._call(doc)
        assert "| Col1 | Col2 |" in result
        assert "| A    | B    |" in result

    def test_preserva_bloques_codigo(self):
        """Contenido dentro de bloques de código se preserva sin filtrar."""
        doc = "```\n1946\nIBM\n```"
        result = self._call(doc)
        assert "1946" in result
        assert "IBM" in result

    def test_preserva_parrafos_largos(self):
        """Párrafos normales con texto largo se preservan."""
        doc = "Este es un párrafo con contenido real que no debe ser eliminado por el filtro."
        result = self._call(doc)
        assert "párrafo con contenido real" in result

    def test_elimina_fragmento_truncado(self):
        """Fragmentos cortos sin contexto se eliminan."""
        doc = "## Sección\n\nes de compu\n\nContenido real aquí."
        result = self._call(doc)
        assert "es de compu" not in result
        assert "Contenido real aquí." in result
