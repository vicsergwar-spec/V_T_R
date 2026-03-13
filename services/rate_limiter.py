"""
Rate limiter para llamadas a la API de Gemini.

Singleton compartido entre GeminiService y SlideExtractor.
Permite máximo 58 llamadas por minuto (margen de 2 sobre el límite real de 60).
"""

import threading
import time
import logging
from collections import deque

logger = logging.getLogger(__name__)

_MAX_CALLS_PER_MINUTE = 58
_WINDOW_SECONDS = 60.0


class _GeminiRateLimiter:
    """Rate limiter con ventana deslizante de 60 segundos."""

    def __init__(self, max_calls: int = _MAX_CALLS_PER_MINUTE, window: float = _WINDOW_SECONDS):
        self._max_calls = max_calls
        self._window = window
        self._lock = threading.Lock()
        self._timestamps: deque[float] = deque()

    def acquire(self) -> None:
        """
        Bloquea hasta que haya un slot disponible dentro de la ventana.
        Debe llamarse antes de cada request a la API de Gemini.
        """
        with self._lock:
            now = time.monotonic()

            # Purgar timestamps fuera de la ventana
            while self._timestamps and (now - self._timestamps[0]) >= self._window:
                self._timestamps.popleft()

            if len(self._timestamps) >= self._max_calls:
                # Esperar hasta que el timestamp más antiguo salga de la ventana
                wait = self._window - (now - self._timestamps[0]) + 0.1
                if wait > 0:
                    logger.info(
                        f"[RateLimiter] Límite de {self._max_calls} calls/min alcanzado, "
                        f"esperando {wait:.1f}s"
                    )
                    # Liberar el lock mientras esperamos
                    self._lock.release()
                    try:
                        time.sleep(wait)
                    finally:
                        self._lock.acquire()

                    # Purgar de nuevo tras la espera
                    now = time.monotonic()
                    while self._timestamps and (now - self._timestamps[0]) >= self._window:
                        self._timestamps.popleft()

            self._timestamps.append(time.monotonic())


# Singleton global compartido entre todos los servicios
gemini_rate_limiter = _GeminiRateLimiter()
