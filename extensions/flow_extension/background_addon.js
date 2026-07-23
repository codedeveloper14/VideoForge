// background_addon.js - agregar al background.js de la extension Imperio
// Maneja el registro de bearers y los envia al bridge

var BRIDGE_URL = "http://localhost:5556";

// Escuchar mensajes de los content scripts
chrome.runtime.onMessage.addListener(function(msg, sender, sendResponse) {
  if (!msg) return;

  // Cuando el content script envia REGISTER_ACCOUNT con bearer
  if (msg.type === "REGISTER_ACCOUNT" && msg.bearer) {
    // Enviar bearer al bridge — el background NO tiene restricciones CORS para localhost
    fetch(BRIDGE_URL + "/flow-register-bearer", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({account: msg.accountHash, bearer: msg.bearer})
    }).catch(function() {});
    // No interferir con el handler existente de REGISTER_ACCOUNT
  }
});
