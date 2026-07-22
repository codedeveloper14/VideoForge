// background.js v7.6
var BRIDGE_PORT = 5556;
var WS_PORT     = 5557;
var BRIDGE_BASE = "http://127.0.0.1:" + BRIDGE_PORT;
var WS_URL      = "ws://127.0.0.1:" + WS_PORT;
var FLOW_HOST   = "labs.google";

var _ws             = null;
var _wsReconnTimer  = null;
var _accountToTab   = {};
var _tabToAccount   = {};
var _activeRequests = {};
var _bearerCache    = {};  // hash → bearer, persiste mientras el SW vive
var _emailCache     = {};  // hash → email, para que el backend muestre "Conectado como X" sin que el usuario haga nada
var MAX_CONCURRENT  = 10;
var _pollTimer      = null;

function getActiveCount(h) { return _activeRequests[h] || 0; }
function incActive(h)      { _activeRequests[h] = getActiveCount(h) + 1; }
function decActive(h)      { _activeRequests[h] = Math.max(0, getActiveCount(h) - 1); }

// ── Keepalive: storage ping cada 4s ──────────────────────────────────────────
setInterval(function() {
  chrome.storage.local.set({ _ka: Date.now() }, function() {});
}, 4000);

// Dominios que NUNCA se deben cerrar (slots activos de generación)
var _PROTECTED_HOSTS = ['labs.google', 'meta.ai', 'grok.com', 'qwen.ai', 'vibes.ai'];

function _isProtected(url) {
  if (!url) return false;
  for (var i = 0; i < _PROTECTED_HOSTS.length; i++) {
    if (url.indexOf(_PROTECTED_HOSTS[i]) >= 0) return true;
  }
  return false;
}

// Pestañas recién creadas (de CUALQUIER origen: chrome.tabs.create de esta
// extensión, o el subproceso de Chrome lanzado por Python con varias URLs de
// arranque) — _cleanupTabs corría con solo 1s de margen tras crearse una
// pestaña nueva, y con varias pestañas de meta.ai compitiendo por red/CPU al
// mismo tiempo, una pestaña lenta podía seguir en "about:blank" (sin
// "meta.ai" todavía en su url) en ese momento — _isProtected la veía como NO
// protegida y la cerraba por error. Con 3 pestañas casi nunca alcanzaba a
// pasar; con 5+ era mucho más probable, explicando que algunos slots nunca
// llegaran a registrarse. Se les da un margen de gracia antes de poder
// cerrarlas, sin importar su url todavía.
var _recentlyCreatedTabs = {};   // tabId → timestamp de creación
var CLEANUP_GRACE_MS = 20000;
function _isRecentlyCreated(tabId) {
  var ts = _recentlyCreatedTabs[tabId];
  if (!ts) return false;
  if (Date.now() - ts > CLEANUP_GRACE_MS) { delete _recentlyCreatedTabs[tabId]; return false; }
  return true;
}

// ── Cerrar pestañas extra — solo mantener Flow y slots activos ───────────────
function _cleanupTabs() {
  try {
    chrome.tabs.query({}, function(tabs) {
      if (!tabs || tabs.length === 0) return;
      var flowTabs = [], otherTabs = [];
      tabs.forEach(function(t) {
        if (t.url && t.url.indexOf(FLOW_HOST) >= 0) flowTabs.push(t);
        else otherTabs.push(t);
      });
      // Si hay tabs de Flow, cerrar solo tabs que NO son slots activos
      if (flowTabs.length > 0) {
        otherTabs.forEach(function(t) {
          if (!_isProtected(t.url) && !_isRecentlyCreated(t.id) && t.status !== 'loading') {
            try { chrome.tabs.remove(t.id); } catch(e) {}
          }
        });
      }
      // Si hay múltiples Flow, mantener solo la primera (menor id = más antigua = la activa)
      if (flowTabs.length > 1) {
        flowTabs.sort(function(a,b){ return a.id - b.id; });
        for (var i = 1; i < flowTabs.length; i++) {
          try { chrome.tabs.remove(flowTabs[i].id); } catch(e) {}
        }
      }
    });
  } catch(e) {}
}

