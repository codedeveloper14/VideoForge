import http.server
import threading
import time

from desktop import window


class _OkHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args):
        pass  # silencia el log de acceso en la salida de los tests


def _start_dummy_server():
    server = http.server.HTTPServer(("127.0.0.1", 0), _OkHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def test_wait_for_backend_true_cuando_responde():
    server, port = _start_dummy_server()
    try:
        ok = window._wait_for_backend(f"http://127.0.0.1:{port}/", max_wait=3, interval=0.1)
        assert ok is True
    finally:
        server.shutdown()


def test_wait_for_backend_false_si_nunca_responde():
    ok = window._wait_for_backend("http://127.0.0.1:1/no-existe", max_wait=0.3, interval=0.1)
    assert ok is False


def test_screen_size_devuelve_dimensiones_positivas():
    w, h = window._screen_size()
    assert w > 0
    assert h > 0


def test_run_cae_a_navegador_con_vf_no_webview(monkeypatch):
    monkeypatch.setenv("VF_NO_WEBVIEW", "1")
    # Evita esperar el timeout real de 20s del health-check -- no es lo que se prueba aqui.
    monkeypatch.setattr(window, "_wait_for_backend", lambda *a, **kw: True)
    opened = {}
    monkeypatch.setattr(window.webbrowser, "open", lambda url: opened.setdefault("url", url))

    started = []
    window.run(lambda: started.append(True), url="http://127.0.0.1:59999/custom")

    assert opened["url"] == "http://127.0.0.1:59999/custom"
    assert started == [True]
