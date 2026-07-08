const tabs = document.querySelectorAll(".tab"); // empty NodeList — no tabs in new UI
const flowPanel = document.getElementById("flowPanel");
const whiskPanel = document.getElementById("whiskPanel");
const grokPanel = document.getElementById("grokPanel");
const geminiPanel = document.getElementById("geminiPanel");
const qwenPanel = document.getElementById("qwenPanel");

const flowStatusEl = document.getElementById("flowStatus");
const flowCookieBox = document.getElementById("flowCookieBox");
const flowCopyBtn = document.getElementById("flowCopyBtn");
const flowDot = document.getElementById("flowDot");

const whiskStatusEl = document.getElementById("whiskStatus");
const whiskCookieBox = document.getElementById("whiskCookieBox");
const whiskCopyBtn = document.getElementById("whiskCopyBtn");
const whiskDot = document.getElementById("whiskDot");

const grokStatusEl = document.getElementById("grokStatus");
const grokCookieBox = document.getElementById("grokCookieBox");
const grokCopyBtn = document.getElementById("grokCopyBtn");
const grokDot = document.getElementById("grokDot");

const geminiStatusEl = document.getElementById("geminiStatus");
const geminiCookieBox = document.getElementById("geminiCookieBox");
const geminiCopyBtn = document.getElementById("geminiCopyBtn");
const geminiDot = document.getElementById("geminiDot");

const qwenStatusEl = document.getElementById("qwenStatus");
const qwenCookieBox = document.getElementById("qwenCookieBox");
const qwenCopyBtn = document.getElementById("qwenCopyBtn");
const qwenDot = document.getElementById("qwenDot");

const dubvoicePanel = document.getElementById("dubvoicePanel");
const dubvoiceStatusEl = document.getElementById("dubvoiceStatus");
const dubvoiceCookieBox = document.getElementById("dubvoiceCookieBox");
const dubvoiceCopyBtn = document.getElementById("dubvoiceCopyBtn");
const dubvoiceDot = document.getElementById("dubvoiceDot");

let flowCookieString = "";
let whiskCookieString = "";
let grokCookieString = "";
let geminiCookieString = "";
let qwenTokenString = "";
let dubvoiceCookieString = "";
let currentStoreId = null;

// Single-panel UI — switchTab is kept as no-op for compatibility
function switchTab(target) {
  // Only Flow panel is shown; nothing to switch
}

function processFlowCookies(cookies) {
  if (!cookies || cookies.length === 0) {
    flowStatusEl.className = "status error";
    flowStatusEl.textContent =
      "No se encontraron cookies. Inicia sesion en labs.google/fx/tools/flow primero.";
    flowDot.className = "dot red";
    return;
  }

  const cookieNames = cookies.map((c) => c.name);
  const hasSession = cookieNames.some((n) => n.includes("session-token"));

  flowCookieString = cookies.map((c) => c.name + "=" + c.value).join("; ");

  if (!hasSession) {
    flowStatusEl.className = "status error";
    flowStatusEl.textContent =
      "Falta session-token. Inicia sesion en labs.google/fx/tools/flow primero.";
    flowDot.className = "dot yellow";
  } else {
    flowStatusEl.className = "status success";
    flowStatusEl.textContent = cookies.length + " cookies encontradas - OK";
    flowDot.className = "dot green";
  }

  flowCookieBox.style.display = "block";
  flowCookieBox.textContent = flowCookieString.substring(0, 200) + "...";

  flowCopyBtn.disabled = false;
  if (document.getElementById("flowSendBtn")) document.getElementById("flowSendBtn").disabled = false;
}

function processWhiskCookies(cookies) {
  if (!cookies || cookies.length === 0) {
    whiskStatusEl.className = "status error";
    whiskStatusEl.textContent =
      "No se encontraron cookies. Inicia sesion en labs.google/fx/tools/whisk primero.";
    whiskDot.className = "dot red";
    return;
  }

  whiskCookieString = cookies.map((c) => c.name + "=" + c.value).join("; ");

  whiskStatusEl.className = "status success";
  whiskStatusEl.textContent = cookies.length + " cookies encontradas";
  whiskDot.className = "dot green";

  whiskCookieBox.style.display = "block";
  whiskCookieBox.textContent = whiskCookieString.substring(0, 200) + "...";

  whiskCopyBtn.disabled = false;
}

