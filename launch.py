"""
V_T_R - Launcher con ventana nativa (pywebview)

Inicia Flask en un hilo de fondo y:
  - Si pywebview está instalado → abre una ventana propia del sistema.
  - Si no está instalado       → abre el navegador por defecto automáticamente.
"""

import threading
import time
import socket
import logging
import webbrowser

logger = logging.getLogger(__name__)

# Intentar importar pywebview (opcional; puede no estar disponible en
# algunos sistemas donde pythonnet no se pudo compilar).
try:
    import webview
    _HAS_WEBVIEW = True
except ImportError:
    _HAS_WEBVIEW = False


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

    host = '127.0.0.1' if config.FLASK_HOST in ('0.0.0.0', '') else config.FLASK_HOST
    url  = f"http://{host}:{config.FLASK_PORT}"

    # 1. Arrancar Flask en un hilo daemon
    flask_thread = threading.Thread(target=_start_flask, daemon=True, name="flask-server")
    flask_thread.start()

    # 2. Esperar a que el servidor esté listo (máx. 15 s)
    if not _wait_for_server(host, config.FLASK_PORT):
        print("[!] El servidor tardó demasiado en arrancar. Abriendo de todos modos...")

    # 3a. Ventana nativa con pywebview
    if _HAS_WEBVIEW:
        webview.create_window(
            "V_T_R - Video Transcriptor y Resumen",
            url,
            width=1280,
            height=800,
            resizable=True,
            min_size=(900, 600),
        )
        webview.start()
        # Al cerrar la ventana el proceso termina;
        # el hilo Flask es daemon y muere junto con él.

    # 3b. Fallback: abrir navegador por defecto y esperar Ctrl+C
    else:
        print(f"\n  [OK] Servidor listo en {url}")
        print("  Abriendo navegador automaticamente...")
        webbrowser.open(url)
        print("  Presiona Ctrl+C para detener el servidor.\n")
        try:
            flask_thread.join()
        except KeyboardInterrupt:
            print("\n  Servidor detenido.")
