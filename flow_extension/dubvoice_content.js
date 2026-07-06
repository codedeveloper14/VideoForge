(function() {
  window.addEventListener("message", function(event) {
    if (event.source !== window) return;
    if (event.data && event.data.type === "IMPERIO_DUBVOICE_RESPONSE") {
      chrome.storage.local.set({ dubvoice_token_data: event.data.data });
    }
  });

  window.postMessage({ type: "IMPERIO_DUBVOICE_REQUEST" }, "*");
})();
