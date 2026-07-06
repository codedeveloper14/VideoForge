// flow_content.js v5.1
// Cerrar pestañas que no sean Flow — ejecutar al cargar la página
(function() {
  try {
    chrome.runtime.sendMessage({ type: "CLOSE_OTHER_TABS" });
  } catch(e) {}
})();

// ── WebSocket desde content script (fallback para cuando el SW no puede conectar) ──
// El content script corre en la pestaña labs.google y tiene las mismas
// host_permissions que el background, pero sin las restricciones MV3 del SW.
var _BRIDGE_WS_URL = "ws://127.0.0.1:5557";
var _csWs       = null;
var _csWsReconn = null;

function _csWsConnect() {
  if (_csWs && (_csWs.readyState === 0 || _csWs.readyState === 1)) return;
  if (!_flowAccountHash) return;  // esperar al hash antes de conectar
  try {
    console.log("[Imperio CS] WS: intentando conectar...");
    _csWs = new WebSocket(_BRIDGE_WS_URL);
  } catch(e) {
    console.log("[Imperio CS] WS: constructor falló: " + e.message);
    return;
  }
  _csWs.onopen = function() {
    console.log("[Imperio CS] WS: conectado OK — registrando " + _flowAccountHash);
    try { _csWs.send(JSON.stringify({ type: "register", account_hash: _flowAccountHash, bearer: _flowBearer || "" })); } catch(e) {}
  };
  _csWs.onmessage = function(ev) {
    try {
      var msg = JSON.parse(ev.data);
      if (msg.type === "generate" && msg.requests) {
        msg.requests.forEach(function(r) {
          // Reenviar al MAIN world para que flow_token_gen.js lo procese
          window.postMessage({ type: "FLOW_GENERATE_REQUEST", requestId: r.requestId, url: r.url, bearer: r.bearer, body: r.body }, "*");
        });
      }
    } catch(e) {}
  };
  _csWs.onclose = function(ev) {
    console.log("[Imperio CS] WS: cerrado code=" + ev.code + " wasClean=" + ev.wasClean);
    _csWs = null;
    if (!_csWsReconn)
      _csWsReconn = setTimeout(function() { _csWsReconn = null; _csWsConnect(); }, 5000);
  };
  _csWs.onerror = function() {
    console.log("[Imperio CS] WS: error — readyState=" + (_csWs ? _csWs.readyState : 'null'));
  };
}

var _flowAccountHash  = null;
var _flowBearer       = null;
var _registerPending  = false;
var _registerAttempts = 0;

function registerWithBackground(hash, bearer) {
  if (_registerPending) return;
  _registerPending = true;
  try {
    chrome.runtime.sendMessage({
      type: "REGISTER_ACCOUNT", accountHash: hash, bearer: bearer || null
    }, function(resp) {
      _registerPending = false;
      if (chrome.runtime.lastError) {
        _registerAttempts++;
        var d = Math.min(2000 * Math.pow(1.5, Math.min(_registerAttempts - 1, 5)), 20000);
        setTimeout(function() { registerWithBackground(hash, _flowBearer); }, d);
        return;
      }
      _registerAttempts = 0;
      console.log("[Imperio] Registered OK — " + hash);
    });
  } catch(e) {
    _registerPending = false;
    _registerAttempts++;
    setTimeout(function() { registerWithBackground(hash, _flowBearer); }, 2000);
  }
}

window.addEventListener("message", function(ev) {
  if (ev.source !== window || !ev.data) return;
  if (ev.data.type === "FLOW_ACCOUNT_HASH") {
    _flowAccountHash = ev.data.hash;
    _registerAttempts = 0;
    console.log("[Imperio] Flow account hash set: " + _flowAccountHash);
    registerWithBackground(_flowAccountHash, _flowBearer);
    _csWsConnect();  // iniciar WS del content script ahora que tenemos el hash
    return;
  }
  if (ev.data.type === "FLOW_BEARER_UPDATE") {
    _flowBearer = ev.data.bearer;
    var hash = ev.data.hash || _flowAccountHash;
    if (hash) { _registerAttempts = 0; registerWithBackground(hash, _flowBearer); }
    // Si WS ya está conectado pero sin bearer, re-registrar con bearer
    if (_csWs && _csWs.readyState === 1 && hash) {
      try { _csWs.send(JSON.stringify({ type: "register", account_hash: hash, bearer: _flowBearer || "" })); } catch(e) {}
    } else if (hash) {
      _csWsConnect();  // conectar WS si aún no está conectado
    }
    return;
  }
  if (ev.data.type === "FLOW_GENERATE_RESULT") {
    var rid = ev.data.requestId;
    var resultMsg = { type: "result", requestId: rid, status: ev.data.status || 0, body: ev.data.body || "", error: ev.data.error || "" };
    // Enviar resultado por WS del content script (más directo que HTTP)
    if (_csWs && _csWs.readyState === 1) {
      try { _csWs.send(JSON.stringify(resultMsg)); } catch(e) {}
    }
    // También vía background como fallback
    try {
      chrome.runtime.sendMessage({
        type: "FLOW_RESULT", requestId: rid,
        status: ev.data.status || 0, body: ev.data.body || "", error: ev.data.error || ""
      });
    } catch(e) {}
  }
});

chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (!msg || msg.type !== "FLOW_GENERATE_REQUEST") return;
  window.postMessage({
    type: "FLOW_GENERATE_REQUEST", requestId: msg.requestId,
    url: msg.url, bearer: msg.bearer, body: msg.body
  }, "*");
  sendResponse({ ok: true });
  return true;
});

setInterval(function() {
  if (_flowAccountHash && _registerAttempts === 0)
    registerWithBackground(_flowAccountHash, _flowBearer);
  // Mantener WS del content script activo
  if (_flowAccountHash) _csWsConnect();
}, 45000);

console.log("[Imperio] Flow content script v5.1 (WS desde CS)");