// ── Abrir N tabs de meta.ai ───────────────────────────────────────────────────
var _metaTabsOpening = false;
function _openMetaTabs(needed) {
  if (_metaTabsOpening || needed <= 0) return;
  _metaTabsOpening = true;
  var opened = 0;
  function openNext() {
    if (opened >= needed) { _metaTabsOpening = false; return; }
    opened++;
    chrome.tabs.create({ url: 'https://www.meta.ai/', active: false }, function(tab) {
      // Sin esto, Chrome "Memory Saver" descarga/congela las pestañas en
      // segundo plano bajo presión de memoria — con muchas pestañas dejaban
      // de ejecutar nada hasta que el usuario les daba foco manualmente.
      if (tab && tab.id) {
        try { chrome.tabs.update(tab.id, { autoDiscardable: false }, function() {}); } catch (e) {}
        _recentlyCreatedTabs[tab.id] = Date.now();
      }
      setTimeout(openNext, 1200);  // 1.2s entre cada apertura para que meta.ai no bloquee
    });
  }
  openNext();
}
// Limpiar al arrancar (3s para que carguen todas las tabs)
setTimeout(_cleanupTabs, 3000);
// También limpiar cuando se crea una pestaña nueva
try {
  chrome.tabs.onCreated.addListener(function(tab) {
    if (tab && tab.id) _recentlyCreatedTabs[tab.id] = Date.now();
    setTimeout(_cleanupTabs, 1000);
  });
} catch(e) {}

// ── WebSocket ────────────────────────────────────────────────────────────────
function wsConnect() {
  if (_ws && (_ws.readyState === 0 || _ws.readyState === 1)) return;
  try {
    console.log("[Imperio BG] WS: intentando conectar a " + WS_URL);
    _ws = new WebSocket(WS_URL);
  } catch(e) {
    console.log("[Imperio BG] WS: constructor falló: " + e.message);
    return;
  }
  _ws.onopen = function() {
    console.log("[Imperio BG] WS: conectado OK — registrando cuentas: " + JSON.stringify(Object.keys(_accountToTab)));
    Object.keys(_accountToTab).forEach(function(h) {
      try { _ws.send(JSON.stringify({ type: "register", account_hash: h, bearer: _bearerCache[h] || "", email: _emailCache[h] || "" })); } catch(e) {}
    });
  };
  _ws.onmessage = function(ev) {
    try {
      var msg = JSON.parse(ev.data);
      if (msg.type === "generate" && msg.requests)
        msg.requests.forEach(function(r) { dispatch(r, msg.account_hash); });
    } catch(e) {}
  };
  _ws.onclose = function(ev) {
    console.log("[Imperio BG] WS: desconectado code=" + ev.code + " reason=" + ev.reason + " wasClean=" + ev.wasClean);
    _ws = null;
    if (!_wsReconnTimer)
      _wsReconnTimer = setTimeout(function() { _wsReconnTimer = null; wsConnect(); }, 3000);
  };
  _ws.onerror = function(ev) {
    console.log("[Imperio BG] WS: error — readyState=" + (_ws ? _ws.readyState : 'null'));
  };
}

function dispatch(req, accountHash) {
  var hash  = accountHash || req.account_hash;
  // NUNCA caer a "cualquier pestaña registrada" cuando el hash pedido no tiene tab --
  // ese fallback es lo que mandaba requests de Flow a la pestaña de Vibes (o viceversa)
  // cuando la cuenta correcta no estaba registrada en el momento exacto del dispatch.
  // Si el hash pedido no tiene tab, la request falla explícito (no_tab) y el backend
  // reintenta/rota -- nunca se ejecuta contra la pestaña equivocada.
  var tabId = hash ? _accountToTab[hash] : null;
  if (!tabId) { sendResultHttp({ requestId: req.requestId, error: "no_tab" }); return; }
  incActive(hash);
  chrome.tabs.sendMessage(tabId, {
    type: "FLOW_GENERATE_REQUEST", requestId: req.requestId,
    url: req.url, bearer: req.bearer, body: req.body, kind: req.kind
  }, function() {
    if (chrome.runtime.lastError) {
      decActive(hash);
      sendResultHttp({ requestId: req.requestId, error: "tab_unreachable" });
    }
  });
}

function sendResultHttp(data) {
  fetch(BRIDGE_BASE + "/flow-generate-result", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ requestId: data.requestId, status: data.status||0, body: data.body||"", error: data.error||"" })
  }).catch(function(){});
}

