window.addEventListener("message", async function(event) {
  if (event.source !== window) return;
  if (!event.data || event.data.type !== "IMPERIO_GROK_UPLOAD_REQUEST") return;

  var requestId = event.data.requestId;
  var payload = event.data.payload;
  var nonce = event.data.nonce || "";

  try {
    var response = await fetch("/rest/app-chat/upload-file", {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    var status = response.status;
    var data = null;
    try {
      data = await response.json();
    } catch (e) {
      data = { error: await response.text() };
    }

    window.postMessage({
      type: "IMPERIO_GROK_UPLOAD_RESPONSE",
      requestId: requestId,
      nonce: nonce,
      success: status === 200,
      status: status,
      data: data,
    }, "*");
  } catch (error) {
    window.postMessage({
      type: "IMPERIO_GROK_UPLOAD_RESPONSE",
      requestId: requestId,
      nonce: nonce,
      success: false,
      status: 0,
      data: { error: error.message },
    }, "*");
  }
});

window.addEventListener("message", function(event) {
  if (event.source !== window) return;
  if (!event.data || event.data.type !== "IMPERIO_GROK_GET_ACCOUNT") return;

  var nonce = event.data.nonce || "";
  var cookies = document.cookie.split(";");
  var ssoValue = "";
  for (var i = 0; i < cookies.length; i++) {
    var c = cookies[i].trim();
    if (c.indexOf("sso=") === 0) {
      ssoValue = c.substring(4);
      break;
    }
  }

  if (ssoValue) {
    var h = 5381;
    for (var j = 0; j < ssoValue.length; j++) {
      h = ((h << 5) + h + ssoValue.charCodeAt(j)) & 0xFFFFFFFF;
    }
    window.postMessage({
      type: "IMPERIO_GROK_ACCOUNT_HASH",
      nonce: nonce,
      hash: h.toString(16).padStart(8, "0"),
    }, "*");
  } else {
    window.postMessage({
      type: "IMPERIO_GROK_ACCOUNT_HASH",
      nonce: nonce,
      hash: null,
    }, "*");
  }
});
