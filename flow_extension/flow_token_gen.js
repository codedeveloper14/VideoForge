var RECAPTCHA_ACTION = "IMAGE_GENERATION";
var TOKEN_POOL_SIZE = 0;    // pool desactivado — evita execute() background sin control
var TOKEN_MAX_AGE_MS = 100000;

// Detecta el site key reCAPTCHA que usa la página, para evitar usar uno obsoleto.
function _detectSiteKey() {
  try {
    // Patrón más común: <script src="...recaptcha/enterprise.js?render=KEY">
    var scripts = document.querySelectorAll('script[src*="recaptcha"]');
    for (var i = 0; i < scripts.length; i++) {
      var m = scripts[i].src.match(/[?&]render=([A-Za-z0-9_-]+)/);
      if (m && m[1] !== 'explicit') {
        console.log("[Imperio] reCAPTCHA site key detectado del DOM: " + m[1]);
        return m[1];
      }
    }
  } catch(e) {}
  try {
    // Alternativa: grecaptcha guarda el config en window.___grecaptcha_cfg
    var cfg = window.___grecaptcha_cfg;
    if (cfg && cfg.clients) {
      for (var k in cfg.clients) {
        var c = cfg.clients[k];
        if (c && c.sitekey) { console.log("[Imperio] site key de cfg.clients: " + c.sitekey); return c.sitekey; }
        for (var j in c) {
          if (c[j] && typeof c[j] === 'object' && c[j].sitekey) {
            console.log("[Imperio] site key de cfg.clients[k][j]: " + c[j].sitekey); return c[j].sitekey;
          }
        }
      }
    }
  } catch(e) {}
  console.log("[Imperio] site key no detectado — usando hardcoded");
  return "6LdsFiUsAAAAAIjVDZcuLhaHiDn5nnHVXVRQGeMV";
}
var SITE_KEY = _detectSiteKey();
var _tokenPool = [];
var _tokenFetching = 0;
var _maxTokenFetching = 1;
var _currentBearer = "";
var _currentHash   = "";

// ── Project rotation (solución 429) ─────────────────────────────────────────
// Cuando Flow devuelve 429, el proyecto GCP asignado a esta sesión agotó su
// cuota. La solución: crear un proyecto nuevo vía la API de Flow y reemplazar
// el project ID en la URL antes de reintentar.
var _cachedProjectId  = null;   // proyecto activo (se reemplaza al rotar)
var _projectRotating  = false;  // evita rotaciones paralelas
var _rotateCallbacks  = [];     // colas de promesas esperando el nuevo proyecto

// Extrae el project ID de una URL como:
// https://aisandbox-pa.googleapis.com/v1/projects/PROJ_ID/flowMedia:batchGenerateImages
function _extractProjectId(url) {
  var m = url.match(/\/projects\/([^\/]+)\//);
  return m ? m[1] : null;
}

// Reemplaza el project ID en la URL por uno nuevo
function _swapProjectId(url, newId) {
  return url.replace(/\/projects\/[^\/]+\//, "/projects/" + newId + "/");
}

// Llama a la API de Flow para crear (o recuperar) un proyecto nuevo con cuota fresca.
// Devuelve una Promise<string> con el nuevo project ID.
function _createNewFlowProject() {
  console.log("[Imperio] Creando nuevo proyecto Flow para rotar cuota…");
  // Flow crea proyectos automáticamente al llamar a /fx/api/projects
  // Si ya existe uno activo lo devuelve; si está agotado crea uno nuevo.
  return fetch("/fx/api/projects", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ displayName: "vf_" + Date.now() })
  })
  .then(function(r) { return r.json(); })
  .then(function(data) {
    // La respuesta puede ser { name: "projects/NEW_ID", ... }
    var name = data.name || data.projectId || "";
    var newId = name.replace("projects/", "").trim();
    if (!newId) throw new Error("Sin project ID en respuesta: " + JSON.stringify(data));
    console.log("[Imperio] Nuevo proyecto creado: " + newId);
    return newId;
  })
  .catch(function(e) {
    // Fallback: intentar listar proyectos y tomar el más reciente distinto al actual
    console.log("[Imperio] POST /fx/api/projects falló (" + e.message + "), intentando listar…");
    return fetch("/fx/api/projects?pageSize=10", { credentials: "include" })
      .then(function(r) { return r.json(); })
      .then(function(data) {
        var projects = data.projects || data.items || [];
        // Filtrar el proyecto agotado y tomar el más reciente
        var candidates = projects
          .map(function(p) { return (p.name || "").replace("projects/", ""); })
          .filter(function(id) { return id && id !== _cachedProjectId; });
        if (candidates.length > 0) {
          console.log("[Imperio] Proyecto alternativo encontrado: " + candidates[0]);
          return candidates[0];
        }
        throw new Error("No hay proyectos alternativos disponibles");
      });
  });
}

