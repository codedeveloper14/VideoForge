var BRIDGE_BASE = "http://localhost:5001";
var POLL_INTERVAL = 3000;
var IDLE_POLL_INTERVAL = 10000;
var _accountHash = null;
var _bridgeActive = false;

function generateNonce() {
  var chars = "abcdefghijklmnopqrstuvwxyz0123456789";
  var result = "";
  for (var i = 0; i < 16; i++) {
    result += chars.charAt(Math.floor(Math.random() * chars.length));
  }
  return result;
}

function getAccountHashFromPage() {
  return new Promise(function(resolve) {
    var nonce = generateNonce();
    var timeout = setTimeout(function() {
      window.removeEventListener("message", handler);
      resolve(null);
    }, 5000);

    function handler(event) {
      if (event.source !== window) return;
      if (event.data && event.data.type === "IMPERIO_GROK_ACCOUNT_HASH" && event.data.nonce === nonce) {
        window.removeEventListener("message", handler);
        clearTimeout(timeout);
        resolve(event.data.hash);
      }
    }

    window.addEventListener("message", handler);
    window.postMessage({ type: "IMPERIO_GROK_GET_ACCOUNT", nonce: nonce }, "*");
  });
}

async function checkBridgeServer() {
  try {
    var resp = await fetch(BRIDGE_BASE + "/api/grok-bridge/ping", {
      method: "GET",
    });
    return resp.ok;
  } catch (e) {
    return false;
  }
}

async function pollForUploads() {
  if (!_accountHash) return;

  try {
    var resp = await fetch(
      BRIDGE_BASE + "/api/grok-bridge/poll?account=" + encodeURIComponent(_accountHash),
      { method: "GET" }
    );
    if (!resp.ok) return;

    var data = await resp.json();
    if (!data.pending) return;

    var requestId = data.request_id;
    var payload = data.payload;
    var nonce = generateNonce();

    var resultPromise = new Promise(function(resolve) {
      var timeout = setTimeout(function() {
        window.removeEventListener("message", handler);
        resolve({ success: false, data: { error: "Upload timeout in browser (90s)" } });
      }, 90000);

      function handler(event) {
        if (event.source !== window) return;
        if (event.data && event.data.type === "IMPERIO_GROK_UPLOAD_RESPONSE" &&
            event.data.requestId === requestId && event.data.nonce === nonce) {
          window.removeEventListener("message", handler);
          clearTimeout(timeout);
          resolve({ success: event.data.success, data: event.data.data, status: event.data.status });
        }
      }

      window.addEventListener("message", handler);
    });

    window.postMessage({
      type: "IMPERIO_GROK_UPLOAD_REQUEST",
      requestId: requestId,
      payload: payload,
      nonce: nonce,
    }, "*");

    var result = await resultPromise;

    await fetch(BRIDGE_BASE + "/api/grok-bridge/result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        request_id: requestId,
        account_hash: _accountHash,
        success: result.success,
        result: result.data,
      }),
    });

  } catch (e) {
    // bridge server not available
  }
}

function getAccountHashFromStorage() {
  return new Promise(function(resolve) {
    try {
      chrome.storage.local.get("grok_account_hash", function(data) {
        if (chrome.runtime.lastError || !data || !data.grok_account_hash) {
          resolve(null);
          return;
        }
        resolve(data.grok_account_hash);
      });
    } catch (e) {
      resolve(null);
    }
  });
}

async function startPolling() {
  _accountHash = await getAccountHashFromPage();
  if (!_accountHash) {
    _accountHash = await getAccountHashFromStorage();
  }
  if (!_accountHash) {
    setTimeout(startPolling, IDLE_POLL_INTERVAL);
    return;
  }

  _bridgeActive = await checkBridgeServer();
  if (!_bridgeActive) {
    setTimeout(function() {
      _bridgeActive = false;
      startPolling();
    }, IDLE_POLL_INTERVAL);
    return;
  }

  async function loop() {
    await pollForUploads();
    setTimeout(loop, POLL_INTERVAL);
  }
  loop();
}

setTimeout(startPolling, 2000);