function pollBridge() {
  var hashes = Object.keys(_accountToTab);
  if (!hashes.length) return;
  hashes.forEach(function(hash) {
    if (MAX_CONCURRENT - getActiveCount(hash) <= 0) return;
    fetch(BRIDGE_BASE + "/flow-generate-poll?account=" + encodeURIComponent(hash))
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var reqs = (data&&data.requests&&data.requests.length) ? data.requests
                 : (data&&data.request) ? [data.request] : [];
        reqs.forEach(function(r) { dispatch(r, hash); });
      })
      .catch(function() {});
  });
}

// Verificacion de origen: un hash "flow:*" solo puede registrarse desde una pestaña
// de labs.google/fx/tools/flow, y un hash "vibes:*" solo desde vibes.ai -- aunque el
// hash este bien formado y namespaceado, sin este chequeo nada impide que llegue
// registrado desde la pestaña equivocada (bug, contenido inyectado, etc.). Los
// patrones espejan exactamente los "matches" de content_scripts en manifest.json.
var FLOW_TAB_RE  = /^https:\/\/labs\.google(\.com)?\/fx\/([^/]+\/)?tools\/flow/;
var VIBES_TAB_RE = /^https:\/\/www\.vibes\.ai\//;

function _originMatchesHash(hash, url) {
  if (!hash || !url) return false;
  if (hash.indexOf("flow:") === 0) return FLOW_TAB_RE.test(url);
  if (hash.indexOf("vibes:") === 0) return VIBES_TAB_RE.test(url);
  return true; // hash sin namespace reconocido (otro proveedor) -- no es este chequeo
}

function registerHttp(hash) {
  fetch(BRIDGE_BASE + "/flow-register?account=" + encodeURIComponent(hash)).catch(function(){});
}

function registerBearer(hash, bearer, email) {
  if (!bearer) return;
  fetch(BRIDGE_BASE + "/flow-register-bearer", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account: hash, bearer: bearer, email: email || "" })
  }).catch(function(){});
}

// ── Vibes: bridge propio en el puerto 8080 (mismo Flask que sirve el resto de la
// app, ver src/infrastructure/ai_providers/vibes_bridge.py), separado del bridge
// compartido de Flow (5556/5557). El poll/post real tiene que salir DESDE ESTE
// service worker, no desde un content script (ni MAIN ni ISOLATED) -- confirmado
// en vivo (2026-07-20): Chrome bloquea con "Permission was denied for this
// request to access the `loopback` address space" (Local Network Access) un
// fetch() a 127.0.0.1 hecho por CUALQUIER content script de una pestaña publica,
// sin importar el "world" ni los host_permissions declarados. Solo el contexto
// propio de la extension (este background) queda exento -- por eso Flow, que
// siempre pollea desde aca (pollBridge() arriba), nunca tuvo este problema.
var VIBES_BRIDGE_BASE = "http://127.0.0.1:8080/api/vibes";
var _vibesTabId = null;
var _vibesPollTimer = null;

function vibesPoll() {
  if (!_vibesTabId) return;
  fetch(VIBES_BRIDGE_BASE + "/poll?account=default&max=10")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var reqs = (data && data.requests) || [];
      if (!reqs.length || !_vibesTabId) return;
      reqs.forEach(function (job) {
        chrome.tabs.sendMessage(_vibesTabId, { type: "VIBES_JOB", job: job }, function () {
          void chrome.runtime.lastError; // pestaña cerrada entre el poll y el dispatch -- se ignora
        });
      });
    })
    .catch(function () {});
}

function vibesSendResult(payload) {
  fetch(VIBES_BRIDGE_BASE + "/result", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload), keepalive: true
  }).catch(function(){});
}

function _ensureVibesPollTimer() {
  if (_vibesPollTimer) return;
  _vibesPollTimer = setInterval(vibesPoll, 1200);
}
function _stopVibesPollTimer() {
  if (!_vibesPollTimer) return;
  clearInterval(_vibesPollTimer);
  _vibesPollTimer = null;
}

// ── Qwen: mismo patron que Vibes arriba (bridge propio en el puerto 8080,
// poll/post real desde este service worker por la misma restriccion de Local
// Network Access) pero con una diferencia clave: cada cuenta Qwen corre en su
// PROPIO proceso de Chromium (perfil + extension propios), asi que no hace
// falta un mapa cuenta->tab como en Flow -- este service worker en particular
// solo va a ver UNA pestaña de chat.qwen.ai en toda su vida (la de su propio
// perfil), y ya sabe de antemano cual cuenta es (se la paso yo mismo al
// lanzar Chromium via ?imperio_qwen_account=<nombre>).
var QWEN_TAB_RE = /^https:\/\/([\w-]+\.)?qwen\.ai\//;
var QWEN_BRIDGE_BASE = "http://127.0.0.1:8080/api/qwen";
var _qwenAccountName = null;
var _qwenTabId = null;
var _qwenPollTimer = null;

