// vibes_bridge.js v5 — hibrido: el prompt se escribe en el editor Lexical real y "Generate"
// se clickea de verdad (DOM), pero la imagen de referencia se sube via las 2 llamadas HTTP
// reales que usa vibes.ai (capturadas de una subida manual), igual que meta_gql_client.py
// hace con rupload.meta.ai para meta.ai -- sin tocar el menu "Ingredients" en absoluto.
//
// Historial: v1 servidor WS/HTTP propio (poco confiable). v2 armaba a mano el payload de
// /api/generation-batches y /api/generate/videos -- no coincidia con lo real y corrompia el
// batch (500 en /batches, /sync). v3 paso a DOM real para texto+generate, con execCommand
// fallando en silencio hasta correr el content script en "world":"MAIN" (ver manifest.json).
// v4 intento adjuntar la imagen via el input[type=file] oculto detras del menu "Ingredients"
// (click Ingredients -> asignar File via DataTransfer) -- fallaba: clickear el boton en cada
// tick de poll abria/cerraba el menu en bucle antes de que el input llegara a montarse. v5
// se salta el DOM para la imagen: sube los bytes directo a POST /api/upload-media
// (multipart/form-data) y registra el resultado con POST /api/projects/{id}/upload (JSON).
(function () {
  var BRIDGE = "http://127.0.0.1:8080";
  var POLL_FAST_MS = 1000;
  var POLL_IDLE_MS = 2500;

  var SEL_EDITOR = 'div[data-lexical-editor="true"][aria-label="Describe a video..."]';
  var SEL_EDITOR_FALLBACK = 'div[data-lexical-editor="true"][role="textbox"]';
  var SEL_GENERATE_BTN = 'button[data-analytics-id="send_message"]';
  var SEL_CREATE_NEW_BTN = 'button[data-analytics-id="create_new_button_click"]';

  var accountHash = "default";
  var pollTimer = null;

  function djb2Hash(str) {
    var h = 5381;
    for (var i = 0; i < str.length; i++) h = ((h << 5) + h + str.charCodeAt(i)) | 0;
    var hex = (h >>> 0).toString(16);
    while (hex.length < 8) hex = "0" + hex;
    return hex;
  }

  function detectAccountHash() {
    var m = document.cookie.match(/(?:^|;\s*)meta_session=([^;]+)/);
    if (m) accountHash = djb2Hash(decodeURIComponent(m[1]));
  }

  function apiFetch(path, opts) {
    opts = opts || {};
    var headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    return fetch("https://vibes.ai" + path, {
      method: opts.method || "GET",
      credentials: "include",
      headers: headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    }).then(function (resp) {
      return resp.text().then(function (text) {
        var data = null;
        try {
          data = text ? JSON.parse(text) : null;
        } catch (e) {}
        return { status: resp.status, ok: resp.ok, data: data, text: text };
      });
    });
  }

  // Poll de una condicion SINCRONA (ej. buscar un elemento en el DOM).
  function waitFor(fn, timeoutMs, intervalMs) {
    intervalMs = intervalMs || 300;
    var deadline = Date.now() + timeoutMs;
    return new Promise(function (resolve, reject) {
      function tick() {
        var v;
        try {
          v = fn();
        } catch (e) {
          v = null;
        }
        if (v) {
          resolve(v);
          return;
        }
        if (Date.now() > deadline) {
          reject(new Error("Timeout esperando condicion en el DOM"));
          return;
        }
        setTimeout(tick, intervalMs);
      }
      tick();
    });
  }

  // Poll de una condicion ASINCRONA (ej. un fetch que devuelve null hasta que este listo).
  function pollAsync(checkFn, deadlineTs, intervalMs) {
    intervalMs = intervalMs || 3000;
    return new Promise(function (resolve, reject) {
      function tick() {
        if (Date.now() > deadlineTs) {
          reject(new Error("Timeout esperando resultado de vibes.ai"));
          return;
        }
        checkFn()
          .then(function (v) {
            if (v) {
              resolve(v);
              return;
            }
            setTimeout(tick, intervalMs);
          })
          .catch(function () {
            setTimeout(tick, intervalMs);
          });
      }
      tick();
    });
  }

  function base64ToBlob(b64, mime) {
    var byteChars = atob(b64);
    var byteNumbers = new Array(byteChars.length);
    for (var i = 0; i < byteChars.length; i++) byteNumbers[i] = byteChars.charCodeAt(i);
    return new Blob([new Uint8Array(byteNumbers)], { type: mime || "image/jpeg" });
  }

  // Subida real de la imagen, reconstruida de una captura de red de una subida manual
  // (igual que se hizo para meta.ai en meta_gql_client.py -- POST directo con los bytes,
  // sin tocar el DOM). Dos pasos:
  //   1) POST /api/upload-media (multipart/form-data, campo "file") -> devuelve
  //      {mediaEntId, cdnUrl, dimensions, aspectRatio, uploadToken}.
  //   2) POST /api/projects/{id}/upload (JSON) con {files:[{...eso mismo, filename}]} --
  //      registra la imagen subida como ingredient del proyecto.
  function uploadMedia(blob, fileName) {
    var fd = new FormData();
    fd.append("file", blob, fileName);
    fd.append("filename", fileName);
    return fetch("https://vibes.ai/api/upload-media", {
      method: "POST",
      credentials: "include",
      body: fd,
    }).then(function (resp) {
      return resp.text().then(function (text) {
        if (!resp.ok) throw new Error("upload-media fallo (" + resp.status + "): " + text.slice(0, 200));
        return JSON.parse(text);
      });
    });
  }

  function registerMediaWithProject(projectId, media, fileName, attempt) {
    attempt = attempt || 1;
    var payload = {
      files: [
        {
          mediaEntId: media.mediaEntId,
          cdnUrl: media.cdnUrl,
          dimensions: media.dimensions,
          aspectRatio: media.aspectRatio,
          uploadToken: media.uploadToken,
          filename: fileName,
        },
      ],
    };
    return apiFetch("/api/projects/" + projectId + "/upload", { method: "POST", body: payload }).then(function (r) {
      if (!r.ok) {
        // El primer upload justo despues de crear el proyecto a veces da 500 (condicion de
        // carrera del lado de vibes.ai, el proyecto aun no esta listo) -- reintentar una vez.
        if (attempt < 3) {
          console.log("[Vibes] paso: projects/upload fallo (" + r.status + "), reintentando en 1.5s...");
          return new Promise(function (resolve) {
            setTimeout(resolve, 1500);
          }).then(function () {
            return registerMediaWithProject(projectId, media, fileName, attempt + 1);
          });
        }
        throw new Error("projects/upload fallo (" + r.status + "): " + r.text.substring(0, 200));
      }
      return media;
    });
  }

  function findButtonByText(text) {
    var btns = document.querySelectorAll("button");
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].textContent.trim() === text) return btns[i];
    }
    return null;
  }

  // element.click() solo dispara el evento "click" -- los triggers de menu de Radix UI (como
  // "Ingredients") escuchan "pointerdown" para abrirse, asi que un .click() normal nunca los
  // abre. Ademas Radix valida pointerType/isPrimary/pointerId/button en el evento -- un
  // PointerEvent sin esos campos (quedan en sus defaults vacios) se ignora en silencio, sin
  // errores ni excepciones, lo que hizo muy dificil de diagnosticar. Confirmado con una prueba
  // manual en consola: con estos campos el panel abre (2 dialogs), sin ellos no abre (0).
  function realClick(el) {
    var rect = el.getBoundingClientRect();
    var x = rect.left + rect.width / 2;
    var y = rect.top + rect.height / 2;
    var base = {
      bubbles: true,
      cancelable: true,
      view: window,
      clientX: x,
      clientY: y,
      pointerId: 1,
      pointerType: "mouse",
      isPrimary: true,
      button: 0,
    };
    ["pointerdown", "mousedown", "pointerup", "mouseup", "click"].forEach(function (type) {
      var Ctor = type.indexOf("pointer") === 0 ? PointerEvent : MouseEvent;
      el.dispatchEvent(new Ctor(type, base));
    });
  }

  // Subir + registrar deja la imagen disponible como media del proyecto, pero NO la agrega
  // a la generacion -- probamos primero con "Ingredients -> Character", pero esa via genera
  // el video IGNORANDO la imagen (solo usa el texto). El video s+i respeta la imagen cuando
  // se adjunta via "Start, end frame -> Add start frame" (usandola solo como start frame,
  // sin end frame), asi que ese es el flujo real.
  function findThumbnailByAlt(altText) {
    var imgs = document.querySelectorAll('img[alt="' + CSS.escape(altText) + '"]');
    return imgs.length ? imgs[imgs.length - 1] : null;
  }

  function selectStartFrame(fileName) {
    var existingThumb = findThumbnailByAlt(fileName);
    var opened;
    if (existingThumb) {
      opened = Promise.resolve();
    } else {
      var startEndBtn = document.querySelector(
        '[data-analytics-id="creation_gallery.start_end_frame_selection_click"]'
      );
      if (!startEndBtn) return Promise.reject(new Error("Boton 'Start, end frame' no encontrado en el DOM"));
      console.log("[Vibes] paso: click en 'Start, end frame'...");
      realClick(startEndBtn);
      opened = new Promise(function (resolve) {
        setTimeout(resolve, 400);
      }).then(function () {
        var addStartBtn = findButtonByText("Add start frame");
        if (!addStartBtn) throw new Error("Boton 'Add start frame' no encontrado");
        console.log("[Vibes] paso: click en 'Add start frame'...");
        realClick(addStartBtn);
        return new Promise(function (resolve) {
          setTimeout(resolve, 500);
        });
      });
    }
    return opened
      .then(function () {
        return waitFor(function () {
          return findThumbnailByAlt(fileName);
        }, 10000, 300);
      })
      .then(function (img) {
        console.log("[Vibes] paso: miniatura encontrada, seleccionandola...");
        var clickTarget = img.closest("button") || img.closest('[role="button"]') || img;
        realClick(clickTarget);
        return waitFor(function () {
          return findButtonByText("Add to video");
        }, 5000, 200);
      })
      .then(function (addBtn) {
        console.log("[Vibes] paso: click en 'Add to video'");
        realClick(addBtn);
      });
  }

  function attachImage(base64, mime, fileName, projectId) {
    console.log("[Vibes] paso: subiendo imagen (upload-media)...");
    var blob = base64ToBlob(base64, mime);
    var actualName = fileName || "reference.jpg";
    return uploadMedia(blob, actualName)
      .then(function (media) {
        console.log("[Vibes] paso: upload-media OK mediaEntId=" + media.mediaEntId + " -- registrando con el proyecto...");
        return registerMediaWithProject(projectId, media, actualName);
      })
      .then(function () {
        console.log("[Vibes] paso: imagen registrada -- asignandola como start frame...");
        return selectStartFrame(actualName);
      })
      .then(function () {
        console.log("[Vibes] paso: imagen agregada como start frame");
      });
  }

  function currentProjectId() {
    var m = location.pathname.match(/\/projects\/([0-9a-fA-F-]{36})/);
    return m ? m[1] : null;
  }

  function findEditor() {
    return document.querySelector(SEL_EDITOR) || document.querySelector(SEL_EDITOR_FALLBACK);
  }

  function ensureProjectViaDom() {
    var existing = currentProjectId();
    if (existing) return Promise.resolve(existing);
    var btn = document.querySelector(SEL_CREATE_NEW_BTN);
    if (!btn) {
      return Promise.reject(
        new Error("No se encontro el boton 'Create new' -- deja esta pestana en https://vibes.ai/projects")
      );
    }
    btn.click();
    return waitFor(currentProjectId, 15000, 300);
  }

  function typePrompt(text) {
    return waitFor(findEditor, 15000, 300).then(function (editor) {
      editor.focus();
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, text);
      return editor;
    });
  }

  function clickGenerate() {
    var logged = false;
    return waitFor(function () {
      var btn = document.querySelector(SEL_GENERATE_BTN);
      if (!logged) {
        logged = true;
        console.log(
          "[Vibes] paso: buscando boton Generate... encontrado:",
          !!btn,
          "| disabled:",
          btn && btn.disabled,
          "| outerHTML:",
          btn && btn.outerHTML.slice(0, 150)
        );
      }
      return btn && !btn.disabled ? btn : null;
    }, 45000, 300).then(function (btn) {
      console.log("[Vibes] paso: click en boton Generate");
      realClick(btn);
    });
  }

  // Busca en un item de content cualquier campo que parezca URL de video ya lista.
  function extractUrl(item) {
    if (!item) return null;
    var candidates = [item.url, item.videoUrl, item.mediaUrl, item.src, item.assetUrl];
    for (var i = 0; i < candidates.length; i++) {
      if (typeof candidates[i] === "string" && candidates[i]) return candidates[i];
    }
    if (item.media && typeof item.media.url === "string") return item.media.url;
    return null;
  }

  function listBatches(projectId) {
    return apiFetch("/api/projects/" + projectId + "/batches?limit=6&offset=0").then(function (r) {
      var batches = (r.data && (r.data.batches || r.data.items || r.data)) || [];
      return Array.isArray(batches) ? batches : [];
    });
  }

  // Escribe el prompt, adjunta la imagen de referencia (si hay) y hace clic en Generate --
  // el "envio" en si. Devuelve el set de ids de batch que YA existian antes del clic, para
  // que quien llama pueda esperar el batch nuevo por su cuenta SIN bloquear el envio del
  // siguiente job/slot (asi varias generaciones corren en paralelo, como en meta.ai: el
  // envio -- que si tiene que ser secuencial, es el mismo compositor -- es rapido; lo lento
  // es la generacion del video en el servidor, y eso no hace falta esperarlo en fila). El
  // texto se escribe DESPUES de adjuntar la imagen porque el flujo de "Start, end frame"
  // (abrir panel, elegir miniatura, Add to video) re-renderiza el compositor y borra lo que
  // ya se hubiera escrito antes.
  function sendOneMessage(projectId, prompt, imageInfo) {
    return listBatches(projectId).then(function (before) {
      var beforeIds = {};
      before.forEach(function (b) {
        if (b && b.id) beforeIds[b.id] = true;
      });
      var attachChain = imageInfo
        ? attachImage(imageInfo.base64, imageInfo.mime, imageInfo.name, projectId)
        : Promise.resolve();
      return attachChain
        .then(function () {
          if (imageInfo) console.log("[Vibes] paso: imagen adjuntada");
          return typePrompt(prompt);
        })
        .then(function () {
          console.log("[Vibes] paso: texto escrito en el editor");
          return clickGenerate();
        })
        .then(function () {
          // Al enviar, el start frame queda pegado en el compositor (con boton "Remove
          // start frame") -- si no lo sacamos, el siguiente job no encuentra "Add start
          // frame" (ya hay uno puesto) y se traba. Lo sacamos apenas se envia el mensaje.
          var removeBtn = document.querySelector('button[aria-label="Remove start frame"]');
          if (removeBtn) {
            console.log("[Vibes] paso: quitando start frame anterior...");
            realClick(removeBtn);
          }
        })
        .then(function () {
          console.log("[Vibes] paso: mensaje enviado, sigue generando en paralelo...");
          return beforeIds;
        });
    });
  }

  // Espera a que aparezca un batch NUEVO (id que no estaba en beforeIds) y que termine
  // (isComplete). Se corre SIN bloquear la cola de envios -- por eso varias de estas pueden
  // estar activas a la vez, una por cada job/slot ya enviado.
  function waitForVideos(projectId, beforeIds, deadlineTs) {
    return pollAsync(
      function () {
        return listBatches(projectId).then(function (batches) {
          var fresh = null;
          for (var i = 0; i < batches.length; i++) {
            if (batches[i] && batches[i].id && !beforeIds[batches[i].id]) {
              fresh = batches[i];
              break;
            }
          }
          if (!fresh) return null;
          if (fresh.isComplete || fresh.is_complete) {
            var urls = (fresh.content || []).map(extractUrl).filter(Boolean);
            if (urls.length > 0) return urls;
          }
          return null;
        });
      },
      deadlineTs,
      3000
    );
  }

  // Cola global que solo serializa el ENVIO (manipulacion de DOM: escribir texto, adjuntar
  // imagen, clickear Generate) entre jobs distintos -- es el unico compositor de la pagina,
  // asi que eso no se puede paralelizar. La espera de cada video (waitForVideos) NO entra en
  // esta cola, as+i el envio del siguiente job no espera a que el anterior termine de generar.
  var sendQueue = Promise.resolve();

  function runGenerate(job) {
    var requestId = job.requestId;
    var slots = job.slots || 1;
    var timeoutMs = (job.timeoutSec || 900) * 1000;
    var deadlineTs = Date.now() + timeoutMs;

    var imageInfo = job.imageBase64 ? { base64: job.imageBase64, mime: job.imageMime, name: job.imageName } : null;

    console.log(
      "[Vibes] Job recibido req=" +
        requestId.slice(0, 8) +
        " slots=" +
        slots +
        (imageInfo ? " img=" + imageInfo.name : " (sin imagen)") +
        " prompt=" +
        (job.prompt || "").slice(0, 60)
    );

    var waiters = [];
    var sent = sendQueue
      .then(function () {
        return ensureProjectViaDom();
      })
      .then(function (projectId) {
        var slotChain = Promise.resolve();
        for (var i = 0; i < slots; i++) {
          slotChain = slotChain.then(function () {
            return sendOneMessage(projectId, job.prompt, imageInfo).then(function (beforeIds) {
              waiters.push(waitForVideos(projectId, beforeIds, deadlineTs));
            });
          });
        }
        return slotChain;
      });

    // Encolar la siguiente entrada de sendQueue ya mismo (no despues de esperar los videos)
    // -- si este job falla al enviar, no trabamos el envio de los que vienen despues.
    sendQueue = sent.catch(function () {});

    sent
      .then(function () {
        return Promise.all(waiters);
      })
      .then(function (results) {
        var allUrls = [];
        results.forEach(function (urls) {
          allUrls = allUrls.concat(urls);
        });
        console.log("[Vibes] Listo req=" + requestId.slice(0, 8) + " " + allUrls.length + " video(s)");
        sendResult({ requestId: requestId, status: 200, videos: allUrls });
      })
      .catch(function (err) {
        console.log("[Vibes] Error generando req=" + requestId.slice(0, 8) + ": " + err.message);
        sendResult({ requestId: requestId, status: 0, error: err.message });
      });
  }

  function sendResult(payload) {
    fetch(BRIDGE + "/api/meta/vibes-result", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
      keepalive: true,
    }).catch(function () {});
  }

  function poll() {
    fetch(BRIDGE + "/api/meta/vibes-poll?account=" + encodeURIComponent(accountHash) + "&max=1")
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        var reqs = data.requests || [];
        reqs.forEach(runGenerate);
        schedulePoll(reqs.length > 0 ? POLL_FAST_MS : POLL_IDLE_MS);
      })
      .catch(function () {
        schedulePoll(POLL_IDLE_MS);
      });
  }

  function schedulePoll(ms) {
    if (pollTimer) clearTimeout(pollTimer);
    pollTimer = setTimeout(poll, ms);
  }

  detectAccountHash();
  setTimeout(function () {
    detectAccountHash();
    poll();
  }, 500);
  setInterval(detectAccountHash, 45000);

  console.log("[Vibes] content script v5 activo (DOM texto/generate + upload-media HTTP) — cuenta " + accountHash);
})();
