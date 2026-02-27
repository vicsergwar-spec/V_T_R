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
import os
import webbrowser

logger = logging.getLogger(__name__)

# Forzar software-rendering en Chromium/Qt WebEngine para evitar
# conflictos entre CUDA y el compositor GPU de la ventana nativa.
os.environ.setdefault("QTWEBENGINE_CHROMIUM_FLAGS", "--disable-gpu")


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
        from PyQt6.QtWidgets import QApplication, QFileDialog
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

    def _handle_download(download):
        """Muestra diálogo nativo 'Guardar como' para cualquier descarga."""
        suggested = download.suggestedFileName()
        path, _ = QFileDialog.getSaveFileName(win, "Guardar archivo", suggested)
        if path:
            download.setDownloadDirectory(os.path.dirname(path) or ".")
            download.setDownloadFileName(os.path.basename(path))
            download.accept()
        else:
            download.cancel()

    profile.downloadRequested.connect(_handle_download)

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

def _get_local_ip() -> str:
    """Detecta la IP local de la red (no 127.0.0.1)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def _print_access_info(port: int):
    """Muestra las URLs de acceso local y remoto."""
    local_ip = _get_local_ip()
    print("\n" + "=" * 56)
    print("  V_T_R — Video Transcriptor y Resumen")
    print("=" * 56)
    print(f"  Local:       http://127.0.0.1:{port}")
    print(f"  Red local:   http://{local_ip}:{port}")
    print(f"  Remoto:      POST /api/tunnel/start (cloudflared)")
    print("-" * 56)
    print("  GPU procesa localmente sin importar el origen")
    print("  de la subida. Chats y descargas funcionan desde")
    print("  cualquier cliente conectado.")
    print("=" * 56 + "\n")


if __name__ == '__main__':
    import config

    # Flask escucha en 0.0.0.0 para acceso remoto; la ventana local apunta a 127.0.0.1
    local_url = f"http://127.0.0.1:{config.FLASK_PORT}"

    # Arrancar Flask en hilo daemon
    flask_thread = threading.Thread(target=_start_flask, daemon=True, name="flask-server")
    flask_thread.start()

    if not _wait_for_server('127.0.0.1', config.FLASK_PORT):
        print("[!] El servidor tardó demasiado en arrancar. Abriendo de todos modos...")

    _print_access_info(config.FLASK_PORT)

    # Intentar ventana nativa (Qt → pywebview → navegador)
    if _try_qt_window(local_url):
        pass  # Qt manejó todo; al cerrar la ventana el proceso termina
    elif _try_webview_window(local_url):
        pass  # pywebview manejó todo
    else:
        print("  Abriendo navegador automaticamente...")
        webbrowser.open(local_url)
        print("  Presiona Ctrl+C para detener.\n")
        try:
            flask_thread.join()
        except KeyboardInterrupt:
            print("\n  Servidor detenido.")