function processGrokCookies(cookies) {
  if (!cookies || cookies.length === 0) {
    grokStatusEl.className = "status error";
    grokStatusEl.textContent =
      "No se encontraron cookies. Inicia sesion en grok.com primero.";
    grokDot.className = "dot red";
    return;
  }

  grokCookieString = cookies.map((c) => c.name + "=" + c.value).join("; ");

  const cookieNames = cookies.map((c) => c.name);
  const hasSso = cookieNames.includes("sso");

  if (!hasSso) {
    grokStatusEl.className = "status error";
    grokStatusEl.textContent =
      "Falta cookie 'sso'. Inicia sesion en grok.com primero.";
    grokDot.className = "dot red";
  } else {
    grokStatusEl.className = "status success";
    grokStatusEl.textContent =
      cookies.length + " cookies capturadas - OK";
    grokDot.className = "dot green";
  }

  grokCookieBox.style.display = "block";
  grokCookieBox.textContent = grokCookieString.substring(0, 200) + "...";

  const hasCfClearance = cookieNames.includes("cf_clearance");
  if (!hasCfClearance) {
    grokStatusEl.className = "status error";
    grokStatusEl.textContent =
      "Falta 'cf_clearance'. Ve a grok.com/imagine, espera que cargue completamente y vuelve a abrir la extension.";
    grokDot.className = "dot red";
    grokCopyBtn.disabled = true;
    return;
  }

  grokCopyBtn.disabled = false;

  var ssoCookie = cookies.find(function(c) { return c.name === "sso"; });
  if (ssoCookie && ssoCookie.value) {
    var h = 5381;
    for (var i = 0; i < ssoCookie.value.length; i++) {
      h = ((h << 5) + h + ssoCookie.value.charCodeAt(i)) & 0xFFFFFFFF;
    }
    var hash = h.toString(16).padStart(8, "0");
    try {
      chrome.storage.local.set({ "grok_account_hash": hash });
    } catch (e) {}
  }
}

function processGeminiCookies(cookies) {
  if (!cookies || cookies.length === 0) {
    geminiStatusEl.className = "status error";
    geminiStatusEl.textContent =
      "No se encontraron cookies. Inicia sesion en gemini.google.com primero.";
    geminiDot.className = "dot red";
    return;
  }

  const cookieMap = {};
  for (const c of cookies) {
    cookieMap[c.name] = c.value;
  }

  const psid = cookieMap["__Secure-1PSID"];
  const psidts = cookieMap["__Secure-1PSIDTS"];

  if (!psid) {
    geminiStatusEl.className = "status error";
    geminiStatusEl.textContent =
      "Falta __Secure-1PSID. Inicia sesion en gemini.google.com primero.";
    geminiDot.className = "dot red";
    return;
  }

  geminiCookieString = cookies.map((c) => c.name + "=" + c.value).join("; ");

  geminiStatusEl.className = "status success";
  geminiStatusEl.textContent = "Cookies de Gemini encontradas - OK";
  geminiDot.className = "dot green";

  geminiCookieBox.style.display = "block";
  geminiCookieBox.textContent = geminiCookieString.substring(0, 200) + "...";

  geminiCopyBtn.disabled = false;
}

function getCookieQuery(base) {
  if (currentStoreId) {
    return Object.assign({}, base, { storeId: currentStoreId });
  }
  return base;
}

function loadFlowCookies() {
  flowStatusEl.className = "status loading";
  flowStatusEl.textContent = "Buscando cookies de Flow...";

  chrome.cookies.getAll(getCookieQuery({ domain: "labs.google" }), (cookies) => {
    if (cookies && cookies.length > 0) {
      processFlowCookies(cookies);
    } else {
      chrome.cookies.getAll(getCookieQuery({ domain: "labs.google.com" }), (cookiesFallback) => {
        processFlowCookies(cookiesFallback);
      });
    }
  });
}

function loadWhiskCookies() {
  whiskStatusEl.className = "status loading";
  whiskStatusEl.textContent = "Buscando cookies de Whisk...";

  chrome.cookies.getAll(getCookieQuery({ domain: "labs.google" }), (cookies) => {
    if (cookies && cookies.length > 0) {
      processWhiskCookies(cookies);
    } else {
      chrome.cookies.getAll(getCookieQuery({ domain: "labs.google.com" }), (cookiesFallback) => {
        processWhiskCookies(cookiesFallback);
      });
    }
  });
}

