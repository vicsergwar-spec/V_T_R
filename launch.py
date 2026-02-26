"""
V_T_R - Launcher con ventana nativa

Inicia Flask en un hilo de fondo y abre una ventana propia del sistema.
Orden de intentos:
  1. PyQt6 + QWebEngineView  — wheels precompilados, sin compilar nada
  2. pywebview               — requiere pythonnet/.NET SDK en Windows
  3. Navegador por defecto   — fallback garantizado
"""

import threading
import time
import socket
import logging
import sys
import webbrowser

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────
# Flask en hilo daemon
# ──────────────────────────────────────────────

def _start_flask():
    import config
    from app import app
    app.run(
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
        threaded=True,
        use_reloader=False,
    )


def _wait_for_server(host: str, port: int, timeout: int = 15) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1):
                return True
        except OSError:
            time.sleep(0.25)
    return False


# ──────────────────────────────────────────────
# Opción 1: PyQt6 + QWebEngineView
#   Wheels precompilados en PyPI — no requiere .NET ni NuGet
# ──────────────────────────────────────────────

def _try_qt_window(url: str) -> bool:
    try:
        from PyQt6.QtWidgets import QApplication
        from PyQt6.QtWebEngineWidgets import QWebEngineView
        from PyQt6.QtWebEngineCore import QWebEngineProfile
        from PyQt6.QtCore import QUrl, Qt
        from PyQt6.QtGui import QIcon
    except ImportError:
        return False

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("V_T_R")

    # Deshabilitar la política de mismo origen para que Flask funcione bien
    profile = QWebEngineProfile.defaultProfile()
    profile.setPersistentCookiesPolicy(
        QWebEngineProfile.PersistentCookiesPolicy.NoPersistentCookies
    )

    win = QWebEngineView()
    win.setWindowTitle("V_T_R — Video Transcriptor y Resumen")
    win.resize(1280, 800)
    win.setMinimumSize(900, 600)
    win.load(QUrl(url))
    win.show()

    app.exec()
    return True


# ──────────────────────────────────────────────
# Opción 2: pywebview  (requiere pythonnet en Windows)
# ──────────────────────────────────────────────

def _try_webview_window(url: str) -> bool:
    try:
        import webview
    except ImportError:
        return False

    webview.create_window(
        "V_T_R — Video Transcriptor y Resumen",
        url,
        width=1280,
        height=800,
        resizable=True,
        min_size=(900, 600),
    )
    webview.start()
    return True


# ──────────────────────────────────────────────
# Punto de entrada
# ──────────────────────────────────────────────

if __name__ == '__main__':
    import config

    host = '127.0.0.1' if config.FLASK_HOST in ('0.0.0.0', '') else config.FLASK_HOST
    url  = f"http://{host}:{config.FLASK_PORT}"

    # Arrancar Flask en hilo daemon
    flask_thread = threading.Thread(target=_start_flask, daemon=True, name="flask-server")
    flask_thread.start()

    if not _wait_for_server(host, config.FLASK_PORT):
        print("[!] El servidor tardó demasiado en arrancar. Abriendo de todos modos...")

    # Intentar ventana nativa (Qt → pywebview → navegador)
    if _try_qt_window(url):
        pass  # Qt manejó todo; al cerrar la ventana el proceso termina
    elif _try_webview_window(url):
        pass  # pywebview manejó todo
    else:
        print(f"\n  [OK] Servidor listo en {url}")
        print("  Abriendo navegador automaticamente...")
        webbrowser.open(url)
        print("  Presiona Ctrl+C para detener.\n")
        try:
            flask_thread.join()
        except KeyboardInterrupt:
            print("\n  Servidor detenido.")
