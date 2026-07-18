"""Mock-DOM de GenTube para el bug "[S0|1] Sin imagen, reintentando... Finalizado.
0/1 imagenes." (Modulo 02).

La evidencia del propio log descarta el selector del boton/textarea: si esos
fallaran, `_GENERATE_JS` devolveria 'no_textarea'/'no_btn', no "Sin imagen" (ese
mensaje solo sale cuando el click SI funciono pero la imagen resultado nunca se
detecto). El bug real eran dos allowlists de un solo dominio de CDN
("cloudfront.net") en gentube_service.py:

1. `_block_route` (ahora `should_block_request`) bloqueaba TODO recurso tipo
   "image" que no viniera de ese dominio -- si GenTube cambio de CDN, Playwright
   abortaba la descarga de la imagen final antes de que cargara.
2. `_on_resp` (ahora `is_capturable_image_response`) solo reconocia respuestas
   de red cuya URL contuviera "cloudfront.net".
3. `_GENERATE_JS` solo reconocia `<img src="data:image...">` -- no `blob:`, el
   patron comun en apps React que renderizan el resultado con
   URL.createObjectURL(blob).

Este archivo prueba: (a) los dos helpers puros ya no dependen de un dominio
fijo, (b) el click sigue encontrando el boton correcto entre decoys sobre un
DOM simulado, y (c) el detector de imagen (`_GENERATE_JS` real, no una copia)
sigue capturando tanto `data:image` como `blob:` sin re-capturar imagenes
decorativas preexistentes."""

import base64
import json

import pytest

from src.infrastructure.ai_providers import gentube_service
from src.infrastructure.ai_providers.gentube_service import (
    _BLOB_TO_DATA_URL_JS,
    _GENERATE_JS,
    is_capturable_image_response,
    should_block_request,
)

# ── Helpers puros: should_block_request / is_capturable_image_response ──────


@pytest.mark.parametrize(
    "url,resource_type,expected",
    [
        # La imagen final puede venir de CUALQUIER dominio -- nunca debe
        # bloquearse solo por no ser el CDN historico de GenTube.
        ("https://cdn.gentube.app/results/abc.webp", "image", False),
        ("https://some-other-cdn.example.com/img.png", "image", False),
        ("https://res.cloudinary.com/gentube/image/upload/x.png", "image", False),
        # Fuentes y media siguen bloqueadas (ahorro de ancho de banda, no
        # afectan la captura de la imagen resultado).
        ("https://fonts.gstatic.com/foo.woff2", "font", True),
        ("https://gentube.app/intro.mp4", "media", True),
        # Dominios de tracking/ads siguen bloqueados, sin importar resource_type.
        ("https://www.google-analytics.com/collect", "xhr", True),
        ("https://googleads.g.doubleclick.net/pagead", "script", True),
        ("https://ph.gentube.app/e", "xhr", True),
    ],
)
def test_should_block_request_no_depende_de_un_solo_cdn(url, resource_type, expected):
    assert should_block_request(url, resource_type) is expected


@pytest.mark.parametrize(
    "url,content_type,status,expected",
    [
        # Cualquier dominio con content-type imagen y 200 OK es candidato --
        # ya no hace falta que la URL contenga "cloudfront.net".
        ("https://cdn.gentube.app/results/abc.webp", "image/webp", 200, True),
        ("https://some-other-cdn.example.com/gen/xyz.png", "image/png", 200, True),
        # Pero se sigue descartando lo obviamente decorativo.
        ("https://cdn.gentube.app/avatars/profile_42.png", "image/png", 200, False),
        ("https://cdn.gentube.app/icons/spinner.svg", "image/svg+xml", 200, False),
        # No-200 o content-type que no es imagen: descartado.
        ("https://cdn.gentube.app/results/abc.webp", "image/webp", 404, False),
        ("https://cdn.gentube.app/api/status", "application/json", 200, False),
    ],
)
def test_is_capturable_image_response_agnostico_al_dominio(url, content_type, status, expected):
    assert is_capturable_image_response(url, content_type, status) is expected


# ── Mock DOM real via Playwright: _GENERATE_JS tal como lo usa el backend ──


@pytest.fixture(scope="module")
def browser():
    if not gentube_service.playwright_available():
        pytest.skip("Playwright no instalado en este entorno")
    from playwright.sync_api import sync_playwright

    with sync_playwright() as pw:
        try:
            b = pw.chromium.launch(headless=True)
        except Exception as exc:
            pytest.skip(f"No se pudo lanzar Chromium headless: {exc}")
        yield b
        b.close()


@pytest.fixture
def page(browser):
    pg = browser.new_page()
    yield pg
    pg.close()