// Rota el proyecto: si ya hay una rotación en curso, encola y espera el resultado.
// Devuelve Promise<string> con el nuevo project ID.
function _rotateProject() {
  if (!_projectRotating) {
    _projectRotating = true;
    _createNewFlowProject()
      .then(function(newId) {
        _cachedProjectId = newId;
        _projectRotating = false;
        var cbs = _rotateCallbacks.splice(0);
        cbs.forEach(function(cb) { cb.resolve(newId); });
      })
      .catch(function(err) {
        _projectRotating = false;
        var cbs = _rotateCallbacks.splice(0);
        cbs.forEach(function(cb) { cb.reject(err); });
      });
  }
  return new Promise(function(resolve, reject) {
    _rotateCallbacks.push({ resolve: resolve, reject: reject });
  });
}
// ─────────────────────────────────────────────────────────────────────────────

function _getToken() {
  return new Promise(function(resolve, reject) {
    var now = Date.now();
    while (_tokenPool.length > 0) {
      var entry = _tokenPool.shift();
      if (now - entry.time < TOKEN_MAX_AGE_MS) {
        console.log("[Imperio] Using pre-fetched token (pool=" + _tokenPool.length + ", age=" + Math.round((now - entry.time) / 1000) + "s)");
        _refillPool();
        resolve(entry.token);
        return;
      }
    }
    _refillPool();
    if (typeof grecaptcha === "undefined" || !grecaptcha.enterprise) {
      reject(new Error("grecaptcha not available"));
      return;
    }
    // Timeout explícito: si ready()+execute() cuelga para siempre (browser flaggeado o sin red),
    // rechazamos a los 30s para que _rcRelease() libere el lock y el siguiente request avance.
    var _done = false;
    var _rcTimer = setTimeout(function() {
      if (!_done) {
        _done = true;
        console.log("[Imperio] execute() sin respuesta en 30s — forzando rechazo para liberar lock");
        reject(new Error("reCAPTCHA execute() timeout (30s forzado)"));
      }
    }, 30000);
    grecaptcha.enterprise.ready(function() {
      if (_done) return;
      console.log("[Imperio] execute() iniciado key=" + SITE_KEY.substring(0, 12) + "...");
      grecaptcha.enterprise.execute(SITE_KEY, {action: RECAPTCHA_ACTION})
        .then(function(t) {
          if (!_done) { _done = true; clearTimeout(_rcTimer); resolve(t); _refillPool(); }
        })
        .catch(function(e) {
          if (!_done) { _done = true; clearTimeout(_rcTimer); reject(e); }
        });
    });
  });
}

function _fetchOneToken() {
  if (typeof grecaptcha === "undefined" || !grecaptcha.enterprise) return;
  if (_tokenFetching >= _maxTokenFetching) return;
  _tokenFetching++;
  grecaptcha.enterprise.ready(function() {
    grecaptcha.enterprise.execute(SITE_KEY, {action: RECAPTCHA_ACTION})
      .then(function(t) {
        _tokenFetching--;
        if (_tokenPool.length < TOKEN_POOL_SIZE) {
          _tokenPool.push({token: t, time: Date.now()});
          console.log("[Imperio] Token pre-fetched (pool=" + _tokenPool.length + ")");
        }
      })
      .catch(function() { _tokenFetching--; });
  });
}

function _refillPool() {
  var needed = TOKEN_POOL_SIZE - _tokenPool.length - _tokenFetching;
  for (var i = 0; i < needed; i++) _fetchOneToken();
}

function _sendBearerToBackground(hash, bearer) {
  if (!hash || !bearer) return;
  window.postMessage({ type: "FLOW_BEARER_UPDATE", hash: hash, bearer: bearer }, "*");
  console.log("[Imperio] Bearer enviado al background para " + hash);
}

// ── Semáforo de reCAPTCHA: garantiza 1 sola llamada execute() a la vez ──────
// El limiter basado en tiempo tenía una race condition cuando 2 mensajes llegaban
// casi juntos y ambos evaluaban _wait=0. El semáforo es atómico en JS (single-thread):
// el segundo request siempre ve _rcLocked=true y queda encolado.
var _RC_GAP_MS  = 3000;      // ms de pausa DESPUÉS de recibir resultado antes del siguiente
var _rcLocked   = false;     // true cuando hay un execute() + API call en curso
var _rcWaiting  = [];        // cola de funciones esperando el lock

