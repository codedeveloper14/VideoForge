(function() {
  function extractSupabaseToken() {
    var result = { found: false, cookieString: "" };
    try {
      for (var i = 0; i < localStorage.length; i++) {
        var key = localStorage.key(i);
        if (key && key.indexOf("sb-") === 0 && key.indexOf("auth-token") !== -1) {
          var raw = localStorage.getItem(key);
          if (raw) {
            result.found = true;
            result.cookieString = key + "=" + raw;
            break;
          }
        }
      }
    } catch(e) {}
    return result;
  }

  window.addEventListener("message", function(event) {
    if (event.source !== window) return;
    if (event.data && event.data.type === "IMPERIO_DUBVOICE_REQUEST") {
      var data = extractSupabaseToken();
      window.postMessage({ type: "IMPERIO_DUBVOICE_RESPONSE", data: data }, "*");
    }
  });
})();