function qwenPoll() {
  if (!_qwenTabId || !_qwenAccountName) return;
  fetch(QWEN_BRIDGE_BASE + "/poll?account=" + encodeURIComponent(_qwenAccountName) + "&max=10")
    .then(function (r) { return r.json(); })
    .then(function (data) {
      var reqs = (data && data.requests) || [];
      if (!reqs.length || !_qwenTabId) return;
      reqs.forEach(function (job) {
        chrome.tabs.sendMessage(_qwenTabId, { type: "QWEN_JOB", job: job }, function () {
          void chrome.runtime.lastError; // pestaña cerrada entre el poll y el dispatch -- se ignora
        });
      });
    })
    .catch(function () {});
}

function qwenSendResult(payload) {
  fetch(QWEN_BRIDGE_BASE + "/result", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload), keepalive: true
  }).catch(function(){});
}

function _ensureQwenPollTimer() {
  if (_qwenPollTimer) return;
  _qwenPollTimer = setInterval(qwenPoll, 1200);
}
function _stopQwenPollTimer() {
  if (!_qwenPollTimer) return;
  clearInterval(_qwenPollTimer);
  _qwenPollTimer = null;
}

// ── Qwen: adjuntar imagen via CDP (chrome.debugger) -- ningun content script
// puede asignar input.files por JS, en ningun contexto ni navegador (bloqueo
// de seguridad del browser, no de permisos de la extension). El unico camino
// real es que el propio protocolo de depuracion de Chrome se lo asigne, igual
// que hacen Playwright/Puppeteer por debajo. Deja la barra amarilla de
// "depurando este navegador" visible unos segundos mientras corre.
function qwenAttachFile(tabId, selector, filePaths) {
  return new Promise(function (resolve, reject) {
    chrome.debugger.attach({ tabId: tabId }, "1.3", function () {
      if (chrome.runtime.lastError) {
        reject(new Error(chrome.runtime.lastError.message));
        return;
      }
      function detachAndReject(err) {
        chrome.debugger.detach({ tabId: tabId }, function () { void chrome.runtime.lastError; });
        reject(err instanceof Error ? err : new Error(String(err)));
      }
      chrome.debugger.sendCommand({ tabId: tabId }, "DOM.getDocument", {}, function (doc) {
        if (chrome.runtime.lastError || !doc || !doc.root) {
          detachAndReject(chrome.runtime.lastError || new Error("DOM.getDocument sin resultado"));
          return;
        }
        chrome.debugger.sendCommand(
          { tabId: tabId }, "DOM.querySelector",
          { nodeId: doc.root.nodeId, selector: selector },
          function (node) {
            if (chrome.runtime.lastError || !node || !node.nodeId) {
              detachAndReject(chrome.runtime.lastError || new Error("selector no encontrado: " + selector));
              return;
            }
            chrome.debugger.sendCommand(
              { tabId: tabId }, "DOM.setFileInputFiles",
              { files: filePaths, nodeId: node.nodeId },
              function () {
                var err = chrome.runtime.lastError;
                chrome.debugger.detach({ tabId: tabId }, function () { void chrome.runtime.lastError; });
                if (err) reject(new Error(err.message));
                else resolve(true);
              }
            );
          }
        );
      });
    });
  });
}

chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (!msg || !msg.type) return;

  if (msg.type === "CLOSE_OTHER_TABS") {
    // Cerrar todas las pestañas excepto la de Flow que envió este mensaje
    var flowTabId = sender.tab && sender.tab.id;
    try {
      chrome.tabs.query({}, function(tabs) {
        tabs.forEach(function(t) {
          if (t.id !== flowTabId) {
            try { chrome.tabs.remove(t.id); } catch(e) {}
          }
        });
      });
    } catch(e) {}
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "REGISTER_ACCOUNT") {
    var hash = msg.accountHash, tabId = sender.tab && sender.tab.id;
    var tabUrl = sender.tab && sender.tab.url;
    if (hash && tabId && !_originMatchesHash(hash, tabUrl)) {
      console.log("[Imperio BG] REGISTER_ACCOUNT rechazado -- hash " + hash + " no coincide con origen " + tabUrl);
      sendResponse({ ok: false, error: "origin_mismatch" });
      return true;
    }
    if (hash && tabId) {
      _accountToTab[hash] = tabId;
      _tabToAccount[tabId] = hash;
      if (msg.email) _emailCache[hash] = msg.email;
      registerHttp(hash);
      if (msg.bearer) {
        _bearerCache[hash] = msg.bearer;
        registerBearer(hash, msg.bearer, _emailCache[hash] || "");
      }
      if (_ws && _ws.readyState === 1) {
        try { _ws.send(JSON.stringify({ type: "register", account_hash: hash, bearer: _bearerCache[hash] || "", email: _emailCache[hash] || "" })); } catch(e) {}
      }
      if (!_ws || _ws.readyState > 1) wsConnect();
    }
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "FLOW_RESULT") {
    var h = sender.tab && _tabToAccount[sender.tab.id];
    if (h) decActive(h);
    sendResultHttp({ requestId: msg.requestId, status: msg.status, body: msg.body, error: msg.error });
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "FLOW_BRIDGE_POLL") {
    fetch(BRIDGE_BASE + (msg.path || "/flow-generate-poll"))
      .then(function(r) { return r.json(); })
      .then(function(d) { sendResponse({ ok: true, data: d }); })
      .catch(function(e) { sendResponse({ ok: false, error: e.message }); });
    return true;
  }
  if (msg.type === "FLOW_BRIDGE_RESULT") {
    fetch(BRIDGE_BASE + "/flow-generate-result", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(msg.data)
    }).then(function() { sendResponse({ ok: true }); })
      .catch(function(e) { sendResponse({ ok: false, error: e.message }); });
    return true;
  }
  if (msg.type === "META_OPEN_TABS") {
    var needed = (msg.count || 0);
    if (needed > 0) _openMetaTabs(needed);
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "PING_BRIDGE" || msg.type === "PING") {
    fetch(BRIDGE_BASE + "/health")
      .then(function(r) { sendResponse({ ok: r.ok }); })
      .catch(function() { sendResponse({ ok: false }); });
    return true;
  }

  if (msg.type === "VIBES_REGISTER_TAB") {
    var vTabId = sender.tab && sender.tab.id;
    var vTabUrl = sender.tab && sender.tab.url;
    if (vTabId && VIBES_TAB_RE.test(vTabUrl || "")) {
      _vibesTabId = vTabId;
      _ensureVibesPollTimer();
      sendResponse({ ok: true });
    } else {
      sendResponse({ ok: false, error: "origin_mismatch" });
    }
    return true;
  }

  if (msg.type === "VIBES_RESULT") {
    vibesSendResult(msg.payload);
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "REGISTER_QWEN_ACCOUNT") {
    var qTabId = sender.tab && sender.tab.id;
    var qTabUrl = sender.tab && sender.tab.url;
    if (qTabId && msg.account && QWEN_TAB_RE.test(qTabUrl || "")) {
      _qwenAccountName = msg.account;
      _qwenTabId = qTabId;
      _ensureQwenPollTimer();
      sendResponse({ ok: true });
    } else {
      sendResponse({ ok: false, error: "origin_mismatch" });
    }
    return true;
  }

  if (msg.type === "QWEN_RESULT") {
    qwenSendResult(msg.payload);
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "QWEN_ATTACH_FILE") {
    var qaTabId = sender.tab && sender.tab.id;
    if (!qaTabId) {
      sendResponse({ ok: false, error: "no_tab" });
      return true;
    }
    qwenAttachFile(qaTabId, msg.selector || "#filesUpload", msg.filePaths || [])
      .then(function () { sendResponse({ ok: true }); })
      .catch(function (err) { sendResponse({ ok: false, error: String((err && err.message) || err) }); });
    return true; // respuesta asincrona
  }
});

chrome.runtime.onConnect.addListener(function(port) {
  if (port.name === "flow-keepalive")
    port.onDisconnect.addListener(function() {});
});

chrome.tabs.onRemoved.addListener(function(tabId) {
  var hash = _tabToAccount[tabId];
  if (hash) { delete _accountToTab[hash]; delete _activeRequests[hash]; }
  delete _tabToAccount[tabId];
  delete _recentlyCreatedTabs[tabId];
  if (_vibesTabId === tabId) { _vibesTabId = null; _stopVibesPollTimer(); }
  if (_qwenTabId === tabId) { _qwenTabId = null; _qwenAccountName = null; _stopQwenPollTimer(); }
});