function loadGrokCookies() {
  grokStatusEl.className = "status loading";
  grokStatusEl.textContent = "Buscando cookies de Grok...";

  const seen = new Set();
  const merged = [];

  function addCookies(cookies) {
    for (const c of (cookies || [])) {
      if (!seen.has(c.name)) {
        seen.add(c.name);
        merged.push(c);
      }
    }
  }

  function finalize() {
    processGrokCookies(merged);
  }

  function tryPartitioned() {
    try {
      chrome.cookies.getAll(
        getCookieQuery({ url: "https://grok.com", partitionKey: { topLevelSite: "https://grok.com" } }),
        (cp1) => {
          addCookies(cp1);
          try {
            chrome.cookies.getAll(
              getCookieQuery({ url: "https://grok.com", partitionKey: {} }),
              (cp2) => {
                addCookies(cp2);
                finalize();
              }
            );
          } catch (e) {
            finalize();
          }
        }
      );
    } catch (e) {
      finalize();
    }
  }

  chrome.cookies.getAll(getCookieQuery({ url: "https://grok.com" }), (c1) => {
    addCookies(c1);
    chrome.cookies.getAll(getCookieQuery({ domain: "grok.com" }), (c2) => {
      addCookies(c2);
      chrome.cookies.getAll(getCookieQuery({ domain: ".grok.com" }), (c3) => {
        addCookies(c3);
        if (!seen.has("cf_clearance")) {
          tryPartitioned();
        } else {
          finalize();
        }
      });
    });
  });
}

function loadGeminiCookies() {
  geminiStatusEl.className = "status loading";
  geminiStatusEl.textContent = "Buscando cookies de Gemini...";

  const seen = new Set();
  const merged = [];

  function addCookies(cookies) {
    for (const c of (cookies || [])) {
      if (!seen.has(c.name)) {
        seen.add(c.name);
        merged.push(c);
      }
    }
  }

  chrome.cookies.getAll(getCookieQuery({ domain: ".google.com" }), (c1) => {
    addCookies(c1);
    chrome.cookies.getAll(getCookieQuery({ url: "https://gemini.google.com" }), (c2) => {
      addCookies(c2);
      chrome.cookies.getAll(getCookieQuery({ domain: "gemini.google.com" }), (c3) => {
        addCookies(c3);
        if (!seen.has("__Secure-1PSID")) {
          chrome.cookies.getAll(getCookieQuery({ url: "https://accounts.google.com" }), (c4) => {
            addCookies(c4);
            chrome.cookies.getAll(getCookieQuery({ domain: "google.com" }), (c5) => {
              addCookies(c5);
              processGeminiCookies(merged);
            });
          });
        } else {
          processGeminiCookies(merged);
        }
      });
    });
  });
}

function processQwenCookies(cookies) {
  if (!cookies || cookies.length === 0) {
    qwenStatusEl.className = "status error";
    qwenStatusEl.textContent = "No se encontraron cookies. Inicia sesion en chat.qwen.ai primero.";
    qwenDot.className = "dot red";
    return;
  }

  let tokenValue = "";
  for (const c of cookies) {
    if (c.name === "token" && c.value && c.value.startsWith("eyJ")) {
      tokenValue = c.value;
      break;
    }
  }

  if (!tokenValue) {
    qwenStatusEl.className = "status error";
    qwenStatusEl.textContent = "No se encontro token JWT. Inicia sesion en chat.qwen.ai primero.";
    qwenDot.className = "dot yellow";
    return;
  }

  qwenTokenString = tokenValue;
  qwenStatusEl.className = "status success";
  qwenStatusEl.textContent = "Token JWT encontrado - OK";
  qwenDot.className = "dot green";

  qwenCookieBox.style.display = "block";
  qwenCookieBox.textContent = tokenValue.substring(0, 50) + "..." + tokenValue.substring(tokenValue.length - 20);

  qwenCopyBtn.disabled = false;
}