# HTML minimo que imita la zona de prompt de GenTube: un textarea con un boton
# "flecha" sin texto justo a su derecha (el que _GENERATE_JS debe clickear), y
# tres decoys que un selector ingenuo podria clickear por error.
_MOCK_PAGE_HTML = """
<!doctype html><html><body>
  <div style="display:flex;align-items:flex-start;position:relative;">
    <textarea id="prompt-box" style="width:300px;height:80px;"></textarea>
    <button id="send-btn" style="width:32px;height:32px;margin-left:4px;"
            onclick="window.__clicked='send-btn'"><svg></svg></button>
    <button id="tooltip-close" class="tooltip absolute-overlay"
            style="width:20px;height:20px;margin-left:4px;"
            onclick="window.__clicked='tooltip-close'"></button>
  </div>
  <button id="cancel-btn" style="width:32px;height:32px;"
          onclick="window.__clicked='cancel-btn'">Cancel</button>
  <button id="disabled-btn" style="width:32px;height:32px;" disabled
          onclick="window.__clicked='disabled-btn'"></button>
</body></html>
"""


def _run_generate(page, prompt: str = "un gato astronauta"):
    page.set_content(_MOCK_PAGE_HTML)
    page.evaluate("() => { window.__clicked = null; }")
    result = page.evaluate(_GENERATE_JS % {"prompt": json.dumps(prompt)})
    return result


def test_click_encuentra_el_boton_correcto_entre_decoys(page):
    """El boton sin texto, habilitado, pegado a la derecha del textarea gana --
    ni el que tiene texto ("Cancel"), ni el disabled, ni el marcado como
    overlay (class incluye "absolute") deben recibir el click."""
    result = _run_generate(page)

    assert result == "ok"
    clicked = page.evaluate("() => window.__clicked")
    assert clicked == "send-btn", f"debio clickear send-btn, pero clickeo: {clicked}"

    prompt_value = page.eval_on_selector("#prompt-box", "el => el.value")
    assert prompt_value == "un gato astronauta"


def test_sin_textarea_devuelve_no_textarea(page):
    page.set_content("<!doctype html><html><body><p>sin textarea aca</p></body></html>")
    result = page.evaluate(_GENERATE_JS % {"prompt": '"hola"'})
    assert result == "no_textarea"


# ── Deteccion de la imagen final: data: (clasico) y blob: (apps React modernas) ──


def _wait_for_gt_img(page, timeout_s: float = 3.0) -> str | None:
    import time

    deadline = time.time() + timeout_s
    while time.time() < deadline:
        val = page.evaluate("() => window.__gt_img || null")
        if val:
            return val
        time.sleep(0.05)
    return None


def test_detecta_imagen_data_uri_nueva_e_ignora_las_preexistentes(page):
    """Imagen decorativa YA en el DOM antes de generar (icono chico, o incluso
    un data: URI largo pero preexistente) no debe contarse -- solo una nueva
    que aparezca despues del click, y suficientemente grande para ser un
    resultado real (no un icono inline)."""
    page.set_content(_MOCK_PAGE_HTML)
    # Icono decorativo YA presente antes de generar.
    small_icon = "data:image/png;base64,iVBORw0KGgoAAAANSU"
    page.evaluate(
        "(src) => { const i = document.createElement('img'); i.src = src; document.body.appendChild(i); }",
        small_icon,
    )

    _run_generate(page)

    # Simula que GenTube renderizo el resultado: una imagen NUEVA, grande.
    fake_bytes = b"fake-png-bytes-" * 500  # bien por encima del umbral de 5000 chars
    big_data_uri = "data:image/png;base64," + base64.b64encode(fake_bytes).decode()
    page.evaluate(
        "(src) => { const i = document.createElement('img'); i.src = src; document.body.appendChild(i); }",
        big_data_uri,
    )

    captured = _wait_for_gt_img(page)
    assert captured == big_data_uri, "debio capturar la imagen NUEVA y grande, no la decorativa preexistente"


def test_detecta_imagen_blob_url_y_se_puede_convertir_a_data_url(page):
    """GenTube puede renderizar el resultado con URL.createObjectURL(blob) en
    vez de un data: URI inline -- _GENERATE_JS debe reconocer blob: tambien, y
    _BLOB_TO_DATA_URL_JS debe poder leer esos bytes desde el contexto de la
    pagina (el unico lugar donde el Blob realmente vive)."""
    _run_generate(page)

    original_bytes = b"contenido-fake-de-imagen-generada-por-gentube"
    blob_url = page.evaluate(
        """
        (b64) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            const blob = new Blob([bytes], {type: 'image/png'});
            const url = URL.createObjectURL(blob);
            const img = document.createElement('img');
            img.src = url;
            document.body.appendChild(img);
            return url;
        }
        """,
        base64.b64encode(original_bytes).decode(),
    )
    assert blob_url.startswith("blob:")

    captured = _wait_for_gt_img(page)
    assert captured == blob_url, "debio capturar la URL blob: nueva"

    data_url = page.evaluate(_BLOB_TO_DATA_URL_JS, captured)
    assert data_url.startswith("data:image/png;base64,")
    header, _, b64data = data_url.partition(",")
    assert base64.b64decode(b64data) == original_bytes, (
        "la conversion blob: -> data: debe preservar los bytes originales exactos"
    )