// ── Anti-throttling: Chrome congela los timers (setTimeout/setInterval) de
// pestañas/ventanas que quedan ocultas tras otra (occlusion) o sin foco por
// un rato — los bridges dejaban de hacer polling hasta que el usuario hacía
// clic manualmente en cada pestaña para "despertarla". Solución: rotar el
// foco automáticamente entre todas las pestañas meta.ai registradas, dándole
// a cada una un instante "activa/visible" antes de pasar a la siguiente —
// así ninguna queda oculta el tiempo suficiente para que Chrome la congele.
function _grantFocus(tabId) {
  try {
    chrome.tabs.update(tabId, { active: true }, function (tab) {
      if (chrome.runtime.lastError || !tab) return;
      try { chrome.windows.update(tab.windowId, { focused: true }); } catch (e) {}
    });
  } catch (e) {}
}
// _tabToAccount SOLO se llena vía el mensaje "REGISTER_ACCOUNT", que es del
// flujo de Flow/labs.google — meta_bridge.js y meta_token_gen.js NUNCA lo
// envían (confirmado por grep: no existe ese sendMessage en esos archivos).
// Las versiones anteriores (v6.6-v6.9) rotaban foco sobre _tabToAccount, que
// para meta.ai estaba SIEMPRE VACÍO — la rotación nunca tocaba estas
// pestañas, sin importar cuánto se ajustara el intervalo. Ahora se detectan
// las pestañas de meta.ai directamente por su URL, igual que _isProtected.
function _isMetaTab(url) { return !!url && url.indexOf('meta.ai') !== -1; }
function _getMetaTabIds(cb) {
  chrome.tabs.query({}, function (tabs) {
    var ids = [];
    (tabs || []).forEach(function (t) { if (_isMetaTab(t.url)) ids.push(t.id); });
    cb(ids);
  });
}
// _openMetaTabs (chrome.tabs.create) ya pone autoDiscardable:false, pero las
// pestañas de meta.ai casi siempre las abre el PROCESO de Python al lanzar
// Chrome con varias URLs de arranque — esas nunca pasan por _openMetaTabs,
// así que en la práctica quedaban SIN esta protección. Bajo presión de
// memoria (más probable con 5+ pestañas), Chrome "Memory Saver" puede
// descargarlas — eso se ve exactamente como una pestaña que "muere" y queda
// inactiva hasta que se le hace clic manualmente. Se aplica a cualquier
// pestaña de meta.ai sin importar quién la creó.
function _protectFromDiscard(tabId) {
  try { chrome.tabs.update(tabId, { autoDiscardable: false }, function () { void chrome.runtime.lastError; }); } catch (e) {}
}
var _focusRotateIdx = 0;
// El reset por inactividad (RESET_IDLE_MS en meta_bridge.js) navega la
// pestaña a meta.ai/ para limpiar el composer — si en ESE instante la
// rotación ya le había dado el turno a otra pestaña, esta queda en segundo
// plano justo cuando más necesita CPU para que sus setTimeout de arranque
// (_register/_schedulePoll) corran sin throttling. Confirmado: pestañas que
// se quedan "pegadas sin hacer nada" justo después de actualizarse/recargar.
// Foco inmediato al detectar la recarga, sin esperar el turno de rotación.
try {
  chrome.tabs.onUpdated.addListener(function (tabId, changeInfo, tab) {
    if (_isMetaTab((tab && tab.url) || changeInfo.url)) {
      _protectFromDiscard(tabId);
      if (changeInfo.status === 'loading') _grantFocus(tabId);
    }
  });
} catch (e) {}
// Con un intervalo FIJO de 6s, el tiempo que cada pestaña espera para volver
// a tener foco crece con la cantidad de pestañas (3 pestañas → 18s de espera;
// 5 → 30s) — confirmado: con 5 pestañas empezaron a aparecer "muertas" que
// antes con 3 no se veían. Se recalcula el intervalo para que el CICLO
// completo (todas las pestañas visitadas una vez) dure ~15s sin importar
// cuántas haya, en vez de que cada pestaña tarde más cuantas más se agreguen.
var ROTATE_CYCLE_MS = 15000;
var _rotateTimer = null;