function _rcAcquire(fn) {
  if (!_rcLocked) {
    _rcLocked = true;
    console.log("[Imperio] reCAPTCHA lock acquired — cola=" + _rcWaiting.length);
    fn();
  } else {
    console.log("[Imperio] reCAPTCHA encolado (lock ocupado) — cola=" + (_rcWaiting.length + 1));
    _rcWaiting.push(fn);
  }
}

function _rcRelease() {
  setTimeout(function() {
    if (_rcWaiting.length > 0) {
      var next = _rcWaiting.shift();
      console.log("[Imperio] reCAPTCHA lock → siguiente (cola restante=" + _rcWaiting.length + ")");
      next();
    } else {
      _rcLocked = false;
      console.log("[Imperio] reCAPTCHA lock liberado (cola vacía)");
    }
  }, _RC_GAP_MS);
}

function doGenerateRequest(data) {
  // Upload no necesita reCAPTCHA — saltárselo evita el cuelgue de 45s en la primera llamada
  if (data.url && data.url.indexOf('uploadImage') >= 0) {
    console.log("[Imperio] Upload bypass (sin reCAPTCHA) requestId=" + data.requestId);
    try {
      var uploadBody = JSON.parse(data.body);
      var bearerToUse = _currentBearer || data.bearer;
      fetch(data.url, {
        method: "POST",
        credentials: "include",
        headers: { "Content-Type": "application/json", "Authorization": "Bearer " + bearerToUse },
        body: JSON.stringify(uploadBody)
      })
      .then(function(resp) {
        return resp.text().then(function(text) {
          console.log("[Imperio] Upload result status=" + resp.status + " body=" + text.substring(0, 200));
          window.postMessage({ type: "FLOW_GENERATE_RESULT", requestId: data.requestId, status: resp.status, body: text }, "*");
        });
      })
      .catch(function(e) {
        console.log("[Imperio] Upload error: " + e.toString());
        window.postMessage({ type: "FLOW_GENERATE_RESULT", requestId: data.requestId, error: e.toString() }, "*");
      });
    } catch(e) {
      console.log("[Imperio] Upload parse error: " + e.toString());
      window.postMessage({ type: "FLOW_GENERATE_RESULT", requestId: data.requestId, error: e.toString() }, "*");
    }
    return;
  }

  if (typeof grecaptcha === "undefined" || !grecaptcha.enterprise) {
    console.log("[Imperio] grecaptcha NOT available");
    window.postMessage({type: "FLOW_GENERATE_RESULT", requestId: data.requestId, error: "grecaptcha not available"}, "*");
    return;
  }
  console.log("[Imperio] doGenerateRequest requestId=" + data.requestId);

  // Cachear el project ID de la URL original la primera vez que lo vemos
  var originalProjectId = _extractProjectId(data.url);
  if (originalProjectId && !_cachedProjectId) {
    _cachedProjectId = originalProjectId;
  }

  // URL activa (puede cambiar si rotamos proyecto)
  var activeUrl = data.url;

  function _attempt(retriesLeft) {
    // _lockReleased: evita llamar _rcRelease() dos veces si hay error después del token
    var _lockReleased = false;
    function _maybeReleaseLock() {
      if (!_lockReleased) { _lockReleased = true; _rcRelease(); }
    }

    _getToken()
      .then(function(rcToken) {
        // Liberar el lock justo aquí — execute() ya terminó.
        // El API call corre en paralelo con el siguiente execute() de la cola.
        _maybeReleaseLock();
        console.log("[Imperio] reCAPTCHA token obtained, key=" + SITE_KEY.substring(0,12) + "... len=" + rcToken.length);
        var body = JSON.parse(data.body);
        body.clientContext = body.clientContext || {};
        body.clientContext.recaptchaContext = { token: rcToken, applicationType: "RECAPTCHA_APPLICATION_TYPE_WEB" };
        if (body.requests && body.requests.length > 0) {
          body.requests[0].clientContext = body.requests[0].clientContext || {};
          body.requests[0].clientContext.recaptchaContext = { token: rcToken, applicationType: "RECAPTCHA_APPLICATION_TYPE_WEB" };
        }
        var bearerToUse = _currentBearer || data.bearer;
        return fetch(activeUrl, {
          method: "POST",
          credentials: "include",
          headers: { "Content-Type": "application/json", "Authorization": "Bearer " + bearerToUse },
          body: JSON.stringify(body)
        });
      })
      .then(function(resp) {
        return resp.text().then(function(text) {

          // ── 429: rotar proyecto y reintentar (re-encolando con semáforo) ──
          if (resp.status === 429 && retriesLeft > 0) {
            console.log("[Imperio] 429 detectado — rotando proyecto Flow (intentos restantes: " + retriesLeft + ")");
            _rotateProject()
              .then(function(newId) {
                activeUrl = _swapProjectId(data.url, newId);
                console.log("[Imperio] Reintentando con proyecto: " + newId);
                setTimeout(function() { _rcAcquire(function() { _attempt(retriesLeft - 1); }); }, 1500);
              })
              .catch(function(rotateErr) {
                console.log("[Imperio] No se pudo rotar proyecto: " + rotateErr.message + " — devolviendo 429 al launcher");
                window.postMessage({ type: "FLOW_GENERATE_RESULT", requestId: data.requestId, status: 429, body: text }, "*");
              });
            return;
          }
          // ─────────────────────────────────────────────────────────────

          if (resp.status !== 200) {
            console.log("[Imperio] API error status=" + resp.status + " body=" + text.substring(0, 500));
          }
          // Si 403, re-detectar site key por si labs.google lo cambió
          if (resp.status === 403) {
            var newKey = _detectSiteKey();
            if (newKey && newKey !== SITE_KEY) {
              console.log("[Imperio] Actualizando SITE_KEY: " + SITE_KEY + " → " + newKey);
              SITE_KEY = newKey;
              _tokenPool = [];
            }
          }
          window.postMessage({ type: "FLOW_GENERATE_RESULT", requestId: data.requestId, status: resp.status, body: text }, "*");
        });
      })
      .catch(function(e) {
        console.log("[Imperio] Fetch error: " + e.toString());
        // _maybeReleaseLock libera solo si execute() falló antes de obtener el token
        // (si ya se liberó en .then(), esta llamada es no-op)
        _maybeReleaseLock();
        window.postMessage({ type: "FLOW_GENERATE_RESULT", requestId: data.requestId, error: e.toString() }, "*");
      });
  }

  // Encolar con semáforo: garantiza 1 sola llamada execute() + API a la vez
  _rcAcquire(function() { _attempt(3); });
}
// ─────────────────────────────────────────────────────────────────────────────

