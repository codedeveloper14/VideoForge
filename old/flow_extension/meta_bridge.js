// meta_bridge.js v9.0 — Isolated world, www.meta.ai
// Modo MULTI-SLOT, 2 JOBS EN VUELO POR PESTAÑA: meta_token_gen.js v6.0 agregó
// correlación por posición en el DOM (cada job vigila su propio contenedor de
// mensaje hasta ver su data-video-url propio), que ya no depende del orden de
// llegada de eventos del WebSocket — eso es lo que hace seguro tener más de 1
// job en vuelo sin mezclar contenido entre ellos. El DOM del slot solo se
// resetea navegando cuando la cola de trabajo lleva un rato realmente vacía —
// nunca a mitad de un lote, para no destruir jobs todavía pendientes.

(function () {
  'use strict';

  var BRIDGE       = 'http://127.0.0.1:8080';
  var POLL_FAST_MS  = 500;
  var POLL_IDLE_MS  = 2500;
  // v9.0: subido de 1 a 2. meta_token_gen.js v6.0 agregó correlación por
  // POSICIÓN EN EL DOM — cada job se asocia a su propio contenedor de mensaje
  // (data-message-id) en cuanto aparece, y se vigila SOLO ese nodo hasta ver
  // su data-video-url propio. El orden de esos contenedores en el DOM SIEMPRE
  // respeta el orden de envío, sin importar cuál termine de generar primero
  // — a diferencia del FIFO por WebSocket (que sí se puede desincronizar si
  // Meta genera en paralelo), esto ya no depende de adivinar orden de
  // llegada. Con eso, tener 2 jobs en vuelo por pestaña ya no puede mezclar
  // su contenido. Probado en MAX_INFLIGHT=3: empeoró (más duplicados/desorden)
  // — revertido a 2, que fue la última configuración confirmada limpia por
  // el usuario. No volver a subir esto sin pruebas extensas primero.
  var MAX_INFLIGHT  = 2;
  // Subirlo a 45s causó MÁS duplicados — pero eso fue probado con
  // MAX_INFLIGHT=3, donde varios jobs compartían composer/conversación y
  // este reset (navigate a /) era la única red de seguridad real contra
  // basura de adjuntos acumulada entre ellos. Con MAX_INFLIGHT=1 ya no hay
  // jobs simultáneos compitiendo, y _clearExistingAttachments (meta_token_gen.js)
  // limpia de forma determinística ANTES de cada imagen nueva — el reset ya
  // no es la única defensa, así que subirlo aquí es seguro. En 5000ms, si
  // Flask tarda más de 5s en tener listo el siguiente job (normal: preparar
  // la imagen, etc.), la pestaña navegaba y recargaba TODA la página justo
  // cuando el siguiente job estaba por llegar — esa recarga completa era la
  // demora "entre jobs" reportada. Con margen amplio, el reset solo actúa
  // como limpieza de respaldo si la pestaña queda realmente sin trabajo.
  var RESET_IDLE_MS = 30000;

  // ── Slot ID persistente — sobrevive navigate de reseteo ────────────────
  // sessionStorage, NO localStorage: localStorage se comparte entre TODAS
  // las pestañas del mismo origen (meta.ai), así que con 2+ pestañas todas
  // leían la MISMA clave y terminaban con el MISMO _slotId — Flask las veía
  // como una sola cuenta compitiendo por la misma cola (de ahí que todas
  // generaran los mismos jobs 001,002,003...). sessionStorage es exclusivo
  // de cada pestaña, pero sigue sobreviviendo si ESA pestaña navega/resetea.
  var LS_SLOT_KEY = 'vf_meta_slot_id';
  var _slotId = null;
  try { _slotId = sessionStorage.getItem(LS_SLOT_KEY); } catch (_) {}
  if (!_slotId) {
    _slotId = 'ms_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
    try { sessionStorage.setItem(LS_SLOT_KEY, _slotId); } catch (_) {}
  }

  var _inFlight   = 0;
  var _pollTimer  = null;
  var _resetTimer = null;
  // Antes (RESET_IDLE_MS=5000) la pestaña recargaba constantemente entre
  // jobs — efecto secundario no buscado pero confirmado por el usuario: esas
  // recargas frecuentes evitaban que Chrome acumulara "deuda" de throttling
  // en pestañas que llevan mucho tiempo en segundo plano. Al subir
  // RESET_IDLE_MS a 30s (para no recargar a mitad de un hueco normal entre
  // jobs), bajo carga continua la cola casi nunca queda idle 30s, así que el
  // reset por inactividad prácticamente deja de disparar — la pestaña puede
  // pasar MUCHO tiempo sin recargar mientras el usuario trabaja en otra
  // ventana, acumulando throttling hasta quedar "pegada" sin revivir sola.
  // Este contador fuerza un reset periódico por CANTIDAD de jobs, sin
  // importar si hay más trabajo en cola — recupera ese efecto sin volver a
  // la demora de recargar entre cada job individual.
  var JOBS_PER_RESET   = 6;
  var _jobsSinceReset  = 0;

  // ── Registro con Flask ────────────────────────────────────────────────
  function _register() {
    fetch(BRIDGE + '/api/meta/ext-register?account=' + encodeURIComponent(_slotId))
      .catch(function () {});
  }

  // ── Poll Flask — hasta MAX_INFLIGHT jobs en vuelo por slot ─────────────
  function _poll() {
    var capacity = MAX_INFLIGHT - _inFlight;
    if (capacity <= 0) { _schedulePoll(POLL_FAST_MS); return; }

    fetch(BRIDGE + '/api/meta/ext-poll?account=' + encodeURIComponent(_slotId) + '&max=' + capacity)
      .then(function (r) { return r.json(); })
      .then(function (data) {
        var reqs = data.requests || (data.request ? [data.request] : []);
        reqs.forEach(function (req) {
          _inFlight++;
          if (_resetTimer) { clearTimeout(_resetTimer); _resetTimer = null; }
          console.log('[VF Bridge] 🎬 Job slot=' + _slotId.slice(0, 12) + ' req=' + req.requestId.slice(0, 8) + ' | en vuelo=' + _inFlight);
          window.postMessage({
            type:      'META_GEN_REQUEST',
            requestId: req.requestId,
            image_b64: req.image_b64 || '',
            prompt:    req.prompt    || '',
            filename:  req.filename  || 'image.jpg',
          }, '*');
        });
        _schedulePoll(reqs.length > 0 ? POLL_FAST_MS : POLL_IDLE_MS);
      })
      .catch(function () { _schedulePoll(POLL_IDLE_MS); });
  }

  function _schedulePoll(ms) {
    if (_pollTimer) clearTimeout(_pollTimer);
    _pollTimer = setTimeout(_poll, ms);
  }

  // ── Listeners de meta_token_gen.js ────────────────────────────────────
  window.addEventListener('message', function (ev) {
    if (ev.source !== window || !ev.data) return;

    // meta_token_gen.js (MAIN world) no tiene acceso a chrome.runtime — esta
    // pestaña (ISOLATED world) hace de puente para pedirle a background.js
    // que le sostenga el foco mientras adjunta+envía, en vez de depender de
    // que le toque turno en la rotación fija (con varias pestañas, ese turno
    // podía ser muy corto y dejar el adjunto a medias).
    if (ev.data.type === 'META_NEED_FOCUS' || ev.data.type === 'META_FOCUS_DONE') {
      try { chrome.runtime.sendMessage({ type: ev.data.type }, function () { void chrome.runtime.lastError; }); } catch (_) {}
      return;
    }

    // meta_token_gen.js listo → registrar y arrancar
    if (ev.data.type === 'META_MAIN_READY') {
      _register();
      _schedulePoll(1000);
      return;
    }

    // OAuth/tenant capturado → reportar a Flask
    if (ev.data.type === 'META_LEARNED_STATE') {
      var st = ev.data.state || {};
      if (st.oauth_token || st.upload_tenant) {
        fetch(BRIDGE + '/api/meta/ext-learn', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ account: _slotId, state: st }),
        }).catch(function () {});
      }
      return;
    }

    // Job completado → enviar resultado. El reset del DOM se programa con un
    // debounce: si llega más trabajo antes de RESET_IDLE_MS, se cancela.
    if (ev.data.type === 'META_GEN_RESULT') {
      var d = ev.data;
      _inFlight = Math.max(0, _inFlight - 1);
      console.log('[VF Bridge]', d.url ? '✅' : '❌',
        'req=' + d.requestId.slice(0, 8), '| en vuelo=' + _inFlight,
        d.url ? d.url.slice(0, 70) : (d.error || '').slice(0, 80));

      try {
        fetch(BRIDGE + '/api/meta/ext-result', {
          method:    'POST',
          headers:   { 'Content-Type': 'application/json' },
          body:      JSON.stringify({ requestId: d.requestId, url: d.url || '', error: d.error || '' }),
          keepalive: true,
        }).catch(function () {});
      } catch (_) {}

      // Reset periódico por cantidad de jobs (ver comentario junto a
      // JOBS_PER_RESET) — no espera a que la cola quede idle, solo a que no
      // haya un job en vuelo en este instante (lo normal justo aquí, recién
      // bajado a 0 arriba).
      _jobsSinceReset++;
      if (_jobsSinceReset >= JOBS_PER_RESET && _inFlight === 0) {
        _jobsSinceReset = 0;
        if (_resetTimer) clearTimeout(_resetTimer);
        if (_pollTimer) clearTimeout(_pollTimer);
        _pollTimer = null;
        window.location.href = 'https://www.meta.ai/';
        return;
      }

      // / (home) confirmado funcional con el selector real ([data-testid=
      // 'composer-input']) + reintentos de meta_token_gen.js — las fallas
      // anteriores eran de selectores viejos/timing, no de la página en sí.
      if (_resetTimer) clearTimeout(_resetTimer);
      _resetTimer = setTimeout(function () {
        if (_inFlight > 0) return; // llegó más trabajo mientras esperábamos — no resetear
        if (_pollTimer) clearTimeout(_pollTimer);
        _pollTimer = null;
        window.location.href = 'https://www.meta.ai/';
      }, RESET_IDLE_MS);
    }
  });

  // Heartbeat para que Flask sepa que el slot sigue vivo
  setInterval(_register, 20000);

  // Arranque con pequeño delay para que meta_token_gen.js esté listo
  setTimeout(function () {
    _register();
    _schedulePoll(2000);
  }, 1500);

  console.log('[VideoForge] meta_bridge.js v9.0 — slot=' + _slotId + ' | max en vuelo=' + MAX_INFLIGHT + ' (correlación por DOM en meta_token_gen.js v6.0, ya no por FIFO de WebSocket) | RESET_IDLE_MS=' + RESET_IDLE_MS + ' | reset forzado cada ' + JOBS_PER_RESET + ' jobs (no solo por inactividad) — recupera el efecto de las recargas frecuentes de RESET_IDLE_MS=5000 que sin querer evitaban que Chrome acumulara throttling en pestañas mucho tiempo en segundo plano.');
})();