function loadQwenCookies() {
  qwenStatusEl.className = "status loading";
  qwenStatusEl.textContent = "Buscando token de Qwen...";

  chrome.tabs.query({ active: true, currentWindow: true }, (activeTabs) => {
    const activeUrl = (activeTabs && activeTabs.length > 0) ? (activeTabs[0].url || "") : "";
    const activeTabId = (activeTabs && activeTabs.length > 0) ? activeTabs[0].id : null;

    if (activeUrl.includes("qwen.ai") && activeTabId) {
      chrome.tabs.sendMessage(activeTabId, { action: "requestQwenToken" }, () => {
        if (chrome.runtime.lastError) {}
      });

      const onMsg = (message) => {
        if (message && message.action === "qwenToken" && message.token) {
          chrome.runtime.onMessage.removeListener(onMsg);
          qwenTokenString = message.token;
          qwenStatusEl.className = "status success";
          qwenStatusEl.textContent = "Token JWT encontrado (localStorage) - OK";
          qwenDot.className = "dot green";
          qwenCookieBox.style.display = "block";
          qwenCookieBox.textContent = message.token.substring(0, 50) + "..." + message.token.substring(message.token.length - 20);
          qwenCopyBtn.disabled = false;
        }
      };
      chrome.runtime.onMessage.addListener(onMsg);

      setTimeout(() => {
        chrome.runtime.onMessage.removeListener(onMsg);
        if (!qwenTokenString) {
          _loadQwenFromCookies();
        }
      }, 1500);
    } else {
      _loadQwenFromCookies();
    }
  });
}

function _loadQwenFromCookies() {
  chrome.cookies.getAll(getCookieQuery({ domain: "chat.qwen.ai" }), (c1) => {
    if (c1 && c1.length > 0) {
      processQwenCookies(c1);
    } else {
      chrome.cookies.getAll(getCookieQuery({ domain: ".qwen.ai" }), (c2) => {
        if (c2 && c2.length > 0) {
          processQwenCookies(c2);
        } else {
          chrome.cookies.getAll(getCookieQuery({ url: "https://chat.qwen.ai" }), (c3) => {
            processQwenCookies(c3);
          });
        }
      });
    }
  });
}

function copyToClipboard(text, btn, label) {
  navigator.clipboard
    .writeText(text)
    .then(() => {
      btn.textContent = "Copiado!";
      btn.className = "copied";
      setTimeout(() => {
        btn.textContent = label;
        btn.className = "primary";
      }, 2000);
    })
    .catch(() => {
      const ta = document.createElement("textarea");
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      document.execCommand("copy");
      document.body.removeChild(ta);
      btn.textContent = "Copiado!";
      btn.className = "copied";
      setTimeout(() => {
        btn.textContent = label;
        btn.className = "primary";
      }, 2000);
    });
}

flowCopyBtn.addEventListener("click", () => {
  if (!flowCookieString) return;
  copyToClipboard(flowCookieString, flowCopyBtn, "Copiar Cookie de Flow");
});

// ── Send to VideoForge ──────────────────────────────────────────────────
const flowSendBtn    = document.getElementById("flowSendBtn");
const flowSendStatus = document.getElementById("flowSendStatus");

function flowEnableButtons() {
  if (flowSendBtn) flowSendBtn.disabled = false;
}

// Hook into processFlowCookies to enable send button
const _origProcessFlow = processFlowCookies;
// We enable it after cookies are loaded
(function patchFlowEnable() {
  const origDot = flowDot;
  // watch for green dot
  const obs = new MutationObserver(() => {
    if (flowDot.className === "dot green" && flowCookieString) {
      flowEnableButtons();
    }
  });
  if (origDot) obs.observe(origDot, { attributes: true });
})();

flowSendBtn && flowSendBtn.addEventListener("click", () => {
  if (!flowCookieString) return;
  flowSendStatus.style.display = "block";
  flowSendStatus.textContent = "Enviando...";
  flowSendStatus.style.color = "#fbbf24";

  // Ask which account slot to use
  const slot = prompt("¿Número de cuenta Flow? (0=primera, 1=segunda, etc.)", "0");
  if (slot === null) { flowSendStatus.style.display = "none"; return; }
  const idx = parseInt(slot) || 0;

  fetch("http://127.0.0.1:8080/api/flow/save-cookie", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ account: idx, cookie: flowCookieString })
  })
  .then(r => r.json())
  .then(d => {
    if (d.ok) {
      flowSendStatus.textContent = "✅ Guardada en VideoForge" + (d.email ? ": " + d.email : "");
      flowSendStatus.style.color = "#22c55e";
    } else {
      flowSendStatus.textContent = "❌ " + (d.error || "Error desconocido");
      flowSendStatus.style.color = "#f87171";
    }
    setTimeout(() => { flowSendStatus.style.display = "none"; }, 4000);
  })
  .catch(e => {
    flowSendStatus.textContent = "❌ No se pudo conectar a VideoForge (¿está corriendo en :8080?)";
    flowSendStatus.style.color = "#f87171";
    setTimeout(() => { flowSendStatus.style.display = "none"; }, 4000);
  });
});

