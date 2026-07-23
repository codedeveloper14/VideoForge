window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data && event.data.type === "IMPERIO_QWEN_TOKEN") {
    chrome.runtime.sendMessage({ action: "qwenToken", token: event.data.token });
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "requestQwenToken") {
    window.postMessage({ type: "IMPERIO_REQUEST_QWEN_TOKEN" }, "*");
    sendResponse({ ok: true });
  }
  return true;
});

// ─────────────────────────────────────────────────────────────────
// Bridge de generacion -- DOM real, no fetch(). Confirmado en vivo
// (2026-07-22): un fetch() a create_chat/submit_completion, aunque salga de
// esta misma pestaña autenticada, recibe el mismo challenge del WAF de
// Alibaba que curl_cffi desde Python (HTML con markers aliyun_waf_aa/
// aliyun_waf_bb) -- fetch() nunca ejecuta el JS del challenge embebido en la
// respuesta, sea quien sea el que lo dispare. La unica forma real de generar
// es que la request salga del propio bundle de Qwen ya cargado y
// autenticado: simular la interaccion real (click en "+", elegir "Crear
// Video", adjuntar imagen, escribir el prompt, click en Enviar) y esperar a
// que aparezca el <video> real en el DOM. Confirmado con una generacion
// real de punta a punta usando Playwright antes de escribir esto.
//
// El input de archivo (#filesUpload) no se puede llenar por JS -- ningun
// script, en ningun navegador ni contexto, puede asignar input.files (regla
// de seguridad del browser). Por eso adjuntar la imagen se delega a
// background.js via chrome.debugger/CDP (mensaje QWEN_ATTACH_FILE) -- el
// mismo mecanismo que usan Playwright/Puppeteer por debajo.
//
// Los textos ("Crear Video", "Enviar", "Nuevo Chat") se vieron en español e
// ingles en la misma cuenta en distintas cargas de pagina -- todo matching
// de texto acepta ambas variantes.
//
// run_at:"document_start" en manifest.json -- necesario para capturar
// ?imperio_qwen_account=<nombre> ANTES de que el router propio del SPA de
// Qwen lo reescriba/elimine de la URL. Se guarda en sessionStorage para
// sobrevivir a un redirect posterior que recargue la pagina.
(() => {
  const params = new URLSearchParams(location.search);
  const urlAccount = params.get("imperio_qwen_account");
  if (urlAccount) {
    try {
      sessionStorage.setItem("imperio_qwen_account", urlAccount);
    } catch (e) {}
  }
  let accountName = urlAccount;
  if (!accountName) {
    try {
      accountName = sessionStorage.getItem("imperio_qwen_account") || "";
    } catch (e) {
      accountName = "";
    }
  }
  if (!accountName) return;

  function sendResult(payload) {
    try {
      chrome.runtime.sendMessage({ type: "QWEN_RESULT", payload });
    } catch (e) {}
  }

  function sleep(ms) {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  async function waitFor(fn, timeoutMs, intervalMs) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const v = fn();
      if (v) return v;
      await sleep(intervalMs);
    }
    return null;
  }

  // Ant Design (la libreria de UI de Qwen) escucha una secuencia real de
  // eventos de mouse, no solo .click() -- mas confiable disparar la
  // secuencia completa, igual de espiritu que el realClick() de
  // vibes_bridge.js (ahi por Radix, aca por las dudas con Ant Design).
  function realClick(el) {
    if (!el) return false;
    const rect = el.getBoundingClientRect();
    const opts = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: rect.x + rect.width / 2,
      clientY: rect.y + rect.height / 2,
    };
    ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach((type) => {
      el.dispatchEvent(new MouseEvent(type, opts));
    });
    return true;
  }

  function findByText(selector, variants) {
    const els = Array.from(document.querySelectorAll(selector));
    return els.find((el) => variants.includes((el.innerText || el.textContent || "").trim()));
  }

  // React no detecta un simple `el.value = x` -- hay que pasar por el
  // setter nativo del prototipo para que su listener de "input" dispare y
  // el estado interno del componente se actualice.
  function setNativeValue(el, value) {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, "value");
    if (desc && desc.set) desc.set.call(el, value);
    else el.value = value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
  }

  async function newChat() {
    const el = findByText("div, a, span, button", ["Nuevo Chat", "New Chat"]);
    if (el) {
      realClick(el);
      await sleep(800);
    }
  }

  async function openVideoMode() {
    const plusBtn = document.querySelector('[aria-label="Seleccionar modo"], [aria-label="Select mode"]');
    if (!plusBtn) throw new Error('boton "+" (Seleccionar modo) no encontrado');
    realClick(plusBtn);
    const item = await waitFor(() => findByText(".ant-dropdown-menu-item", ["Crear Video", "Create Video"]), 5000, 200);
    if (!item) throw new Error('opcion "Crear Video" no encontrada en el menu');
    realClick(item);
    await sleep(500);
  }

  async function attachImage(imagePath) {
    const resp = await chrome.runtime.sendMessage({
      type: "QWEN_ATTACH_FILE",
      selector: "#filesUpload",
      filePaths: [imagePath],
    });
    if (!resp || !resp.ok) {
      throw new Error("no se pudo adjuntar la imagen: " + ((resp && resp.error) || "sin respuesta del background"));
    }
    await sleep(1500); // tiempo para que la app procese el archivo recien adjuntado
  }

  function typePrompt(text) {
    const ta = document.querySelector(".message-input-textarea");
    if (!ta) throw new Error("caja de texto del prompt no encontrada");
    ta.focus();
    setNativeValue(ta, text);
  }

  async function clickSend() {
    const btn = await waitFor(
      () => document.querySelector('button.send-button[aria-label="Enviar"], button.send-button[aria-label="Send"]'),
      5000,
      200,
    );
    if (!btn) throw new Error('boton "Enviar" no encontrado');
    realClick(btn);
  }

  function extractVideoUrl() {
    const video = document.querySelector("video");
    if (!video) return "";
    return video.currentSrc || video.src || "";
  }

  async function runJob(job) {
    const requestId = job.requestId;
    try {
      await newChat();
      await openVideoMode();
      if (job.imagePath) {
        await attachImage(job.imagePath);
      }
      typePrompt(job.prompt);
      await sleep(300);
      await clickSend();

      const timeoutMs = (job.timeoutSec || 600) * 1000;
      const videoUrl = await waitFor(extractVideoUrl, timeoutMs, 3000);
      if (!videoUrl) {
        sendResult({ requestId, status: 0, error: "Timeout esperando el video (no aparecio <video> en el DOM)" });
        return;
      }
      sendResult({ requestId, status: 200, videoUrl });
    } catch (exc) {
      sendResult({ requestId, status: 0, error: String((exc && exc.message) || exc) });
    }
  }

  function register() {
    try {
      chrome.runtime.sendMessage({ type: "REGISTER_QWEN_ACCOUNT", account: accountName });
    } catch (e) {}
  }

  chrome.runtime.onMessage.addListener((msg) => {
    if (!msg || msg.type !== "QWEN_JOB") return;
    runJob(msg.job);
  });

  register();
  // Re-registrar periodicamente -- mismo patron que vibes_relay.js, cubre el
  // caso de que el service worker se haya suspendido (MV3) y perdido el registro.
  setInterval(register, 45000);
})();
