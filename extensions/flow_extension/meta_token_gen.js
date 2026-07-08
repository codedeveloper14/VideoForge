// meta_token_gen.js v2.0 — MAIN world, www.meta.ai
// DESCUBRIMIENTO CLAVE (HAR analysis, ver historial de chat):
//   El envío del prompt en meta.ai NO pasa por GraphQL. Pasa por un WebSocket
//   binario propietario (wss://gateway.meta.ai/ws/clippy, protocolo Protobuf
//   interno "DGW/Ecto", sin schema público). Por eso v1.x nunca logró capturar
//   un "real_send_doc_id" — no existe, ese mutation no está en GraphQL.
//
// ESTRATEGIA v2.0 — híbrida:
//   1. Enviar (imagen + prompt) sigue siendo vía DOM real — es lo único que
//      dispara confiablemente el agente de IA de Meta sobre su WS propietario.
//   2. Para obtener el resultado YA NO se hace polling lento del <video> del DOM.
//      Se interceptan los frames RECIBIDOS del WebSocket (sin decodificar el
//      Protobuf completo — el media_id final aparece en texto plano dentro del
//      frame como "fbid://123456789") y, en cuanto aparece uno nuevo, se usa
//      para hacer polling DIRECTO por GraphQL (DOC_GEN + SSE, ya confirmado
//      funcional) en vez de esperar a que el DOM renderice el <video>.
//   3. Si el sniffer del WS no encuentra nada a tiempo (cambio de protocolo,
//      frame binario distinto, etc.), el polling del DOM sigue activo en
//      paralelo como fallback — nunca se pierde el resultado, solo se vuelve
//      más lento (igual que v1.x).