whiskCopyBtn.addEventListener("click", () => {
  if (!whiskCookieString) return;
  copyToClipboard(whiskCookieString, whiskCopyBtn, "Copiar Cookie de Whisk");
});

grokCopyBtn.addEventListener("click", () => {
  if (!grokCookieString) return;
  copyToClipboard(grokCookieString, grokCopyBtn, "Copiar Cookie de Grok");
});

geminiCopyBtn.addEventListener("click", () => {
  if (!geminiCookieString) return;
  copyToClipboard(geminiCookieString, geminiCopyBtn, "Copiar Cookies de Gemini");
});

qwenCopyBtn.addEventListener("click", () => {
  if (!qwenTokenString) return;
  copyToClipboard(qwenTokenString, qwenCopyBtn, "Copiar Token de Qwen");
});

dubvoiceCopyBtn.addEventListener("click", () => {
  if (!dubvoiceCookieString) return;
  copyToClipboard(dubvoiceCookieString, dubvoiceCopyBtn, "Copiar Cookie de DubVoice");
});

function processDubVoiceCookies(cookies) {
  if (!cookies || cookies.length === 0) {
    dubvoiceStatusEl.className = "status error";
    dubvoiceStatusEl.textContent =
      "No se encontraron cookies. Inicia sesion en www.dubvoice.ai primero.";
    dubvoiceDot.className = "dot red";
    return;
  }

  var authCookies = [];
  for (var i = 0; i < cookies.length; i++) {
    var c = cookies[i];
    if (c.name.indexOf("sb-") === 0 && c.name.indexOf("auth-token") !== -1) {
      authCookies.push(c);
    }
  }

  if (authCookies.length === 0) {
    dubvoiceStatusEl.className = "status error";
    dubvoiceStatusEl.textContent =
      "No se encontraron cookies de autenticacion. Inicia sesion en www.dubvoice.ai primero.";
    dubvoiceDot.className = "dot red";
    return;
  }

  authCookies.sort(function(a, b) {
    return a.name.localeCompare(b.name);
  });

  dubvoiceCookieString = authCookies.map(function(c) {
    return c.name + "=" + c.value;
  }).join("; ");

  dubvoiceStatusEl.className = "status success";
  dubvoiceStatusEl.textContent =
    authCookies.length + " cookie(s) de autenticacion encontradas - OK";
  dubvoiceDot.className = "dot green";

  dubvoiceCookieBox.style.display = "block";
  dubvoiceCookieBox.textContent = dubvoiceCookieString.substring(0, 200) + "...";

  dubvoiceCopyBtn.disabled = false;
}

