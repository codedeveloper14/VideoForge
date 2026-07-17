// vibes_content.js v1.0 -- relay de generacion de video para Vibes (vibes.ai),
// mismo patron que flow_content.js: background.js ya es generico (dispatch() manda
// {type:"FLOW_GENERATE_REQUEST", requestId, url, bearer, body} a la pestaña
// registrada, sin importar el proveedor), asi que no hace falta tocarlo.
//
// Por que este archivo existe: la generacion via fetch() automatizado (Playwright)
// o via requests puro (Python) siempre devuelve "Generation failed to start" aunque
// la sesion/cookie sea valida -- confirmado en vivo. Con Chrome normal, tipeando,
// genera bien. La diferencia es el browser real: este content script corre DENTRO
// de esa misma pestaña real (con la extension cargada), asi que el fetch() sale con
// el fingerprint real del browser, no el de una automatizacion.

var VIBES_ACCOUNT_HASH = "vibes-default";
var _registerPending = false;

function registerWithBackground() {
  if (_registerPending) return;
  _registerPending = true;
  try {
    chrome.runtime.sendMessage({ type: "REGISTER_ACCOUNT", accountHash: VIBES_ACCOUNT_HASH }, function (resp) {
      _registerPending = false;
      if (chrome.runtime.lastError) {
        setTimeout(registerWithBackground, 3000);
        return;
      }
      console.log("[Imperio Vibes] Registered OK — " + VIBES_ACCOUNT_HASH);
    });
  } catch (e) {
    _registerPending = false;
    setTimeout(registerWithBackground, 3000);
  }
}

registerWithBackground();
// Re-registrar periodicamente -- mismo patron que flow_content.js, cubre el caso de
// que el service worker se haya suspendido (MV3) y perdido el registro en memoria.
setInterval(registerWithBackground, 45000);

function _sendResult(requestId, status, body, error) {
  try {
    chrome.runtime.sendMessage({ type: "FLOW_RESULT", requestId: requestId, status: status || 0, body: body || "", error: error || "" });
  } catch (e) {}
}

// Parsea un bloque SSE completo (varias lineas "data:") a un objeto. Formato real
// confirmado: {"success":true,"isComplete":true,"items":[{videoUrl,imageUrl,error},...]}
function _parseSseBlock(block) {
  var lines = block.split("\n").filter(function (l) { return l.indexOf("data:") === 0; });
  if (!lines.length) return null;
  var raw = lines.map(function (l) { return l.slice(5).trim(); }).join("\n");
  try {
    return JSON.parse(raw);
  } catch (e) {
    return null;
  }
}

async function handleGenerateRequest(data) {
  var requestId = data.requestId;
  try {
    var createResp = await fetch(data.url, {
      method: "POST",
      headers: { "content-type": "application/json" },
      credentials: "include",
      body: data.body,
    });
    var createText = await createResp.text();
    if (!createResp.ok) {
      console.log("[Imperio Vibes] creacion fallo HTTP " + createResp.status + ": " + createText.slice(0, 200));
      _sendResult(requestId, createResp.status, createText, "create_failed");
      return;
    }

    var reqBody;
    try {
      reqBody = JSON.parse(data.body);
    } catch (e) {
      _sendResult(requestId, 0, "", "body_parse_error: " + e.message);
      return;
    }
    var batchId = reqBody.id;
    var streamUrl = data.url + "/" + batchId + "/stream";
    console.log("[Imperio Vibes] batch creado " + batchId + " -- escuchando stream...");

    var streamResp = await fetch(streamUrl, {
      headers: { accept: "text/event-stream" },
      credentials: "include",
    });
    if (!streamResp.ok) {
      var streamErrText = await streamResp.text();
      _sendResult(requestId, streamResp.status, streamErrText, "stream_failed");
      return;
    }

    var reader = streamResp.body.getReader();
    var decoder = new TextDecoder();
    var buf = "";
    var deadline = Date.now() + 300000;
    var finalEvent = null;

    while (Date.now() < deadline) {
      var chunk = await reader.read();
      if (chunk.done) break;
      buf += decoder.decode(chunk.value, { stream: true });
      var blocks = buf.split("\n\n");
      buf = blocks.pop();
      for (var i = 0; i < blocks.length; i++) {
        var evt = _parseSseBlock(blocks[i]);
        if (evt && evt.isComplete === true) {
          finalEvent = evt;
          break;
        }
      }
      if (finalEvent) break;
    }
    try {
      reader.cancel();
    } catch (e) {}

    if (finalEvent) {
      console.log("[Imperio Vibes] [OK] isComplete=true, " + (finalEvent.items || []).length + " item(s)");
      _sendResult(requestId, 200, JSON.stringify(finalEvent), "");
    } else {
      _sendResult(requestId, 0, "", "timeout esperando isComplete=true");
    }
  } catch (e) {
    console.log("[Imperio Vibes] excepcion: " + e.toString());
    _sendResult(requestId, 0, "", e.toString());
  }
}

// Sube una imagen de referencia via POST multipart/form-data (data.url =
// /api/upload-media). data.body es JSON {filename, dataB64} -- el binario viaja
// en base64 porque el protocolo del bridge (WS/HTTP poll) solo lleva strings; se
// reconstruye a Blob aca adentro, en la pestaña real, antes del fetch. Igual
// motivo que handleGenerateRequest: un upload automatizado sin browser real puede
// ser rechazado, asi que corre dentro de esta pestaña con la extension cargada.
async function handleUploadRequest(data) {
  var requestId = data.requestId;
  try {
    var parsed = JSON.parse(data.body);
    var filename = parsed.filename || "reference.jpg";
    var byteChars = atob(parsed.dataB64);
    var bytes = new Uint8Array(byteChars.length);
    for (var i = 0; i < byteChars.length; i++) bytes[i] = byteChars.charCodeAt(i);
    var blob = new Blob([bytes]);

    var form = new FormData();
    form.append("file", blob, filename);
    form.append("filename", filename);

    var resp = await fetch(data.url, { method: "POST", credentials: "include", body: form });
    var text = await resp.text();
    if (!resp.ok) {
      console.log("[Imperio Vibes] upload-media fallo HTTP " + resp.status + ": " + text.slice(0, 200));
      _sendResult(requestId, resp.status, text, "upload_failed");
      return;
    }
    console.log("[Imperio Vibes] [OK] imagen de referencia subida");
    _sendResult(requestId, 200, text, "");
  } catch (e) {
    console.log("[Imperio Vibes] upload excepcion: " + e.toString());
    _sendResult(requestId, 0, "", e.toString());
  }
}

chrome.runtime.onMessage.addListener(function (msg, sender, sendResponse) {
  if (!msg || msg.type !== "FLOW_GENERATE_REQUEST") return;
  if (msg.kind === "upload_media") {
    handleUploadRequest(msg);
  } else {
    handleGenerateRequest(msg);
  }
  sendResponse({ ok: true });
  return true;
});

console.log("[Imperio Vibes] vibes_content.js v1.1 cargado");
