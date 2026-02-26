"""
V_T_R - Launcher con ventana nativa (pywebview)

Inicia Flask en un hilo de fondo y abre la interfaz como ventana de escritorio,
sin necesidad de abrir Chrome ni ningún navegador externo.
"""

import threading
import time
import socket
import logging

logger = logging.getLogger(__name__)


def _start_flask():
    """Corre el servidor Flask en un hilo daemon."""
    import config
    from app import app

    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,        # pywebview no es compatible con debug/reloader
        threaded=True,
        use_reloader=False,
    )


def _wait_for_server(host: str, port: int, timeout: int = 15) -> bool:
    """Sondea el puerto hasta que Flask esté listo para responder."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


if __name__ == '__main__':
    import config
    import webview

    host = '127.0.0.1' if config.FLASK_HOST in ('0.0.0.0', '') else config.FLASK_HOST
    url  = f"http://{host}:{config.FLASK_PORT}"

    # 1. Arrancar Flask en un hilo daemon
    flask_thread = threading.Thread(target=_start_flask, daemon=True, name="flask-server")
    flask_thread.start()

    # 2. Esperar a que el servidor esté listo (máx. 15 s)
    if not _wait_for_server(host, config.FLASK_PORT):
        print("[!] El servidor tardó demasiado en arrancar. Abriendo la ventana de todos modos...")

    # 3. Crear y abrir ventana nativa
    webview.create_window(
        "V_T_R - Video Transcriptor y Resumen",
        url,
        width=1280,
        height=800,
        resizable=True,
        min_size=(900, 600),
    )
    webview.start()
    # Al cerrar la ventana, el proceso termina;
    # el hilo Flask es daemon así que muere junto con él.