window.addEventListener("message", function(event) {
  if (event.source !== window) return;
  if (!event.data) return;
  if (event.data.type === "FLOW_GENERATE_REQUEST") doGenerateRequest(event.data);
});

var attempts = 0;
var waitInterval = setInterval(function() {
  attempts++;
  if (typeof grecaptcha !== "undefined" && grecaptcha.enterprise) {
    clearInterval(waitInterval);
    // Re-detectar site key ahora que reCAPTCHA está cargado (podría haberse cargado async)
    var detectedKey = _detectSiteKey();
    if (detectedKey && detectedKey !== SITE_KEY) {
      console.log("[Imperio] reCAPTCHA listo — actualizando SITE_KEY: " + SITE_KEY + " → " + detectedKey);
      SITE_KEY = detectedKey;
      _tokenPool = [];
    } else {
      console.log("[Imperio] grecaptcha ready, SITE_KEY=" + SITE_KEY.substring(0,12) + "... action=" + RECAPTCHA_ACTION);
    }
    _refillPool();
  }
  if (attempts > 120) clearInterval(waitInterval);
}, 500);

function djb2Hash(str) {
  var h = 5381;
  for (var i = 0; i < str.length; i++) { h = ((h << 5) + h + str.charCodeAt(i)) | 0; }
  var hex = (h >>> 0).toString(16);
  while (hex.length < 8) hex = "0" + hex;
  return hex;
}

function _refreshSession() {
  fetch("/fx/api/auth/session", {credentials: "include"})
    .then(function(r) { return r.json(); })
    .then(function(data) {
      var user = data.user || {};
      var identity = user.email || user.name || "";
      var bearer   = data.access_token || "";
      if (identity) {
        var hash = djb2Hash(identity);
        _currentHash   = hash;
        _currentBearer = bearer;
        window.postMessage({type: "FLOW_ACCOUNT_HASH", hash: hash}, "*");
        console.log("[Imperio] Flow account hash: " + hash + " (" + identity + ")");
        if (bearer) _sendBearerToBackground(hash, bearer);
      }
    })
    .catch(function(e) { console.log("[Imperio] Could not get Flow account: " + e.message); });
}

_refreshSession();
setInterval(_refreshSession, 5 * 60 * 1000);
