// meta_main.js v6.1  — MAIN world, www.meta.ai
// UNA sola tab, N slots simultáneos.
// Lógica: submitear imagen+prompt consecutivamente (sin esperar el video anterior),
// todos generan en paralelo en el backend de Meta.
// Mapeo: FIFO — el primer video nuevo que aparece en el DOM es del primer job submitado.
// Meta muestra los videos en el orden de envío → el mapeo es correcto.

(function () {
  'use strict';

  var SUBMIT_DELAY_MS = 3500;   // ms entre envíos consecutivos (upload + click + margen)
  var TIMEOUT_MS      = 600000; // 10 min por job

  // ── Estado ───────────────────────────────────────────────────────────────
  var _submitQueue = [];  // jobs pendientes de submitear al DOM
  var _pending     = [];  // [{requestId, submittedAt}] — en orden de envío, esperando video
  var _known       = new Set();   // URLs de video ya vistas (pre-seeds + resultados ya entregados)
  var _submitting  = false;       // ¿hay un submit DOM en curso?

  // Pre-seed al cargar: ignorar cualquier video que ya esté en la página
  document.querySelectorAll('video').forEach(function (v) {
    var s = v.src || v.currentSrc || v.getAttribute('src') || '';
    if (s) _known.add(s);
  });

  // ── Poll DOM: buscar <video> nuevos cada 1.5 s ───────────────────────────
  setInterval(function () {
    if (_pending.length === 0) return;

    document.querySelectorAll('video').forEach(function (v) {
      if (_pending.length === 0) return;  // ya resueltos todos
      var src = v.src || v.currentSrc || v.getAttribute('src') || '';
      if (!src) v.querySelectorAll('source').forEach(function (s) {
        src = src || s.src || s.getAttribute('src') || '';
      });
      if (!src || !src.startsWith('http') || _known.has(src)) return;
      _known.add(src);

      // FIFO: asignar al job más antiguo sin resolver
      var req = _pending.shift();
      console.log('[VF] ✅ Video #' + (_pending.length === 0 ? '(último)' : '') +
                  ' → ' + req.requestId.slice(0, 8) + '…  ' + src.slice(0, 80));
      window.postMessage({
        type: 'META_GEN_RESULT', requestId: req.requestId,
        url: src, error: '', captured: [],
      }, '*');
    });
  }, 1500);

  // ── Timeout: revisar el job más antiguo cada 5 s ─────────────────────────
  setInterval(function () {
    if (_pending.length === 0) return;
    var oldest = _pending[0];
    if (Date.now() - oldest.submittedAt > TIMEOUT_MS) {
      _pending.shift();
      console.warn('[VF] ⏰ Timeout 10min → ' + oldest.requestId.slice(0, 8));
      window.postMessage({
        type: 'META_GEN_RESULT', requestId: oldest.requestId,
        url: '', error: 'Timeout 10min sin video', captured: [],
      }, '*');
    }
  }, 5000);

  // ── Procesador de cola de submit ─────────────────────────────────────────
  function _processQueue() {
    if (_submitting || _submitQueue.length === 0) return;
    _submitting = true;
    var data = _submitQueue.shift();

    _pending.push({ requestId: data.requestId, submittedAt: Date.now() });
    console.log('[VF] 📤 Submit ' + data.requestId.slice(0, 8) + '…' +
                ' | en cola: ' + _submitQueue.length +
                ' | esperando video: ' + _pending.length);

    // Callback que se llama cuando el click "Send" fue ejecutado (NO cuando llega el video).
    // Después de SUBMIT_DELAY_MS, submitear el siguiente de la cola.
    function afterSend() {
      _submitting = false;
      if (_submitQueue.length > 0) {
        setTimeout(_processQueue, SUBMIT_DELAY_MS);
      }
    }

    if (data.image_b64) {
      _setImage(data.image_b64, data.filename, function (ok) {
        setTimeout(function () { _setPromptAndSend(data.prompt, afterSend); }, ok ? 700 : 100);
      });
    } else {
      _setPromptAndSend(data.prompt, afterSend);
    }
  }

  // ── Set image via file input ─────────────────────────────────────────────
  function _setImage(b64, filename, cb) {
    var parts = b64.split(','), mime = 'image/jpeg', raw = b64;
    if (parts.length > 1) {
      var mm = parts[0].match(/:([^;]+)/);
      mime = mm ? mm[1] : 'image/jpeg';
      raw  = parts[1];
    }
    var file;
    try {
      var bytes = atob(raw), arr = new Uint8Array(bytes.length);
      for (var i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
      file = new File([arr], filename || 'image.jpg', { type: mime });
    } catch (e) { cb(false); return; }

    var input = document.querySelector("input[type='file']");
    if (input) { _applyFile(input, file); cb(true); return; }

    var sels = [
      "[aria-label*='ttach']", "[aria-label*='mage']", "[aria-label*='Photo']",
      "[data-testid*='attach']", "button[type='button'] svg",
    ];
    var btn = null;
    for (var j = 0; j < sels.length; j++) { btn = document.querySelector(sels[j]); if (btn) break; }
    if (btn) {
      var el = btn;
      while (el && el.tagName !== 'BUTTON') el = el.parentElement;
      if (el) el.click();
      setTimeout(function () {
        input = document.querySelector("input[type='file']");
        if (input) { _applyFile(input, file); cb(true); } else { cb(false); }
      }, 400);
    } else {
      cb(false);
    }
  }

  function _applyFile(input, file) {
    try {
      var dt = new DataTransfer(); dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.dispatchEvent(new Event('input',  { bubbles: true }));
    } catch (e) {
      input.dispatchEvent(new Event('change', { bubbles: true }));
    }
  }

  // ── Escribir prompt y clickar Send — cb se llama al hacer click ──────────
  function _setPromptAndSend(prompt, cb) {
    var el = null;
    var ss = [
      "div[contenteditable='true']", "div[role='textbox']",
      "textarea[placeholder]", "textarea",
    ];
    for (var i = 0; i < ss.length; i++) {
      var c = document.querySelector(ss[i]);
      if (c && c.getBoundingClientRect().width > 0) { el = c; break; }
    }
    if (!el) {
      console.warn('[VF] ⚠️ No se encontró campo de texto — saltando submit');
      cb && cb();
      return;
    }

    el.focus();
    if (el.contentEditable === 'true') {
      document.execCommand('selectAll', false, null);
      document.execCommand('insertText', false, prompt);
    } else {
      var ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
      if (ns && ns.set) ns.set.call(el, prompt); else el.value = prompt;
    }
    el.dispatchEvent(new Event('input',  { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));

    setTimeout(function () {
      var sent = false;
      var bs = [
        "button[aria-label*='end']", "button[type='submit']",
        "div[role='button'][aria-label*='end']", "[data-testid*='send']",
        "button[aria-label*='enerate']", "button[aria-label*='nimate']",
      ];
      for (var i = 0; i < bs.length; i++) {
        var b = document.querySelector(bs[i]);
        if (b && !b.disabled && b.getAttribute('aria-disabled') !== 'true') {
          b.click(); sent = true; break;
        }
      }
      if (!sent) {
        el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, keyCode: 13, which: 13 }));
        el.dispatchEvent(new KeyboardEvent('keyup',   { key: 'Enter', bubbles: true, keyCode: 13, which: 13 }));
      }
      console.log('[VF] ▶️  Enviado: "' + prompt.slice(0, 50) + '…" — siguiente en ' + (SUBMIT_DELAY_MS/1000) + 's');
      cb && cb();
    }, 200);
  }

  // ── Listener de mensajes del bridge ─────────────────────────────────────
  window.addEventListener('message', function (ev) {
    if (ev.source !== window || !ev.data) return;
    if (ev.data.type === 'META_GEN_REQUEST') {
      _submitQueue.push(ev.data);
      _processQueue();
    }
  });

  window.postMessage({ type: 'META_MAIN_READY' }, '*');
  console.log('[VideoForge] meta_main.js v6.1 — 1 tab, N slots, submit consecutivo, FIFO mapping.');
})();