function loadDubVoiceCookies() {
  dubvoiceStatusEl.className = "status loading";
  dubvoiceStatusEl.textContent = "Buscando cookies de DubVoice...";

  var seen = {};
  var merged = [];

  function addCookies(cookies) {
    for (var i = 0; i < (cookies || []).length; i++) {
      var c = cookies[i];
      if (!seen[c.name]) {
        seen[c.name] = true;
        merged.push(c);
      }
    }
  }

  var directNames = [
    "sb-bfdrgcjeksdxhysqktwy-auth-token.0",
    "sb-bfdrgcjeksdxhysqktwy-auth-token.1",
    "sb-bfdrgcjeksdxhysqktwy-auth-token.2",
    "sb-bfdrgcjeksdxhysqktwy-auth-token",
  ];
  var directUrls = [
    "https://www.dubvoice.ai",
    "https://www.dubvoice.ai/en",
    "https://www.dubvoice.ai/en/dashboard",
    "https://dubvoice.ai",
  ];

  function tryDirectGet() {
    var directResults = [];
    var pending = directNames.length * directUrls.length;
    var done = 0;
    for (var ni = 0; ni < directNames.length; ni++) {
      for (var ui = 0; ui < directUrls.length; ui++) {
        (function(name, url) {
          chrome.cookies.get({ url: url, name: name }, function(cookie) {
            if (cookie) directResults.push(cookie);
            done++;
            if (done >= pending) {
              if (directResults.length > 0) {
                processDubVoiceCookies(directResults);
              } else {
                tryLocalStorageFallback();
              }
            }
          });
        })(directNames[ni], directUrls[ui]);
      }
    }
  }

  function tryLocalStorageFallback() {
    chrome.storage.local.get("dubvoice_token_data", function(result) {
      var tokenData = result && result.dubvoice_token_data;
      if (tokenData && tokenData.found && tokenData.cookieString) {
        var parts = tokenData.cookieString.split("=");
        var fakeCookie = { name: parts[0], value: parts.slice(1).join("=") };
        processDubVoiceCookies([fakeCookie]);
      } else {
        chrome.tabs.query({ active: true, currentWindow: true }, function(tabs) {
          if (tabs && tabs.length > 0 && tabs[0].url && tabs[0].url.indexOf("dubvoice.ai") !== -1) {
            chrome.tabs.sendMessage(tabs[0].id, { type: "IMPERIO_DUBVOICE_EXTRACT" }, function() {
              if (chrome.runtime.lastError) {}
            });
            setTimeout(function() {
              chrome.storage.local.get("dubvoice_token_data", function(r2) {
                var td = r2 && r2.dubvoice_token_data;
                if (td && td.found && td.cookieString) {
                  var p = td.cookieString.split("=");
                  var fc = { name: p[0], value: p.slice(1).join("=") };
                  processDubVoiceCookies([fc]);
                } else {
                  processDubVoiceCookies([]);
                }
              });
            }, 1500);
          } else {
            dubvoiceStatusEl.className = "status error";
            dubvoiceStatusEl.textContent = "No se encontraron cookies. Abre www.dubvoice.ai (con sesion iniciada) y vuelve a abrir la extension.";
            dubvoiceDot.className = "dot red";
          }
        });
      }
    });
  }

  var cookieQueries = [
    getCookieQuery({ domain: "dubvoice.ai" }),
    getCookieQuery({ domain: ".dubvoice.ai" }),
    getCookieQuery({ domain: "www.dubvoice.ai" }),
    getCookieQuery({ url: "https://www.dubvoice.ai" }),
    getCookieQuery({ domain: ".bfdrgcjeksdxhysqktwy.supabase.co" }),
    getCookieQuery({ url: "https://bfdrgcjeksdxhysqktwy.supabase.co" }),
    { domain: "dubvoice.ai" },
    { domain: ".dubvoice.ai" },
    { domain: "www.dubvoice.ai" },
    { url: "https://www.dubvoice.ai" },
    { url: "https://www.dubvoice.ai/en/dashboard" },
    { domain: ".bfdrgcjeksdxhysqktwy.supabase.co" },
    { url: "https://bfdrgcjeksdxhysqktwy.supabase.co" },
  ];
  var qi = 0;
  function nextQuery() {
    if (qi >= cookieQueries.length) {
      var hasAuth = false;
      for (var i = 0; i < merged.length; i++) {
        if (merged[i].name.indexOf("sb-") === 0 && merged[i].name.indexOf("auth-token") !== -1) {
          hasAuth = true;
          break;
        }
      }
      if (hasAuth) {
        processDubVoiceCookies(merged);
      } else {
        tryDirectGet();
      }
      return;
    }
    chrome.cookies.getAll(cookieQueries[qi], function(cookies) {
      addCookies(cookies);
      qi++;
      nextQuery();
    });
  }
  nextQuery();
}

chrome.tabs.query({ active: true, currentWindow: true }, (activeTabs) => {
  if (activeTabs && activeTabs.length > 0) {
    const tabId = activeTabs[0].id;
    const url = activeTabs[0].url || "";

    chrome.cookies.getAllCookieStores((stores) => {
      if (stores) {
        for (const store of stores) {
          if (store.tabIds && store.tabIds.includes(tabId)) {
            currentStoreId = store.id;
            break;
          }
        }
      }

      loadFlowCookies();
      loadWhiskCookies();
      loadGrokCookies();
      loadGeminiCookies();
      loadQwenCookies();
      loadDubVoiceCookies();
    });

    if (url.includes("dubvoice.ai")) {
      switchTab("dubvoice");
    } else if (url.includes("qwen.ai")) {
      switchTab("qwen");
    } else if (url.includes("grok.com")) {
      switchTab("grok");
    } else if (url.includes("gemini.google.com")) {
      switchTab("gemini");
    } else if (url.includes("labs.google") && url.includes("flow")) {
      switchTab("flow");
    } else if (url.includes("labs.google")) {
      switchTab("whisk");
    }
  } else {
    loadFlowCookies();
    loadWhiskCookies();
    loadGrokCookies();
    loadGeminiCookies();
    loadQwenCookies();
    loadDubVoiceCookies();
  }
});
