// vibes_relay.js v2 -- contraparte ISOLATED de vibes_bridge.js (que corre en
// "world":"MAIN", sin privilegios de extension). v1 hacia el fetch() al bridge
// Python (127.0.0.1:8080) directo desde aca, pero Chrome lo bloquea igual con
// "Permission was denied for this request to access the `loopback` address
// space" (Local Network Access) -- confirmado en vivo (2026-07-20): esa
// restriccion se aplica por pestaña/pagina publica, no por "world" de content
// script, asi que ISOLATED no alcanza. El fetch real ahora vive en background.js
// (unico contexto exento) -- este archivo es solo un relay de mensajes en las
// dos puntas: window.postMessage <-> vibes_bridge.js (MAIN, dueño del DOM real),
// chrome.runtime <-> background.js (dueño del fetch real al bridge).
(function () {
  function register() {
    try { chrome.runtime.sendMessage({ type: "VIBES_REGISTER_TAB" }); } catch (e) {}
  }

  // Jobs entrantes desde background.js -- se reenvian a la pagina real (MAIN
  // world) porque solo vibes_bridge.js tiene acceso al DOM del compositor.
  chrome.runtime.onMessage.addListener(function (msg) {
    if (!msg || msg.type !== "VIBES_JOB") return;
    window.postMessage({ __vibesRelay: true, type: "VIBES_JOB", job: msg.job }, "*");
  });

  // Resultados salientes desde la pagina -- se reenvian a background.js, que es
  // quien realmente hace el POST al bridge (ver nota de arriba).
  window.addEventListener("message", function (event) {
    if (event.source !== window) return;
    var data = event.data;
    if (!data || data.__vibesRelay !== true || data.type !== "VIBES_RESULT") return;
    try { chrome.runtime.sendMessage({ type: "VIBES_RESULT", payload: data.payload }); } catch (e) {}
  });

  register();
  // Re-registrar periodicamente -- mismo patron que flow_content.js, cubre el caso
  // de que el service worker se haya suspendido (MV3) y perdido el registro.
  setInterval(register, 45000);

  console.log("[Vibes] relay v2 activo (isolated -- relay hacia background.js, que hace el fetch real por Local Network Access)");
})();