// ── Foco sostenido a pedido ─────────────────────────────────────────────────
// meta_token_gen.js pide foco justo antes de adjuntar+enviar (el tramo
// sensible a estar en segundo plano) y lo libera al terminar. Mientras hay
// una pestaña con el foco reservado, la rotación normal se pausa para ESA
// pestaña — si hay más pestañas pidiendo foco a la vez, se atienden en orden
// de llegada. FOCUS_HOLD_MAX_MS es una red de seguridad por si el aviso de
// "terminé" nunca llega (ej. la pestaña se recarga a mitad de camino).
var _focusQueue       = [];   // tabIds esperando su turno con foco garantizado
var _focusHoldTabId   = null;
var _focusHoldUntil   = 0;
var FOCUS_HOLD_MAX_MS = 6000;

function _requestFocus(tabId) {
  if (!tabId) return;
  if (_focusHoldTabId === tabId) { _focusHoldUntil = Date.now() + FOCUS_HOLD_MAX_MS; return; }
  if (_focusQueue.indexOf(tabId) === -1) _focusQueue.push(tabId);
  if (_rotateTimer) { clearTimeout(_rotateTimer); _scheduleRotate(); } // no esperar al próximo tick
}
function _releaseFocusHold(tabId) {
  if (!tabId) return;
  if (_focusHoldTabId === tabId) { _focusHoldTabId = null; _focusHoldUntil = 0; }
  var idx = _focusQueue.indexOf(tabId);
  if (idx !== -1) _focusQueue.splice(idx, 1);
}
try {
  chrome.runtime.onMessage.addListener(function (msg, sender) {
    if (!msg || !sender || !sender.tab) return;
    if (msg.type === 'META_NEED_FOCUS') _requestFocus(sender.tab.id);
    else if (msg.type === 'META_FOCUS_DONE') _releaseFocusHold(sender.tab.id);
  });
} catch (e) {}

function _scheduleRotate() {
  _getMetaTabIds(function (tabIds) {
    tabIds.forEach(_protectFromDiscard);
    var now = Date.now();
    if (_focusHoldTabId && now > _focusHoldUntil) _focusHoldTabId = null; // venció, nunca llegó el DONE
    if (!_focusHoldTabId && _focusQueue.length > 0) {
      _focusHoldTabId = _focusQueue.shift();
      _focusHoldUntil = now + FOCUS_HOLD_MAX_MS;
    }
    if (_focusHoldTabId) {
      _grantFocus(_focusHoldTabId);
    } else if (tabIds.length > 1) {
      _focusRotateIdx = (_focusRotateIdx + 1) % tabIds.length;
      _grantFocus(tabIds[_focusRotateIdx]);
    } else if (tabIds.length === 1) {
      _grantFocus(tabIds[0]);
    }
    var n = Math.max(1, tabIds.length);
    var interval = Math.max(2000, Math.round(ROTATE_CYCLE_MS / n));
    // Con un hold activo o pedidos en cola, revisar más seguido — no hacer
    // esperar al resto el ciclo completo de rotación normal.
    if (_focusHoldTabId || _focusQueue.length > 0) interval = Math.min(interval, 800);
    _rotateTimer = setTimeout(_scheduleRotate, interval);
  });
}
_scheduleRotate();

try {
  chrome.alarms.create("hb", { periodInMinutes: 0.5 });
  chrome.alarms.onAlarm.addListener(function(a) {
    if (a.name === "hb") { Object.keys(_accountToTab).forEach(registerHttp); wsConnect(); }
  });
} catch(e) {}

_pollTimer = setInterval(pollBridge, 1000);
wsConnect();
console.log("[Imperio BG] v7.6 started — dispatch() ya no cae a 'cualquier pestaña registrada' cuando el hash pedido no tiene tab (podia mandar requests de Flow a la pestaña de Vibes o viceversa); REGISTER_ACCOUNT ahora verifica que el origen (sender.tab.url) coincida con el namespace del hash ('flow:'→labs.google/fx/tools/flow, 'vibes:'→www.vibes.ai) antes de aceptar el registro (v7.6). + vibes.ai agregado a _PROTECTED_HOSTS (v7.5) + dispatch() propaga 'kind' para uploads multipart (v7.4) + registro de cuentas incluye email (v7.3) + foco sostenido a pedido (v7.2) + autoDiscardable:false universal (v7.1) + rotación por URL (v7.0).");
