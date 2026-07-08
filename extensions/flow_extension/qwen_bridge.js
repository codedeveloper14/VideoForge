window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data && event.data.type === "IMPERIO_QWEN_TOKEN") {
    chrome.runtime.sendMessage({ action: "qwenToken", token: event.data.token });
  }
});

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "requestQwenToken") {
    window.postMessage({ type: "IMPERIO_REQUEST_QWEN_TOKEN" }, "*");
    sendResponse({ ok: true });
  }
  return true;
});
