function extractQwenToken() {
  let token = "";
  try {
    token = localStorage.getItem("token") || "";
  } catch (e) {}
  if (!token) {
    try {
      const keys = Object.keys(localStorage);
      for (const key of keys) {
        const val = localStorage.getItem(key);
        if (val && val.startsWith("eyJ") && val.length > 100) {
          token = val;
          break;
        }
      }
    } catch (e) {}
  }
  return token;
}

const initialToken = extractQwenToken();
if (initialToken) {
  window.postMessage({ type: "IMPERIO_QWEN_TOKEN", token: initialToken }, "*");
}

window.addEventListener("message", (event) => {
  if (event.source !== window) return;
  if (event.data && event.data.type === "IMPERIO_REQUEST_QWEN_TOKEN") {
    const token = extractQwenToken();
    if (token) {
      window.postMessage({ type: "IMPERIO_QWEN_TOKEN", token: token }, "*");
    }
  }
});
