from pathlib import Path
from urllib.parse import urlparse
from urllib.request import url2pathname

from desktop import window


def _path_from_file_uri(uri: str) -> Path:
    return Path(url2pathname(urlparse(uri).path))


def test_screen_size_devuelve_dimensiones_positivas():
    w, h = window._screen_size()
    assert w > 0
    assert h > 0


def test_loading_html_incluye_url_destino_url_de_salud_y_titulo():
    html = window._loading_html(
        "http://127.0.0.1:59999/custom", "http://127.0.0.1:59999/api/health", "Studio IVR"
    )
    assert "http://127.0.0.1:59999/custom" in html
    assert "http://127.0.0.1:59999/api/health" in html
    assert "Studio IVR" in html
    assert "no-cors" in html


def test_write_loading_page_crea_archivo_html_legible():
    html = window._loading_html("http://127.0.0.1:1/x", "http://127.0.0.1:1/api/health", "Studio IVR")
    path = window._write_loading_page(html)
    try:
        assert path.exists()
        assert path.read_text(encoding="utf-8") == html
    finally:
        path.unlink(missing_ok=True)


def test_run_cae_a_navegador_con_vf_no_webview(monkeypatch):
    monkeypatch.setenv("VF_NO_WEBVIEW", "1")
    opened = {}
    monkeypatch.setattr(window.webbrowser, "open", lambda url: opened.setdefault("url", url))

    started = []
    window.run(lambda: started.append(True), url="http://127.0.0.1:59999/custom")

    assert opened["url"].startswith("file:")
    opened_path = _path_from_file_uri(opened["url"])
    try:
        assert opened_path.exists()
        contents = opened_path.read_text(encoding="utf-8")
        assert "http://127.0.0.1:59999/custom" in contents
    finally:
        opened_path.unlink(missing_ok=True)
    assert started == [True]