(function () {
  'use strict';

  // ── Endpoints y doc_ids confirmados por captura de red ─────────────────
  var GQL            = 'https://www.meta.ai/api/graphql';
  var DOC_WARMUP      = 'e7f802582dbfed8e181b012e010993eb';
  var DOC_MODE         = 'c32bbe999c48e64e855dc63177d5153f';
  var DOC_GEN          = '9928a9b87ec492a16326f18925191c0f';
  var DOC_FETCH_CONV   = '4fd795143fc5b90fc1fc3ca716bdbb86';
  var WS_URL_SUBSTR    = 'gateway.meta.ai/ws/clippy';

  // ── Estado persistido (solo lo que necesitan las llamadas GraphQL propias) ─
  var LS_KEY = 'vf_meta_tok_v2';
  var _S = {
    asbd_id:    null,
    csrftoken:  null,
    lsd:        null,  // x-fb-lsd — NUNCA se persiste (es de sesión)
  };
  function _load() {
    try {
      var s = localStorage.getItem(LS_KEY);
      if (!s) return;
      var p = JSON.parse(s);
      for (var k in p) { if (k !== 'lsd') _S[k] = p[k]; }
    } catch (_) {}
  }
  function _save() {
    try {
      var out = {};
      for (var k in _S) { if (k !== 'lsd') out[k] = _S[k]; }
      localStorage.setItem(LS_KEY, JSON.stringify(out));
    } catch (_) {}
  }
  _load();

  // ── Estado en memoria ────────────────────────────────────────────────────
  var _lastConvId      = null;       // conversationId visto en el último WARMUP/MODE de la página
  var _knownVideos     = new Set();  // claves canónicas (sin host de CDN) de video ya vistas
  // Meta sirve el MISMO video desde distintos hosts de borde del CDN
  // (scontent-ord5-3 vs scontent-iad3-1, etc.) con idéntica ruta/blob —
  // comparar la URL completa como string deja pasar duplicados reales. Solo
  // los últimos 2 segmentos del path (carpeta "mNNN" + id del blob, sin
  // query string que puede variar por token firmado) identifican el video.
  function _videoKey(url) {
    if (!url) return url;
    var noQuery = url.split('?')[0];
    var parts = noQuery.split('/').filter(Boolean);
    return parts.slice(-2).join('/');
  }
  function _markKnownVideo(url) { if (url) _knownVideos.add(_videoKey(url)); }
  function _isKnownVideo(url) { return !!url && _knownVideos.has(_videoKey(url)); }
  var _recentVideoUrls = [];         // [{url, ts}] — URLs vistas vía fetch hook / MutationObserver
  var _knownMediaIds   = new Set();  // media ids ya vistos vía sniff del WS
  var _wsMediaBuffer   = [];         // [{id, ts}] — media ids nuevos detectados en el WS
  var _suppressNextMediaId = 0;      // se incrementa al ver un error de Ecto — ver más abajo
  var _submitQueue     = [];         // jobs aún no enviados por DOM
  var _pending         = [];         // [{requestId, deadline, claimed}] en orden de envío — FIFO
  var _submitting      = false;
  // Flask re-encola jobs que considera "perdidos" (timeout de silencio del
  // bridge), pero a veces el job NO estaba perdido — solo lento — y termina
  // llegando dos veces el mismo requestId. Sin esto se procesa (y genera)
  // dos veces, produciendo dos videos casi idénticos de la misma imagen.
  var _seenRequestIds  = new Set();
  // Antes de v4.1, los ~5s desperdiciados reintentando "Nuevo chat" (10×500ms,
  // nunca encontraba el botón) le daban a Meta tiempo de sobra para terminar
  // de procesar el envío anterior en su backend antes de que llegara el
  // siguiente — aunque inútil para su propósito original, funcionaba como
  // colchón accidental. Al quitarlo (v4.1, por velocidad) los envíos quedaron
  // más pegados entre sí: la miniatura correcta puede confirmarse en el DOM
  // mientras el backend de Meta todavía está "asentando" el job anterior y
  // usa su contexto viejo — produciendo un video con la imagen equivocada
  // aunque todo lo verificable del lado del navegador esté correcto. Subido
  // de 3500 a 8000 para restaurar ese colchón sin volver al polling inútil.
  var SUBMIT_DELAY_MS  = 8000;       // ms entre envíos consecutivos (no se espera el video anterior)
  var JOB_TIMEOUT_MS   = 600000;     // 10 min por job

  // ── _origFetch — hook solo para capturar LSD/ASBD/CSRF + conversationId ──
  var _origFetch = window.fetch.bind(window);
  window.fetch = function (url, opts) {
    var p = _origFetch.apply(this, arguments);

    var urlStr, hObj, bObj;
    if (url instanceof Request) {
      urlStr = url.url || '';
      hObj   = (opts && opts.headers) || url.headers;
      bObj   = opts && opts.body;
      if (urlStr.indexOf('/api/graphql') !== -1) {
        try {
          url.clone().text().then(function (bodyTxt) {
            try { _trackConvId(JSON.parse(bodyTxt)); } catch (_) {}
          }).catch(function () {});
        } catch (_) {}
      }
    } else {
      urlStr = typeof url === 'string' ? url : (url && url.toString ? url.toString() : '');
      hObj   = opts && opts.headers;
      bObj   = opts && opts.body;
    }

    function _hdr(k) {
      if (!hObj) return '';
      return typeof hObj.get === 'function'
        ? (hObj.get(k) || hObj.get(k.toLowerCase()) || '')
        : (hObj[k] || hObj[k.toLowerCase()] || '');
    }

    if (urlStr.indexOf('/api/graphql') !== -1 && hObj) {
      var prevLsd = _S.lsd;
      if (!_S.lsd       && _hdr('x-fb-lsd'))     { _S.lsd       = _hdr('x-fb-lsd'); }
      if (!_S.asbd_id   && _hdr('x-asbd-id'))    { _S.asbd_id   = _hdr('x-asbd-id'); }
      if (!_S.csrftoken && _hdr('x-csrftoken'))  { _S.csrftoken = _hdr('x-csrftoken'); }
      if (!prevLsd && _S.lsd) _save();
    }

    if (urlStr.indexOf('/api/graphql') !== -1 && bObj) {
      try { _trackConvId(typeof bObj === 'string' ? JSON.parse(bObj) : bObj); } catch (_) {}
    }

    // Observar respuestas GQL JSON: URLs de video (defensa adicional, además del sniff del WS)
    if (urlStr.indexOf('/api/graphql') !== -1) {
      p.then(function (resp) {
        if (!resp || !resp.ok) return;
        var ct = (resp.headers && resp.headers.get('content-type')) || '';
        if (ct.indexOf('event-stream') !== -1) return;
        resp.clone().text().then(function (txt) {
          var plain = txt.replace(/\\\//g, '/');
          var vurl = _extractURL(plain);
          if (vurl) {
            _recentVideoUrls.push({ url: vurl, ts: Date.now() });
            if (_recentVideoUrls.length > 20) _recentVideoUrls.shift();
          }
        }).catch(function () {});
      }).catch(function () {});
    }

    return p;
  };

  // El WARMUP y el MODE los dispara la propia app de meta.ai al abrir un chat
  // nuevo / seleccionar modo "Creación" — solo necesitamos leer su conversationId,
  // NUNCA llamarlos nosotros mismos.
  function _trackConvId(body) {
    if (!body || typeof body !== 'object') return;
    if (body.doc_id === DOC_WARMUP && body.variables && body.variables.conversationId) {
      _lastConvId = body.variables.conversationId;
    } else if (body.doc_id === DOC_MODE && body.variables && body.variables.input && body.variables.input.conversationId) {
      _lastConvId = body.variables.input.conversationId;
    }
  }

  // ── Sniffer de WebSocket: detecta media_id sin decodificar el Protobuf ───
  // El servidor manda el id final como "fbid://123456" (con distintos niveles
  // de escapado \/ según cuántas capas de JSON-dentro-de-JSON tenga el frame)
  // en texto plano dentro del payload binario — no hace falta parsear el
  // Protobuf, basta un regex tolerante a cualquier cantidad de backslashes.
  var FBID_RE = /fbid:[\\\/]+(\d{6,})/g;

  function _bytesToLatin1(buf) {
    var u8 = buf instanceof ArrayBuffer ? new Uint8Array(buf) : buf;
    var s = '';
    for (var i = 0; i < u8.length; i++) s += String.fromCharCode(u8[i]);
    return s;
  }

  // ── Correlación por req-id (más confiable que FIFO) ────────────────────
  // Cada frame de envío real lleva {"req-id":"<uuid>","payload":...}, y el
  // servidor ECO ese mismo uuid junto con el resultado en los frames de
  // respuesta (confirmado en captura HAR: "$<uuid>" aparece en ambos lados).
  // Si Meta no genera los videos en el mismo orden en que se enviaron (un
  // job más simple puede terminar antes que uno enviado primero), el mapeo
  // FIFO asigna mal. Con req-id sabemos EXACTAMENTE de qué job es cada
  // resultado, sin asumir orden. FIFO queda solo de respaldo si esto falla.
  var REQID_RE      = /[\$"]([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})/i;
  var _reqIdToEntry = {};   // req-id → entry de _pending, armado al enviar
  var _pendingSendMatch = null;  // entry esperando que su ws.send() real ocurra

  function _removeFromPending(entry) {
    var idx = _pending.indexOf(entry);
    if (idx !== -1) _pending.splice(idx, 1);
    entry.claimed = true;
  }
  function _resolveDirectMatch(entry, mediaId) {
    _removeFromPending(entry);
    _pollMediaResult(mediaId, _lastConvId, entry.deadline)
      .then(function (url) { _deliverResult(entry, url); })
      .catch(function (err) { console.warn('[VF] ⚠️ pollMediaResult:', String(err).slice(0, 100)); _deliverResult(entry, null); });
  }

  function _scanFrameForMediaId(data) {
    var str = typeof data === 'string' ? data : _bytesToLatin1(data);
    var m;
    FBID_RE.lastIndex = 0;
    while ((m = FBID_RE.exec(str)) !== null) {
      var id = m[1];
      if (_knownMediaIds.has(id)) continue;
      _knownMediaIds.add(id);

      var rm = str.match(REQID_RE);
      var matchedEntry = rm ? _reqIdToEntry[rm[1].toLowerCase()] : null;
      if (matchedEntry) {
        delete _reqIdToEntry[rm[1].toLowerCase()];
        console.log('[VF] 🔌🔗 media_id (correlación directa por req-id):', id, '→', matchedEntry.requestId.slice(0, 8));
        _resolveDirectMatch(matchedEntry, id);
      } else {
        _wsMediaBuffer.push({ id: id, ts: Date.now() });
        if (_wsMediaBuffer.length > 20) _wsMediaBuffer.shift();
        console.log('[VF] 🔌 media_id detectado (sin req-id, FIFO de respaldo):', id);
      }
    }
  }

  function _scanFrameForReqId(data) {
    if (!_pendingSendMatch) return;
    var str = typeof data === 'string' ? data : _bytesToLatin1(data);
    var m = str.match(/"req-id"\s*:\s*"([0-9a-f-]{36})"/i);
    if (m) {
      _reqIdToEntry[m[1].toLowerCase()] = _pendingSendMatch;
      console.log('[VF] 🔗 req-id armado:', m[1], '→', _pendingSendMatch.requestId.slice(0, 8));
      _pendingSendMatch = null;
    }
  }

  // La correlación directa por req-id (arriba) nunca se dispara en la
  // práctica — todo pasa por el FIFO de respaldo, que asume que cada
  // media_id nuevo en el WS corresponde al siguiente job pendiente en orden
  // de envío. Eso se rompe cuando Meta reintenta internamente tras un error
  // de polling (visible como "[EctoVideoPollingContext] Video generation
  // error" en su propia consola) y vuelve a emitir un media_id "fantasma"
  // para ese reintento — el FIFO no tiene forma de distinguirlo de uno
  // legítimo y se lo asigna al job equivocado, produciendo el corrimiento en
  // cascada (8→9→10→11…) observado en pruebas reales. Mitigación: al ver ese
  // error, se descarta el siguiente media_id de respaldo que llegue. Si la
  // suposición es errónea alguna vez, el peor caso es que ESE job reintente
  // (ya hay retry) — mucho mejor que entregarle el video de otro job.
  try {
    var _origConsoleError = console.error.bind(console);
    console.error = function () {
      try {
        for (var _i = 0; _i < arguments.length; _i++) {
          var _a = arguments[_i];
          if (_a && (_a === 'EctoVideoPollingContext' || (typeof _a === 'string' && _a.indexOf('EctoVideoPollingContext') !== -1))) {
            _suppressNextMediaId++;
            console.warn('[VF] ⚠️ EctoVideoPollingContext error — se descartará el próximo media_id de respaldo (probable reintento fantasma)');
            break;
          }
        }
      } catch (_) {}
      return _origConsoleError.apply(console, arguments);
    };
  } catch (_) {}

  var _OrigWS = window.WebSocket;
  function _WSProxy(url, protocols) {
    var ws = protocols !== undefined ? new _OrigWS(url, protocols) : new _OrigWS(url);
    if (typeof url === 'string' && url.indexOf(WS_URL_SUBSTR) !== -1) {
      console.log('[VF] 🔌 WS clippy detectado — instalando sniffer de media_id');
      ws.addEventListener('message', function (ev) {
        try {
          var data = ev.data;
          if (typeof data === 'string') _scanFrameForMediaId(data);
          else if (data instanceof ArrayBuffer) _scanFrameForMediaId(data);
          else if (data instanceof Blob) data.arrayBuffer().then(_scanFrameForMediaId).catch(function () {});
        } catch (_) {}
      });
      var _origSend = ws.send.bind(ws);
      ws.send = function (sdata) {
        try {
          if (typeof sdata === 'string') _scanFrameForReqId(sdata);
          else if (sdata instanceof ArrayBuffer) _scanFrameForReqId(sdata);
        } catch (_) {}
        return _origSend(sdata);
      };
    }
    return ws;
  }
  _WSProxy.prototype = _OrigWS.prototype;
  _WSProxy.CONNECTING = 0; _WSProxy.OPEN = 1; _WSProxy.CLOSING = 2; _WSProxy.CLOSED = 3;
  window.WebSocket = _WSProxy;

  // ── LSD: leer del DOM / fetch /create ──────────────────────────────────
  var LSD_PATTERNS = [
    /"LSD"\s*,\s*\[\]\s*,\s*\{"token"\s*:\s*"([^"]+)"/,
    /\["LSD"\s*,\s*\[\]\s*,\s*\{"token"\s*:\s*"([^"]+)"/,
    /name="lsd"\s+value="([^"]+)"/,
    /"lsd"\s*:\s*\{"token"\s*:\s*"([^"]+)"/,
    /"lsd"\s*:\s*"([A-Za-z0-9_\-]{4,50})"/,
    /"lsd","([A-Za-z0-9_\-]{4,50})"/,
  ];
  function _parseLSD(text) {
    for (var i = 0; i < LSD_PATTERNS.length; i++) {
      var m = text.match(LSD_PATTERNS[i]);
      if (m && m[1]) return m[1];
    }
    return null;
  }
  function _readLSD() {
    var el = document.querySelector('input[name="lsd"]');
    if (el && el.value) { _S.lsd = el.value; return true; }
    var nd = document.getElementById('__NEXT_DATA__');
    if (nd) { try { var l = _parseLSD(nd.textContent || ''); if (l) { _S.lsd = l; return true; } } catch (_) {} }
    var ss = document.querySelectorAll('script');
    for (var i = 0; i < ss.length; i++) {
      var lsd = _parseLSD(ss[i].textContent || '');
      if (lsd) { _S.lsd = lsd; return true; }
    }
    return false;
  }
  function _fetchLSD() {
    var ctrl  = typeof AbortController !== 'undefined' ? new AbortController() : null;
    var timer = ctrl ? setTimeout(function () { ctrl.abort(); }, 8000) : null;
    _origFetch('https://www.meta.ai/create', { credentials: 'include', signal: ctrl ? ctrl.signal : undefined })
      .then(function (r) { if (timer) clearTimeout(timer); return r.text(); })
      .then(function (html) { _S.lsd = _parseLSD(html) || '__no_lsd__'; })
      .catch(function () { if (timer) clearTimeout(timer); _S.lsd = '__no_lsd__'; });
  }

  // Marca como "ya visto" todo media_id/URL de video que YA exista en el HTML
  // inicial (historial de /create) — sin esto, el primer "fbid://" o <video>
  // que aparezca (aunque sea viejo) se confunde con el resultado del job actual.
  function _seedKnownFromPage() {
    try {
      var html = document.documentElement.outerHTML || '';
      var m;
      FBID_RE.lastIndex = 0;
      while ((m = FBID_RE.exec(html)) !== null) _knownMediaIds.add(m[1]);
      var re = /https?:\/\/(?:video-[^\s"'\\]{5,}|[^\s"'\\]+\.mp4)[^\s"'\\]*/g;
      while ((m = re.exec(html)) !== null) { if (m[0].length > 30) _markKnownVideo(m[0]); }
    } catch (_) {}
  }

  // ── Init (document_start → DOMContentLoaded) ─────────────────────────
  function _initDOM() {
    document.querySelectorAll('video').forEach(function (v) {
      var s = v.src || v.currentSrc || v.getAttribute('src') || '';
      if (s) _markKnownVideo(s);
    });
    _seedKnownFromPage();
    _seedSeenMsgIds();
    if (!_S.lsd || _S.lsd === '__no_lsd__') {
      if (!_readLSD()) _fetchLSD();
    }
    _startGlobalVideoObserver();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', _initDOM);
  else _initDOM();

  // Meta a veces rechaza la generación (rate limit del lado de ellos) y en
  // vez de un video responde con un mensaje de chat normal ("Uy, algo falló
  // con eso. ¿Quieres que intentemos algo diferente..."). Sin detectar esto,
  // el job se queda esperando un video que nunca llega hasta agotar el
  // timeout completo (10 min) — confirmado por el usuario como rate limit
  // normal de Meta, que se soluciona reintentando. Se falla el job pendiente
  // de inmediato en vez de esperar, para que Flask lo reintente rápido.
  var FAILURE_TEXT_RE   = /algo fall[oó]/i;
  // Un mensaje de error VIEJO (de un job ya resuelto hace tiempo) puede
  // volver a mutar en el DOM por motivos ajenos (re-render, scroll, hover,
  // etc.) mucho después de su primera aparición — un debounce por tiempo
  // (4s) no protege contra eso. Si vuelve a disparar, _claimOldestPending()
  // mataría el job que esté pendiente EN ESE MOMENTO (uno legítimo, sin
  // relación con ese mensaje viejo), y su resultado real, cuando llegara,
  // se le asignaría por FIFO al job equivocado — el mismo bug de fondo de
  // toda la sesión, por una vía nueva. Cada nodo de texto solo puede
  // disparar esto UNA vez, sin importar cuántas veces se vuelva a tocar.
  var _handledFailureNodes = (typeof WeakSet !== 'undefined') ? new WeakSet() : null;
  function _checkFailureNode(node) {
    if (!node || typeof node.textContent !== 'string') return;
    if (!FAILURE_TEXT_RE.test(node.textContent)) return;
    if (_handledFailureNodes) {
      if (_handledFailureNodes.has(node)) return;
      _handledFailureNodes.add(node);
    }
    // Segunda capa de seguridad: si el job pendiente lleva mucho tiempo
    // esperando, es más probable que este texto no tenga relación con él
    // (debería haber llegado en segundos tras el envío real). Mejor dejarlo
    // seguir esperando (el watchdog normal lo resuelve por timeout) que
    // arriesgar matarlo por algo ajeno.
    // Con jobs que ya tienen su propio nodo DOM confirmado (_watchEntryNode),
    // este chequeo global debe IGNORARLOS — ese mensaje de error vive en SU
    // PROPIO contenedor o en uno ajeno, y _watchEntryNode ya revisa la falla
    // escopeada a su propio nodo. Esta vía global solo debe poder fallar el
    // job más antiguo de la fila SI ese todavía no tiene nodo propio (la
    // ventana corta entre el envío y que aparezca su mensaje en el DOM) —
    // igual semántica que _claimOldestPending, nunca "saltar" al siguiente.
    if (_pending.length === 0 || _pending[0].domNode) return;
    if (Date.now() - _pending[0].submittedAt > 60000) return;
    var entry = _claimOldestPending();
    if (entry) {
      console.warn('[VF] ⚠️ Meta respondió con texto de error ("algo falló") en vez de video — fallando el job de inmediato:', entry.requestId.slice(0, 8));
      _deliverResult(entry, null);
    }
  }
  function _startGlobalVideoObserver() {
    if (typeof MutationObserver === 'undefined') return;
    var obs = new MutationObserver(function (mutations) {
      mutations.forEach(function (mut) {
        // El texto de respuesta de Meta se escribe con efecto de "streaming"
        // — actualiza el contenido de un nodo de texto YA EXISTENTE en vez de
        // agregar nodos nuevos. childList (addedNodes) nunca veía eso; hace
        // falta también escuchar characterData (mut.target es el nodo de
        // texto afectado, no tiene addedNodes).
        if (mut.type === 'characterData') { _checkFailureNode(mut.target); return; }
        mut.addedNodes.forEach(function (node) {
          if (!node || node.nodeType !== 1) return;
          _checkVideoNode(node);
          _checkFailureNode(node);
          var vids = node.querySelectorAll ? node.querySelectorAll('video') : [];
          for (var i = 0; i < vids.length; i++) _checkVideoNode(vids[i]);
        });
      });
    });
    obs.observe(document.body || document.documentElement, { childList: true, subtree: true, characterData: true });
  }
  function _checkVideoNode(node) {
    if (!node || node.tagName !== 'VIDEO') return;
    var src = node.src || node.currentSrc || node.getAttribute('src') || '';
    if (!src) {
      var sources = node.querySelectorAll ? node.querySelectorAll('source') : [];
      for (var i = 0; i < sources.length; i++) { src = sources[i].src || sources[i].getAttribute('src') || ''; if (src) break; }
    }
    if (!src || !src.startsWith('http') || _isKnownVideo(src)) return;
    _recentVideoUrls.push({ url: src, ts: Date.now() });
    if (_recentVideoUrls.length > 20) _recentVideoUrls.shift();
  }

  // ── GQL helpers ───────────────────────────────────────────────────────
  function _gqlH() {
    var h = { 'content-type': 'application/json', 'accept': '*/*', 'origin': 'https://www.meta.ai', 'referer': 'https://www.meta.ai/create' };
    if (_S.lsd && _S.lsd !== '__no_lsd__') h['x-fb-lsd']    = _S.lsd;
    if (_S.asbd_id)                        h['x-asbd-id']   = _S.asbd_id;
    if (_S.csrftoken)                      h['x-csrftoken'] = _S.csrftoken;
    return h;
  }
  function _gql(docId, vars) {
    return _origFetch(GQL, { method: 'POST', credentials: 'include', headers: _gqlH(), body: JSON.stringify({ doc_id: docId, variables: vars }) });
  }

  function _uuid() {
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function (c) {
      var r = Math.random() * 16 | 0;
      return (c === 'x' ? r : (r & 0x3 | 0x8)).toString(16);
    });
  }

  // ── Extraer URL de video de una respuesta GQL/SSE ──────────────────────
  var _VIDEO_FIELDS = ['"generatedVideo"','"generatedMedia"','"generated_video"','"generated_media"','"outputVideo"','"output_video"','"videoResult"','"video_result"','"batchedGenerationStatusStream"'];
  function _extractURL(text) {
    for (var fi = 0; fi < _VIDEO_FIELDS.length; fi++) {
      var fn = _VIDEO_FIELDS[fi], pos = 0;
      while (pos < text.length) {
        var gi = text.indexOf(fn, pos); if (gi === -1) break;
        pos = gi + fn.length;
        var ci = pos;
        while (ci < text.length && ' \t\n\r'.indexOf(text[ci]) !== -1) ci++;
        if (text[ci] !== ':') continue; ci++;
        while (ci < text.length && ' \t\n\r'.indexOf(text[ci]) !== -1) ci++;
        if (text[ci] !== '{') { pos = ci; continue; }
        var depth = 0, end = -1;
        for (var j = ci; j < Math.min(ci + 16384, text.length); j++) {
          if (text[j] === '{') depth++; else if (text[j] === '}') { depth--; if (depth === 0) { end = j; break; } }
        }
        if (end === -1) continue;
        var chunk = text.slice(ci + 1, end);
        var m = chunk.match(/"url"\s*:\s*"(https?:[^"]{10,})"/);
        if (m) return m[1];
      }
    }
    var re = /https?:\/\/(?:video-[^\s"]{5,}|[^\s"]+\.mp4)[^\s"]*/g, m2;
    while ((m2 = re.exec(text)) !== null) { var u = m2[0]; if (u.length > 30) return u; }
    return null;
  }
  var _URL_KEYS = ['url','videoUrl','video_url','downloadUrl','download_url','src'];
  // "fbcdn.net" por sí solo NO basta — es el dominio genérico de Facebook que
  // sirve tanto imágenes (scontent-*.fbcdn.net, ruta /v/t0/) como videos
  // (video-*.fbcdn.net, ruta /v/t2/). Un chequeo amplio capturaba la imagen
  // fuente (sourceMedia.url) como si fuera el video final mientras éste
  // todavía se generaba.
  function _looksLikeVideoUrl(v) {
    return v.indexOf('.mp4') !== -1 || v.indexOf('/v/t2/') !== -1 || /:\/\/video-/.test(v);
  }
  function _findVideoUrl(obj) {
    if (!obj || typeof obj !== 'object') return null;
    if (Array.isArray(obj)) { for (var i = 0; i < obj.length; i++) { var f = _findVideoUrl(obj[i]); if (f) return f; } return null; }
    for (var k in obj) {
      var v = obj[k];
      if (_URL_KEYS.indexOf(k) !== -1 && typeof v === 'string' && v.length > 20 && v.startsWith('http')) {
        if (_looksLikeVideoUrl(v)) return v;
      }
      if (typeof v === 'object') { var fv = _findVideoUrl(v); if (fv) return fv; }
    }
    return null;
  }

  // ── Leer SSE stream de DOC_GEN ──────────────────────────────────────────
  function _readSSE(resp, deadline, mediaId) {
    return new Promise(function (resolve, reject) {
      if (!resp.body || typeof resp.body.getReader !== 'function') { reject(new Error('Sin ReadableStream')); return; }
      var reader = resp.body.getReader(), dec = new TextDecoder(), buf = '';
      var completeSeen = false, completeTimer = null;

      function _cleanUp() { if (completeTimer) { clearTimeout(completeTimer); completeTimer = null; } }

      // DOC_GEN se pide con mediaIds:[mediaId] propio, pero el stream puede
      // traer eventos de OTRO media_id igual — confirmado con DEBUG-SSE: tras
      // una reconexión (p.ej. una caída momentánea de red), Meta REPITE
      // eventos "COMPLETE" viejos ya entregados (mismo blob, distinto host
      // CDN). Antes, _tryExtract aceptaba cualquier URL nueva que apareciera
      // en ESTE stream sin verificar de qué mediaId era — si el stream de un
      // job incluía (por ese reenvío) el video de OTRO job que terminó
      // primero, se lo podía "robar". Esa era la causa raíz del corrimiento
      // en cascada (8→9→10→11…): ahora solo se acepta una URL si el evento
      // trae explícitamente el mediaId que ESTE poll está esperando.
      function _tryExtract(rawBuf) {
        var lines = rawBuf.split('\n');
        for (var li = 0; li < lines.length; li++) {
          var ln = lines[li], di = ln.indexOf('data:');
          if (di === -1) continue;
          var jsonStr = ln.slice(di + 5).trim();
          if (!jsonStr || jsonStr === '[DONE]') continue;
          try {
            var ev = JSON.parse(jsonStr);
            var bss = ev && ev.data && ev.data.batchedGenerationStatusStream;
            if (!bss || !bss.mediaId || String(bss.mediaId) !== String(mediaId)) continue;
            var eurl = _findVideoUrl(bss);
            if (eurl && !_isKnownVideo(eurl)) return eurl;
          } catch (_) {}
        }
        return null;
      }

      function read() {
        if (Date.now() > deadline) { _cleanUp(); reader.cancel(); reject(new Error('Timeout SSE deadline')); return; }
        reader.read().then(function (res) {
          if (res.value) buf += dec.decode(res.value, { stream: !res.done });
          var url = _tryExtract(buf);
          if (url) { _cleanUp(); reader.cancel(); resolve({ url: url }); return; }
          if (buf.indexOf('"status":"ERROR"') !== -1 || buf.indexOf('"status":"FAILED"') !== -1) {
            _cleanUp(); reader.cancel(); reject(new Error('status ERROR/FAILED en SSE')); return;
          }
          if (!completeSeen && buf.indexOf('event: complete') !== -1) {
            completeSeen = true;
            completeTimer = setTimeout(function () {
              completeTimer = null;
              var u2 = _tryExtract(buf);
              if (u2) { reader.cancel(); resolve({ url: u2 }); return; }
              reader.cancel();
              resolve({ eventComplete: true });
            }, 5000);
          }
          if (res.done) {
            _cleanUp();
            if (completeSeen) { resolve({ eventComplete: true }); return; }
            var hasComplete = buf.indexOf('"COMPLETED"') !== -1;
            var hadProgress = buf.indexOf('"IN_PROGRESS"') !== -1;
            if (hasComplete || hadProgress) resolve({ pollConv: true });
            else reject(new Error('SSE sin datos útiles'));
            return;
          }
          read();
        }).catch(function (e) { _cleanUp(); reject(e); });
      }
      read();
    });
  }

  // ── Poll fetchConversation (fallback cuando el SSE cierra sin URL) ─────
  // DOC_FETCH_CONV devuelve la conversación COMPLETA, no solo el media_id que
  // nos interesa. Como "Nuevo chat" puede fallar y todos los jobs terminan en
  // la MISMA conversación, _extractURL/_findVideoUrl pueden encontrar el video
  // de OTRO job ya entregado en vez del propio. Si la URL encontrada ya está
  // en _knownVideos (ya entregada a otro requestId), se descarta y se sigue
  // sondeando — preferible un timeout a entregar un video duplicado/ajeno.
  function _pollConv(convId, deadline, immediateFirst) {
    return new Promise(function (resolve) {
      var polls = 0, MAX = 15;
      function tick() {
        if (!convId || Date.now() > deadline || polls >= MAX) { resolve(null); return; }
        polls++;
        _gql(DOC_FETCH_CONV, { id: convId })
          .then(function (r) { return r.text(); })
          .then(function (txt) {
            var plain = txt.replace(/\\\//g, '/');
            var url = _extractURL(plain);
            if (!url) { try { var jm = txt.match(/\{[\s\S]+\}/); if (jm) url = _findVideoUrl(JSON.parse(jm[0])); } catch (_) {} }
            if (url && _isKnownVideo(url)) {
              console.warn('[VF] ⚠️ _pollConv encontró un video ya entregado a otro job — ignorando y sigo sondeando:', url.slice(0, 70));
              url = null;
            }
            if (url) { resolve(url); return; }
            setTimeout(tick, 5000);
          })
          .catch(function () { setTimeout(tick, 5000); });
      }
      setTimeout(tick, immediateFirst ? 500 : 3000);
    });
  }

  // ── Polling directo por GraphQL una vez que sabemos el media_id real ───
  function _pollMediaResult(mediaId, convId, deadline) {
    var vars = { mediaIds: [mediaId], conversationId: convId || _uuid() };
    var sseRound = 0, MAX_ROUNDS = 40;
    function runSSE() {
      if (Date.now() > deadline - 15000 || sseRound >= MAX_ROUNDS) return _pollConv(convId, deadline, true);
      sseRound++;
      return _gql(DOC_GEN, vars).then(function (resp) {
        if (!resp.ok) return resp.text().then(function (t) { throw new Error('Gen HTTP ' + resp.status + ': ' + t.slice(0, 200)); });
        return _readSSE(resp, deadline, mediaId).then(function (result) {
          if (result.url) return result.url;
          if (result.eventComplete) {
            return _pollConv(convId, deadline, true).then(function (url) {
              if (url) return url;
              return new Promise(function (res2, rej2) { setTimeout(function () { runSSE().then(res2).catch(rej2); }, 4000); });
            });
          }
          if (result.pollConv) {
            return new Promise(function (resolve, reject) { setTimeout(function () { runSSE().then(resolve).catch(reject); }, 4000); });
          }
          throw new Error('SSE: estado inesperado');
        });
      });
    }
    return runSSE();
  }

  // ── DOM: helpers de envío (imagen + prompt) ────────────────────────────
  function _domApplyFile(input, file) {
    try {
      var dt = new DataTransfer(); dt.items.add(file);
      input.files = dt.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
      input.dispatchEvent(new Event('input',  { bubbles: true }));
    } catch (e) { input.dispatchEvent(new Event('change', { bubbles: true })); }
  }
  // La miniatura adjunta en el composer es <img alt="<filename>" src="blob:...">
  // (confirmado por inspección real del DOM) — el atributo alt coincide
  // exactamente con el filename que le pasamos. Sirve para verificar que
  // Meta YA proceso/muestra NUESTRA imagen antes de escribir+enviar, en vez
  // de un timer fijo que puede no alcanzar si la miniatura anterior tarda en
  // limpiarse. Sin esto, un job puede enviarse con la imagen del job anterior
  // todavía adjunta — el video sale único y bien correlacionado por requestId,
  // pero con el contenido de OTRA imagen (no se detecta como duplicado).
  function _findAttachedImg(filename) {
    var imgs = document.querySelectorAll('img[alt]');
    for (var i = 0; i < imgs.length; i++) { if (imgs[i].alt === filename) return imgs[i]; }
    return null;
  }
  // Cuenta adjuntos PENDIENTES de enviar — NO usar <img blob:> para esto: el
  // historial de la conversación (mensajes YA enviados) también deja
  // miniaturas con src blob: visibles indefinidamente en el scrollback, así
  // que ese conteo nunca volvía a dar 1 después del primer job (regresión
  // v5.0: abortaba TODOS los envíos siguientes, lentísimo y forzando
  // reintentos en cascada). El botón "Remove attachment" sí es un conteo
  // seguro: solo existe para adjuntos del composer aún no enviados.
  function _countPendingAttachments() {
    return document.querySelectorAll('button[aria-label="Remove attachment"]').length;
  }
  function _waitImageAttached(filename, cb) {
    var attempts = 0, MAX_ATTEMPTS = 35; // ~7s a 200ms — antes 4s, muy corto si la pestaña venía desatendida (foco rotativo entre varias)
    function tick() {
      attempts++;
      var img = _findAttachedImg(filename);
      var found = img && img.src && img.src.indexOf('blob:') === 0;
      // No basta con que aparezca MI miniatura — si todavía queda OTRO
      // adjunto pendiente (resto del job anterior que _clearExistingAttachments
      // no alcanzó a quitar a tiempo), Meta puede generar igual con el
      // adjunto viejo aunque el mío también esté presente y verificado.
      if (found && _countPendingAttachments() === 1) { cb(true); return; }
      if (attempts < MAX_ATTEMPTS) { setTimeout(tick, 200); return; }
      // Antes esto seguía igual (cb(true)) y el job se mandaba SIN imagen
      // confirmada (o con restos de otra) — peor que un timeout normal: el
      // timeout se reintenta limpio, esto se descarga como si fuera válido.
      console.warn('[VF] ❌ No se confirmó "' + filename + '" como único adjunto pendiente tras ' + Math.round(attempts * 0.2) + 's (encontrada=' + found + ', pendientes=' + _countPendingAttachments() + ') — abortando este envío');
      cb(false);
    }
    tick();
  }
  // El composer de Meta acumula adjuntos en su propio estado (carrusel de
  // "attachment-tile"), no los reemplaza solo por poner un archivo nuevo en
  // el <input>. Como "Nuevo chat" nunca se encuentra, el adjunto del job
  // anterior podía quedar pegado de fondo aunque la miniatura del job nuevo
  // también apareciera correctamente — Meta podía generar usando la imagen
  // vieja. Botón real confirmado por inspección: aria-label="Remove attachment".
  // Cuando hay 2+ adjuntos acumulados, clickearlos todos de una sola pasada
  // (mismo tick síncrono) no es confiable: React no siempre llega a procesar
  // el primer clic antes de que dispare el segundo, así que algunos quedan
  // sin quitar (consistente con que casi siempre sea la imagen MÁS VIEJA —
  // la primera adjuntada en la conversación — la que se queda pegada). Ahora
  // se quita de una en una, re-consultando el DOM ya actualizado entre cada
  // clic, hasta que no quede ninguna.
  function _clearExistingAttachments(cb) {
    // MAX_ROUNDS/delay subidos (6→10 rondas, 250→300ms): en una pestaña lenta
    // o desatendida (rotación de foco entre varias), cada clic puede tardar
    // más en que React lo procese antes de que el siguiente tick dispare el
    // próximo — quedándose rondas "desperdiciadas". _waitImageAttached ahora
    // además verifica que no quede ningún resto, pero es mejor que la
    // limpieza tenga más margen para no depender solo de esa red de seguridad.
    var rounds = 0, MAX_ROUNDS = 10;
    function step() {
      rounds++;
      var btn = document.querySelector('button[aria-label="Remove attachment"]');
      if (!btn || rounds > MAX_ROUNDS) { cb(); return; }
      try { btn.click(); } catch (e) {}
      setTimeout(step, 300);
    }
    step();
  }
  function _domSetImage(b64, filename, cb) {
    var fname = filename || 'image.jpg';
    var parts = b64.split(','), mime = 'image/jpeg', raw = b64;
    if (parts.length > 1) { var mm = parts[0].match(/:([^;]+)/); if (mm) mime = mm[1]; raw = parts[1]; }
    var file;
    try {
      var bytes = atob(raw), arr = new Uint8Array(bytes.length);
      for (var i = 0; i < bytes.length; i++) arr[i] = bytes.charCodeAt(i);
      file = new File([arr], fname, { type: mime });
    } catch (e) { cb(false); return; }

    _clearExistingAttachments(function () {
      var input = document.querySelector("input[type='file']");
      if (input) { _domApplyFile(input, file); _waitImageAttached(fname, cb); return; }

      var sels = ["[aria-label*='ttach']","[aria-label*='mage']","[aria-label*='Photo']","[data-testid*='attach']","button[type='button'] svg"];
      var btn = null;
      for (var j = 0; j < sels.length; j++) { btn = document.querySelector(sels[j]); if (btn) break; }
      if (btn) {
        var el = btn; while (el && el.tagName !== 'BUTTON') el = el.parentElement;
        if (el) el.click();
        setTimeout(function () {
          input = document.querySelector("input[type='file']");
          if (input) { _domApplyFile(input, file); _waitImageAttached(fname, cb); } else { cb(false); }
        }, 400);
      } else { cb(false); }
    });
  }
  // Selectores ampliados (home y /create usan markup distinto) + reintentos
  // durante varios segundos — la falla anterior en home era casi seguro timing
  // (la app todavía hidratando), no que el selector estuviera mal.
  var _PROMPT_FIELD_SELS = [
    "[data-testid='composer-input']", // confirmado via inspección real del DOM — más estable
    "div[contenteditable='true']", "div[role='textbox']",
    "textarea[placeholder]", "textarea",
    "input[type='text'][placeholder]", "input[type='search'][placeholder]",
    "input[placeholder]:not([type='file'])",
  ];
  function _findPromptField() {
    for (var i = 0; i < _PROMPT_FIELD_SELS.length; i++) {
      var c = document.querySelector(_PROMPT_FIELD_SELS[i]);
      if (c && c.getBoundingClientRect().width > 0) return c;
    }
    return null;
  }
  function _domSetPromptAndSend(prompt, cb) {
    var attempts = 0, MAX_ATTEMPTS = 16; // ~8s a 500ms
    function tryFind() {
      attempts++;
      var el = _findPromptField();
      if (el) { _typeAndSend(el); return; }
      if (attempts < MAX_ATTEMPTS) { setTimeout(tryFind, 500); return; }
      console.warn('[VF] ⚠️ No campo de texto para enviar tras ' + attempts + ' intentos');
      if (cb) cb();
    }
    function _typeAndSend(el) {
      el.focus();
      if (el.contentEditable === 'true') {
        document.execCommand('selectAll', false, null);
        document.execCommand('insertText', false, prompt);
      } else if (el.tagName === 'TEXTAREA') {
        var ns = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value');
        if (ns && ns.set) ns.set.call(el, prompt); else el.value = prompt;
      } else {
        var ni = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
        if (ni && ni.set) ni.set.call(el, prompt); else el.value = prompt;
      }
      el.dispatchEvent(new Event('input',  { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));

      setTimeout(function () {
        var sent = false;
        var bs = ["[data-testid='composer-send-button']","button[aria-label*='end']","button[type='submit']","div[role='button'][aria-label*='end']","[data-testid*='send']","button[aria-label*='enerate']","button[aria-label*='nimate']"];
        for (var i = 0; i < bs.length; i++) {
          var b = document.querySelector(bs[i]);
          if (b && !b.disabled && b.getAttribute('aria-disabled') !== 'true') { b.click(); sent = true; break; }
        }
        if (!sent) {
          el.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true, keyCode: 13, which: 13 }));
          el.dispatchEvent(new KeyboardEvent('keyup',   { key: 'Enter', bubbles: true, keyCode: 13, which: 13 }));
        }
        console.log('[VF] 🖱️ Enviado:', prompt.slice(0, 60) + (prompt.length > 60 ? '…' : ''));
        if (cb) cb();
      }, 300);
    }
    tryFind();
  }

  // ── Correlación por POSICIÓN EN EL DOM (v6.0) ──────────────────────────
  // Hallazgo clave (inspección real del DOM, ver historial de chat): cada
  // mensaje de respuesta queda en un contenedor propio
  // <div data-message-item="true" data-message-id="...assistant">, y una vez
  // termina de generar aparece adentro <div data-testid="generated-video"
  // data-video-url="https://...mp4?...">. El ORDEN en que estos contenedores
  // se agregan a la conversación SIEMPRE respeta el orden en que se enviaron
  // los mensajes — sin importar cuál termine de generar PRIMERO. Esto permite
  // saber con certeza absoluta a qué job pertenece cada video por su propio
  // contenedor, sin depender del orden de llegada de eventos del WebSocket
  // (que SÍ puede desincronizarse del orden de envío si Meta genera en
  // paralelo y uno más simple termina antes que otro enviado primero — la
  // causa de fondo, nunca antes resuelta, de los corrimientos al correr varios
  // jobs a la vez por pestaña). Con esto, MAX_INFLIGHT > 1 vuelve a ser seguro.
  var ASSISTANT_MSG_SEL = '[data-message-item="true"][data-message-id*="_assistant"]';
  var GEN_VIDEO_SEL      = '[data-testid="generated-video"]';

  function _extractVideoUrlFromNode(node) {
    var gv = node.querySelector ? node.querySelector(GEN_VIDEO_SEL) : null;
    if (!gv) return null;
    var u = gv.getAttribute('data-video-url');
    if (u) return u;
    var vid = gv.querySelector('video');
    if (vid) { var s = vid.src || vid.currentSrc || vid.getAttribute('src'); if (s) return s; }
    return null;
  }

  // Asignación de "nodo nuevo" por COLA GLOBAL ÚNICA, en orden de envío —
  // NO por snapshot individual de cada job. Bug real confirmado dos veces en
  // uso real con MAX_INFLIGHT=2 (incluida una reproducción después de revertir
  // a esta misma versión sin este fix: "005 descargado como 006"): si dos
  // jobs esperan su mensaje nuevo AL MISMO TIEMPO, cada uno comparaba contra
  // SU PROPIA foto de "antes de enviar" — desde la foto del job B (tomada
  // después), el mensaje que en realidad es del job A también se ve "nuevo",
  // y B podía robárselo si su tick corría primero. Con una sola cola global
  // (orden de envío) y un solo poller que reparte cada mensaje nuevo, EN
  // ORDEN DE APARICIÓN EN EL DOM, al que lleve más tiempo esperando, no hay
  // ambigüedad posible entre dos esperas simultáneas — se apoya en que la
  // creación de la burbuja del mensaje SÍ respeta el orden de envío (a
  // diferencia de cuándo TERMINA de generar, que no).
  var _allSeenMsgIds   = new Set();
  var _awaitingDomNode = []; // [{cb, deadline}] en orden de espera (FIFO)
  var WAIT_DOMNODE_TIMEOUT_MS = 20000;

  function _seedSeenMsgIds() {
    document.querySelectorAll(ASSISTANT_MSG_SEL).forEach(function (n) {
      var id = n.getAttribute('data-message-id');
      if (id) _allSeenMsgIds.add(id);
    });
  }
  // Confirmado por inspección en vivo: Meta solo mantiene 2 mensajes de
  // asistente MONTADOS en el DOM a la vez (virtualización agresiva de la
  // conversación) — root cause real de que el nodo propio dejara de
  // encontrarse después del job #2 en lotes largos. Un envío automatizado
  // (sin scroll real de usuario) no dispara el auto-scroll que mantendría
  // montado el mensaje más nuevo, así que puede quedar fuera de esa ventana
  // de 2 antes de que lleguemos a verlo. Forzar el scroll al final antes de
  // cada poll asegura que el mensaje más reciente esté montado.
  function _scrollConversationToBottom() {
    try {
      var nodes = document.querySelectorAll(ASSISTANT_MSG_SEL);
      var last = nodes.length ? nodes[nodes.length - 1] : null;
      if (last && last.scrollIntoView) last.scrollIntoView({ block: 'end' });
      window.scrollTo(0, document.body.scrollHeight);
    } catch (_) {}
  }
  function _pollNewAssistantMessages() {
    while (_awaitingDomNode.length > 0 && Date.now() > _awaitingDomNode[0].deadline) {
      var timedOut = _awaitingDomNode.shift();
      console.warn('[VF] ⚠️ No apareció mensaje nuevo de asistente tras enviar (por data-message-id) — sigo con WS/FIFO de respaldo');
      timedOut.cb(null);
    }
    if (_awaitingDomNode.length === 0) return;
    _scrollConversationToBottom();
    var nodes = document.querySelectorAll(ASSISTANT_MSG_SEL);
    for (var i = 0; i < nodes.length; i++) {
      var id = nodes[i].getAttribute('data-message-id');
      if (!id || _allSeenMsgIds.has(id)) continue;
      _allSeenMsgIds.add(id);
      if (_awaitingDomNode.length === 0) continue; // ya no hay nadie esperando, pero igual se marca visto
      var waiter = _awaitingDomNode.shift();
      waiter.cb(nodes[i]);
    }
  }
  setInterval(_pollNewAssistantMessages, 500);

  // Tras enviar, se anota en la cola — el poller global le asignará el
  // próximo mensaje nuevo que aparezca, en orden de espera. Si no le toca
  // ninguno a tiempo, cb(null) — el job sigue cubierto por el WS/FIFO de
  // respaldo, igual que antes de v6.0.
  function _waitForNewAssistantMessage(cb) {
    _awaitingDomNode.push({ cb: cb, deadline: Date.now() + WAIT_DOMNODE_TIMEOUT_MS });
    _scrollConversationToBottom(); // de inmediato, no esperar al próximo tick de 500ms
  }

  // Vigila el contenedor PROPIO de un job hasta que aparezca su video o su
  // error — escopeado a ESE nodo, nunca puede confundirse con otro job.
  function _watchEntryNode(entry, node) {
    var POLL_MS = 600, MAX_TICKS = 950; // ~9.5min — el watchdog general (10min) purga lo que quede
    var ticks = 0;
    // Meta virtualiza la conversación reusando los mismos <div> físicos para
    // mensajes distintos a medida que la lista se desplaza (confirmado: solo
    // 2 mensajes de asistente montados a la vez). Si el nodo que guardamos es
    // RECICLADO para otro mensaje mientras esperamos, su data-message-id
    // cambia — sin este chequeo, _watchEntryNode seguiría leyendo el video de
    // OTRO job creyendo que es el propio. Se guarda el id esperado al
    // capturar el nodo y se verifica en cada tick.
    var expectedId = node.getAttribute('data-message-id');
    function tick() {
      if (entry.claimed) return; // ya resuelto por otra vía (p.ej. purga por deadline)
      ticks++;
      if (expectedId && node.getAttribute('data-message-id') !== expectedId) {
        console.warn('[VF] ⚠️ nodo reciclado por la lista virtualizada de Meta (ya no es', entry.requestId.slice(0, 8) + ') — vuelvo a esperar este job por WS/FIFO');
        entry.domNode = null;
        _waitForNewAssistantMessage(function (newNode) {
          if (newNode && !entry.claimed) {
            entry.domNode = newNode;
            console.log('[VF] 📎 nodo DOM propio re-asociado:', entry.requestId.slice(0, 8));
            _watchEntryNode(entry, newNode);
          }
        });
        return;
      }
      var url = _extractVideoUrlFromNode(node);
      if (url && !_isKnownVideo(url)) {
        _removeFromPending(entry);
        console.log('[VF] 🎯 video via DOM propio (sin WS/FIFO):', entry.requestId.slice(0, 8), url.slice(0, 70));
        var delivered = _deliverResult(entry, url);
        if (delivered) return;
        // _deliverResult lo rechazó (duplicado) y lo devolvió a _pending —
        // sigue vigilando este mismo nodo por si era una falsa alarma.
      } else if (FAILURE_TEXT_RE.test(node.textContent || '')) {
        _removeFromPending(entry);
        console.warn('[VF] ⚠️ "algo falló" dentro del contenedor propio del job — fallando de inmediato:', entry.requestId.slice(0, 8));
        _deliverResult(entry, null);
        return;
      }
      if (ticks < MAX_TICKS) setTimeout(tick, POLL_MS);
    }
    tick();
  }

  // ── Job runner v3: submit sucesivo + mapeo FIFO de resultados ───────────
  // No se espera a que termine de generar el job N para enviar el N+1 — solo
  // se espera SUBMIT_DELAY_MS para que la UI registre el envío. Los resultados
  // (vía WS o fallback del DOM) se asignan al job pendiente MÁS ANTIGUO en
  // cuanto aparece algo nuevo — así nunca se mezclan ni se repiten, igual
  // principio que el meta_main.js original pero con mejor detección de señal.
  function _enqueueDOMJob(data) {
    if (_seenRequestIds.has(data.requestId)) {
      console.warn('[VF] ⚠️ requestId duplicado ignorado (Flask lo reenvió, ya procesado/en curso):', data.requestId.slice(0, 8));
      return;
    }
    _seenRequestIds.add(data.requestId);
    _submitQueue.push(data);
    _processSubmitQueue();
  }

  // Click en "Nuevo chat" antes de cada job — sin esto, varios jobs seguidos
  // caen en la MISMA conversación y el composer de meta.ai reusa la imagen
  // adjuntada anteriormente (su "selector de imágenes recientes") en vez de
  // la nueva, generando videos con la imagen vieja repetida. Como ya estamos
  // en /, este clic resetea el composer sin recarga completa de página.
  // Confirmado en decenas de corridas reales a lo largo de esta sesión: este
  // botón NUNCA aparece (0% de éxito) — reintentar 10×500ms solo desperdicia
  // ~5s por job sin cambiar el resultado. Un solo intento, sin retry.
  function _domClickNewChat(cb) {
    var candidates = document.querySelectorAll('button, a, div[role="button"]');
    var btn = null;
    for (var i = 0; i < candidates.length; i++) {
      var t = (candidates[i].textContent || '').trim().toLowerCase();
      if (t === 'nuevo chat' || t === 'new chat') { btn = candidates[i]; break; }
    }
    if (btn) { btn.click(); setTimeout(cb, 600); return; }
    cb();
  }

  // El botón [data-testid='composer-send-button'] queda `disabled` TANTO
  // cuando el composer está vacío (sin texto aún) COMO cuando Meta está
  // procesando el envío anterior (~5s, "ruedita") — son el MISMO atributo
  // para dos causas distintas. Como esta espera se llama ANTES de escribir
  // el prompt del siguiente job, el campo siempre está vacío en ese momento
  // → el botón SIEMPRE aparece disabled → la espera por "disabled" del botón
  // agota su timeout sin servir para nada (confirmado: timeout en el 100% de
  // los jobs en pruebas reales). La señal correcta es el campo de texto
  // [data-testid='composer-input']: Meta lo vacía solo cuando YA aceptó/
  // procesó el mensaje anterior — si sigue con texto, el job anterior sigue
  // en curso y adjuntar uno nuevo ahora lo mezclaría con ese.
  function _isComposerReady() {
    var el = _findPromptField();
    if (!el) return true; // no se encontró el campo — no se puede verificar, no bloquear
    var txt = el.contentEditable === 'true' ? (el.textContent || '') : (el.value || '');
    return txt.trim() === '';
  }
  function _waitComposerReady(cb) {
    var attempts = 0, MAX_ATTEMPTS = 30; // ~9s a 300ms
    function tick() {
      attempts++;
      if (_isComposerReady()) { cb(); return; }
      if (attempts < MAX_ATTEMPTS) { setTimeout(tick, 300); return; }
      console.warn('[VF] ⚠️ Composer sigue con texto tras ' + Math.round(attempts * 0.3) + 's — continúo de todos modos (riesgo de mezclar jobs)');
      cb();
    }
    tick();
  }

  function _processSubmitQueue() {
    if (_submitting || _submitQueue.length === 0) return;
    _submitting = true;
    var data = _submitQueue.shift();
    console.log('[VF] 🤖 Submit', data.requestId.slice(0, 8), '|', (data.prompt || '').slice(0, 50), '| en cola:', _submitQueue.length);

    var entry = { requestId: data.requestId, deadline: Date.now() + JOB_TIMEOUT_MS, claimed: false, submittedAt: Date.now() };
    _pending.push(entry);

    // Con varias pestañas, la rotación de foco de background.js reparte
    // tiempo fijo entre todas — si adjuntar+enviar necesita más de lo que
    // toca en ese turno, queda a medias (ni falla limpio ni termina) hasta
    // que vuelve a tener foco, varios segundos después. Confirmado: pasaba
    // en todas las pestañas a la vez, "revivían" solo al hacerles clic
    // manualmente. Se pide foco sostenido AHORA (antes de tocar el DOM) y se
    // libera en cuanto el envío termina o se aborta — el polling del
    // resultado que sigue no necesita primer plano.
    window.postMessage({ type: 'META_NEED_FOCUS' }, '*');
    function _releaseFocus() { window.postMessage({ type: 'META_FOCUS_DONE' }, '*'); }

    function afterSend() {
      console.log('[VF] 📤 Enviado', data.requestId.slice(0, 8), '| pendientes de resultado:', _pending.length);
      _releaseFocus();
      _submitting = false;
      if (_submitQueue.length > 0) setTimeout(_processSubmitQueue, SUBMIT_DELAY_MS);
    }
    function _afterImage(ok) {
      console.log('[VF] 🖼️ Imagen:', ok ? '✅' : '❌ no confirmada');
      if (!ok) {
        // Antes esto mandaba el prompt igual sin imagen confirmada — un video
        // generado sin imagen fuente es peor que un timeout: el timeout se
        // reintenta limpio, ese video se descarga como si fuera válido. Se
        // aborta el envío (no se manda nada) y se libera el job para que
        // Flask lo reintente, sin bloquear la cola de esta pestaña.
        console.warn('[VF] ❌ Abortando envío de', data.requestId.slice(0, 8), '— imagen no confirmada a tiempo');
        _removeFromPending(entry);
        _deliverResult(entry, null);
        _releaseFocus();
        _submitting = false;
        if (_submitQueue.length > 0) setTimeout(_processSubmitQueue, SUBMIT_DELAY_MS);
        return;
      }
      setTimeout(function () {
        // Armar la correlación justo antes del clic real — el ws.send() de
        // meta.ai debería ocurrir milisegundos después de este clic, pero con
        // 3 generaciones simultáneas compitiendo por el hilo principal de la
        // pestaña, el envío real del frame WS puede demorarse más de lo
        // esperado. Una ventana de 2s era demasiado corta: si se vencía antes
        // de que llegara el eco con el req-id, la correlación directa (la
        // confiable) se perdía en silencio y el resultado caía al respaldo
        // FIFO — que es donde aparece el corrimiento en cascada (8→9→10→11…)
        // cuando un media_id de más se le asigna al job pendiente equivocado.
        // Como _processSubmitQueue serializa los envíos (solo un job "armado"
        // a la vez por pestaña), alargar esta ventana no arriesga mezclar
        // jobs — solo reduce la chance de perder la correlación directa.
        _pendingSendMatch = entry;
        setTimeout(function () { if (_pendingSendMatch === entry) _pendingSendMatch = null; }, 10000);
        _domSetPromptAndSend(data.prompt || 'animate', function () {
          afterSend();
          _waitForNewAssistantMessage(function (node) {
            if (node && !entry.claimed) {
              entry.domNode = node;
              console.log('[VF] 📎 nodo DOM propio asociado:', entry.requestId.slice(0, 8));
              _watchEntryNode(entry, node);
            }
          });
        });
      }, 700);
    }
    _domClickNewChat(function () {
      document.querySelectorAll('video').forEach(function (v) {
        var s = v.src || v.currentSrc || v.getAttribute('src') || '';
        if (s) _markKnownVideo(s);
      });
      _seedKnownFromPage(); // por si cargó más historial después del _initDOM inicial
      _waitComposerReady(function () {
        if (data.image_b64) _domSetImage(data.image_b64, data.filename || 'image.jpg', _afterImage);
        else _afterImage(true);
      });
    });
  }

  // Reclama el job pendiente más antiguo sin resolver (FIFO) — único punto de
  // asignación, usado por el sniffer del WS, el fallback del DOM y el watchdog.
  // El watchdog (más abajo) solo corre cada 5s — sin este chequeo de deadline
  // AQUÍ, una entrada ya vencida (p.ej. huérfana de un reinicio del backend:
  // Flask la olvida y la reencola con un rid nuevo, pero esta pestaña nunca
  // se reinició y la entrada vieja sigue en _pending) podía quedar hasta 5s
  // como candidata válida y "robarse" el siguiente media_id/video real que
  // llegara — corriendo en cascada todo lo que sigue. Ahora se descarta por
  // timeout en el momento de reclamar, antes de poder competir por nada.
  function _claimOldestPending() {
    while (_pending.length > 0) {
      if (_pending[0].claimed) { _pending.shift(); continue; }
      if (Date.now() > _pending[0].deadline) {
        var expired = _pending.shift();
        expired.claimed = true; // evita que _watchEntryNode siga vigilando y entregue tarde por duplicado
        console.warn('[VF] ⏰ entry vencida purgada de _pending al reclamar (evita que absorba el media_id de otro job):', expired.requestId.slice(0, 8));
        _deliverResult(expired, null);
        continue;
      }
      break;
    }
    // Si el más antiguo de la fila YA tiene su nodo DOM propio confirmado,
    // este evento (media_id/video genérico, sin saber a quién pertenece)
    // probablemente es DE ÉL — pero como _watchEntryNode ya lo va a resolver
    // por su propio contenedor, no hace falta usarlo. CRÍTICO: no hay que
    // "saltarlo" y reasignar el evento al SIGUIENTE job de la fila (versión
    // anterior de este código, bug real confirmado en uso real: un media_id
    // que llegó mientras el job viejo era el único pendiente terminó
    // asignado, varios cientos de ms después, al job nuevo que mientras tanto
    // se había agregado a _pending — mismo bug de fondo de toda la sesión,
    // por una vía nueva). Se descarta el evento entero en vez de adivinar:
    // mejor perder esta señal puntual que mezclar el contenido de dos jobs.
    if (_pending[0].domNode) return null;
    var entry = _pending.shift();
    entry.claimed = true;
    return entry;
  }

  // Único embudo por el que pasan TODAS las entregas (WS directo, FIFO de
  // respaldo, fallback de DOM/buffer, watchdog). Aunque dos jobs resuelvan su
  // URL casi al mismo tiempo desde caminos distintos (cada uno con su propio
  // _isKnownVideo() ya superado antes de que el otro registrara nada),
  // JS procesa estas llamadas una por una — así que este es el único punto
  // donde un duplicado NO puede pasar de largo: si la URL ya fue entregada a
  // otro job, se descarta aquí y el job vuelve a la cola a esperar su propio
  // video real, en vez de quedarse con el de otro.
  function _deliverResult(entry, url) {
    if (url && _isKnownVideo(url)) {
      console.warn('[VF] ⚠️ URL duplicada bloqueada en _deliverResult (ya entregada a otro job) — reintento', entry.requestId.slice(0, 8));
      entry.claimed = false;
      _pending.push(entry);
      return false;
    }
    if (url) _markKnownVideo(url);
    console.log('[VF]', url ? '✅' : '⚠️ timeout', entry.requestId.slice(0, 8), url ? url.slice(0, 70) : '(sin video)');
    window.postMessage({ type: 'META_GEN_RESULT', requestId: entry.requestId, url: url || '', error: url ? '' : 'timeout sin video', captured: [] }, '*');
    return true;
  }

  // Consumidor del WS: cada media_id nuevo se asigna al job pendiente más antiguo.
  setInterval(function () {
    while (_wsMediaBuffer.length > 0 && _pending.length > 0) {
      var item = _wsMediaBuffer.shift();
      if (_suppressNextMediaId > 0) {
        _suppressNextMediaId--;
        console.warn('[VF] 🗑️ media_id descartado por error reciente de Ecto (evita corrimiento FIFO):', item.id);
        continue;
      }
      var entry = _claimOldestPending();
      if (!entry) break;
      console.log('[VF] 🔌 media_id via WS:', item.id, '→', entry.requestId.slice(0, 8));
      (function (e, mediaId) {
        _pollMediaResult(mediaId, _lastConvId, e.deadline)
          .then(function (url) { _deliverResult(e, url); })
          .catch(function (err) { console.warn('[VF] ⚠️ pollMediaResult:', String(err).slice(0, 100)); _deliverResult(e, null); });
      })(entry, item.id);
    }
  }, 300);

  // Consumidor de fallback (DOM/<video>/buffer GQL) — mismo principio FIFO.
  // FALLBACK_GRACE_MS: le da al camino rápido (WS→GraphQL) un margen exclusivo
  // antes de que el fallback pueda reclamar nada. Sin esto, mientras el
  // camino rápido todavía está esperando la respuesta async de _pollMediaResult
  // para el job más antiguo, el fallback puede "ver" ese mismo video ya
  // renderizado en el DOM y asignarlo a OTRO job — el mismo video termina
  // repetido en dos jobs distintos y un tercero se queda sin resultado.
  var FALLBACK_GRACE_MS = 12000;
  setInterval(function () {
    if (_pending.length === 0) return;
    if (Date.now() - _pending[0].submittedAt < FALLBACK_GRACE_MS) return;
    for (var i = _recentVideoUrls.length - 1; i >= 0; i--) {
      var rv = _recentVideoUrls[i];
      if (_isKnownVideo(rv.url)) { _recentVideoUrls.splice(i, 1); continue; }
      _recentVideoUrls.splice(i, 1);
      var claimed = _claimOldestPending();
      if (claimed) _deliverResult(claimed, rv.url);
      break;
    }
    document.querySelectorAll('video').forEach(function (v) {
      if (_pending.length === 0) return;
      var src = v.src || v.currentSrc || v.getAttribute('src') || '';
      if (!src) v.querySelectorAll('source').forEach(function (s) { src = src || s.src || s.getAttribute('src') || ''; });
      if (!src || !src.startsWith('http') || _isKnownVideo(src)) return;
      // Si este <video> vive dentro del contenedor propio de un job que YA
      // tiene su nodo DOM confirmado, dejarlo — _watchEntryNode lo va a
      // recoger y entregarlo con certeza total. Tomarlo aquí por FIFO
      // genérico podría asignarlo al job pendiente equivocado.
      for (var pi = 0; pi < _pending.length; pi++) {
        if (_pending[pi].domNode && _pending[pi].domNode.contains(v)) return;
      }
      // OJO: no marcar _markKnownVideo aquí antes de _deliverResult — bug real
      // confirmado en uso: eso hacía que el propio chequeo de duplicado de
      // _deliverResult SIEMPRE viera la URL como "ya conocida" (porque la
      // acabábamos de marcar nosotros mismos) y la rechazara aunque fuera
      // legítima — _deliverResult ya marca por su cuenta si la entrega tiene
      // éxito, no hace falta (ni es seguro) adelantarlo aquí.
      var claimed2 = _claimOldestPending();
      if (claimed2) _deliverResult(claimed2, src);
    });
  }, 1500);

  // Watchdog: resuelve por timeout cualquier job que se pasó del deadline sin resultado.
  setInterval(function () {
    while (_pending.length > 0 && !_pending[0].claimed && Date.now() > _pending[0].deadline) {
      var e = _claimOldestPending();
      if (e) _deliverResult(e, null);
    }
  }, 5000);

  // ── Listener de mensajes del bridge ───────────────────────────────────
  window.addEventListener('message', function (ev) {
    if (ev.source !== window || !ev.data) return;
    if (ev.data.type === 'META_GEN_REQUEST') _enqueueDOMJob(ev.data);
  });

  // ── Señal al bridge ────────────────────────────────────────────────────
  window.postMessage({ type: 'META_MAIN_READY' }, '*');
  console.log('[VideoForge] meta_token_gen.js v6.5 — root cause real encontrado por inspección en vivo (009 duplicado con 012, 012 como 014): Meta solo mantiene 2 mensajes de asistente MONTADOS en el DOM a la vez (virtualización agresiva) — sin scroll real de usuario, los mensajes nuevos podían quedar montados fuera de esa ventana antes de detectarlos, cayendo TODOS los jobs después del 2do al WS/FIFO de respaldo (el mecanismo menos confiable). Fix: (1) se fuerza scroll al final antes de cada poll y al registrar cada espera. (2) _watchEntryNode detecta si su nodo fue RECICLADO (reusado para otro mensaje por la lista virtualizada) comparando data-message-id, y si pasa, abandona ese nodo y vuelve a esperar uno nuevo en vez de leer el video de otro job por error.');
})();
