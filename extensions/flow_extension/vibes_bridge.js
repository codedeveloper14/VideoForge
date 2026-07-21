// vibes_bridge.js v6 — hibrido: el prompt se escribe en el editor Lexical real y "Generate"
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
//
// v6: el polling al bridge Python (http://127.0.0.1:8080) se movio a vibes_relay.js
// (content script ISOLATED, ver manifest.json) -- este archivo corre en "world":"MAIN"
// (necesario para que execCommand dispare los listeners de React del editor Lexical, ver
// nota v3 arriba), pero MAIN world es indistinguible del script de la propia pagina: sin
// chrome.* y sin el bypass de CORS que da host_permissions, asi que sus fetch() a un
// origen distinto (el bridge) quedaban sujetos a las mismas restricciones de red que
// cualquier pagina -- por eso la extension nunca llegaba a registrarse como "conectada"
// (confirmado: connected_accounts() en el backend nunca se poblaba). vibes_relay.js SI
// tiene ese privilegio (mismo patron que flow_content.js/qwen_bridge.js/grok_bridge.js
// para sus proveedores) y hace el poll/post real; los jobs/resultados van y vuelven de
// este archivo via window.postMessage.
(function () {
  var SEL_EDITOR = 'div[data-lexical-editor="true"][aria-label="Describe a video..."]';
  var SEL_EDITOR_FALLBACK = 'div[data-lexical-editor="true"][role="textbox"]';
  var SEL_GENERATE_BTN = 'button[data-analytics-id="send_message"]';
  var SEL_CREATE_NEW_BTN = 'button[data-analytics-id="create_new_button_click"]';

  function apiFetch(path, opts) {
    opts = opts || {};
    var headers = Object.assign({ "Content-Type": "application/json" }, opts.headers || {});
    // location.origin, no "https://vibes.ai" fijo -- la cookie de sesion de vibes.ai
    // esta verificada como correcta solo en el dominio donde se hizo login (ver
    // vibes_client.py BASE_URL/comentario); fijar un origin distinto al de esta
    // pestaña mandaria el fetch cross-origin, sin esa cookie.
    return fetch(location.origin + path, {
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

  // Log UNA sola vez por nombre (no en cada tick de waitFor, que llama al finder
  // cada 100-150ms y saturaria la consola) -- asi la prueba en vivo deja evidencia
  // clara de si el selector primario matcheo o si tuvo que caer al fallback.
  var _loggedFallbacks = {};
  function _logFallbackOnce(name) {
    if (_loggedFallbacks[name]) return;
    _loggedFallbacks[name] = true;
    console.log("[Vibes] FALLBACK usado para '" + name + "' -- el selector primario no matcheo.");
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
  // vibes.ai tambien da 500 esporadicos en este paso bajo su propia carga (misma
  // causa que el 500 que ya se reintenta un paso mas adelante en
  // registerMediaWithProject) -- sin este reintento, el paso 1 quedaba como el
  // unico eslabon de la subida sin cubrir, pese a ser tan propenso a fallar como
  // el paso 2. blob es un Blob inmutable: reusarlo en un FormData nuevo por cada
  // intento es seguro, no se "consume" al adjuntarlo.
  function uploadMedia(blob, fileName, attempt) {
    attempt = attempt || 1;
    var fd = new FormData();
    fd.append("file", blob, fileName);
    fd.append("filename", fileName);
    // location.origin, no "https://vibes.ai" fijo -- mismo bug que ya se corrigio en
    // apiFetch() (ver su comentario): la pestaña real corre en www.vibes.ai, y un
    // fetch a un subdominio distinto es cross-origin de verdad -- vibes.ai no manda
    // Access-Control-Allow-Origin para eso (no espera que se lo llame cross-origin),
    // asi que el browser lo bloquea antes de que salga. Confirmado en vivo
    // (2026-07-20): "blocked by CORS policy: No 'Access-Control-Allow-Origin' header
    // is present" + net::ERR_FAILED en POST /api/upload-media.
    return fetch(location.origin + "/api/upload-media", {
      method: "POST",
      credentials: "include",
      body: fd,
    }).then(function (resp) {
      return resp.text().then(function (text) {
        if (!resp.ok) {
          if (attempt < 3) {
            console.log("[Vibes] paso: upload-media fallo (" + resp.status + "), reintentando en 1.5s...");
            return new Promise(function (resolve) {
              setTimeout(resolve, 1500);
            }).then(function () {
              return uploadMedia(blob, fileName, attempt + 1);
            });
          }
          throw new Error("upload-media fallo (" + resp.status + "): " + text.slice(0, 200));
        }
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

  // Texto EXACTO -- usar solo para textos que se confirmaron estables (ej. "Start, end
  // frame"/"Add start frame", que quedaron en ingles incluso con la cuenta en español,
  // ver findAddToVideoButton mas abajo para el caso contrario).
  function findButtonByText(text) {
    var btns = document.querySelectorAll("button");
    for (var i = 0; i < btns.length; i++) {
      if (btns[i].textContent.trim() === text) return btns[i];
    }
    return null;
  }

  // Texto por REGEX -- Vibes traduce la UI de forma inconsistente segun idioma de cuenta/
  // sesion (confirmado en vivo, 2026-07-21: la misma pantalla mostro "Add to video" en una
  // sesion y "Añadir al vídeo" en otra) -- un match exacto en ingles se rompe silenciosamente
  // para cualquier cuenta en español. Se busca por regex (ambos idiomas) dentro de `scope`
  // (el dialog de "Select start frame" si se tiene, para no matchear otro boton de la pagina).
  function findButtonByPattern(re, scope) {
    var btns = (scope || document).querySelectorAll("button");
    for (var i = 0; i < btns.length; i++) {
      if (re.test(btns[i].textContent.trim())) return btns[i];
    }
    return null;
  }

  // El boton "Add to video"/"Añadir al vídeo" es el CTA relleno de azul (bg_var(--fill-blue))
  // del dialog "Select start frame" -- selector primario independiente del idioma; el regex es
  // solo fallback por si Vibes cambia esa clase.
  function findAddToVideoButton(scope) {
    var root = scope || document;
    return (
      root.querySelector('button[class*="bg_var(--fill-blue)"]') ||
      findButtonByPattern(/add to video|a[ñn]adir al v[ií]deo/i, root)
    );
  }

  // "Add start frame" -- a diferencia de "Add to video" (arriba), NO tenemos una
  // traduccion al español confirmada en vivo para este boton especifico (el
  // comentario historico en selectStartFrame asumia que quedaba fijo en ingles,
  // pero esa hipotesis nunca se puso a prueba con una cuenta que lo mostrara
  // traducido). El regex de abajo es un fallback de MEJOR ESFUERZO, no un hecho
  // verificado como el de findAddToVideoButton -- si en algun momento se confirma
  // el texto real en español, reemplazar el patron por el string exacto.
  function findAddStartFrameButton(scope) {
    var primary = findButtonByText("Add start frame");
    if (primary) return primary;
    var fallback = findButtonByPattern(/add start frame|a[ñn]adir fotograma de inicio|agregar fotograma de inicio/i, scope);
    if (fallback) _logFallbackOnce("Add start frame");
    return fallback;
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
  //
  // El alt de la miniatura en ESTE dialog ("Select start frame", el que abre "Add start
  // frame") SI es el filename subido -- confirmado en vivo con prueba end-to-end real
  // (2026-07-21). Ojo: en el panel de galeria del costado (creation_gallery, otro
  // componente) el alt es el NOMBRE DEL PROYECTO, no el filename -- por eso una inspeccion
  // anterior contra el panel equivocado concluyo lo opuesto. Cada dialog de Vibes tiene su
  // propia convencion, no asumir que es la misma en toda la app.
  function findOpenDialog() {
    return document.querySelector('[role="dialog"]') || document.querySelector('[role="alertdialog"]');
  }

  // `scope` opcional -- SIN el, esto busca en toda la pagina, lo que es un riesgo real: si
  // el mismo filename quedo visible en cualquier otro lugar (panel de galeria, un dialog de
  // una imagen distinta, estado de React viejo de un intento anterior sin recargar la
  // pestaña), el atajo "existingThumb" de selectStartFrame lo toma como ya seleccionado y
  // SALTA por completo abrir "Start, end frame" -- sin el dialog abierto, "Add to video"
  // nunca aparece y el timeout es indistinguible del bug original. Por eso ahora todo el
  // matching de miniatura en selectStartFrame se limita al dialog "Select start frame" que
  // esta REALMENTE abierto en ese momento.
  function findThumbnailByAlt(altText, scope) {
    var imgs = (scope || document).querySelectorAll('img[alt="' + CSS.escape(altText) + '"]');
    return imgs.length ? imgs[imgs.length - 1] : null;
  }

  function selectStartFrame(fileName) {
    var openDialog = findOpenDialog();
    var existingThumb = openDialog ? findThumbnailByAlt(fileName, openDialog) : null;
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
      // Sin espera fija a ciegas -- se poll directo por "Add start frame" apenas aparece
      // (Radix suele montarlo en unas pocas decenas de ms, no hace falta esperar 400-900ms).
      // findAddStartFrameButton() intenta el texto exacto en ingles primero y cae a un
      // regex bilingue si no matchea (ver su comentario -- el español no esta confirmado
      // en vivo para este boton, es defensivo).
      opened = waitFor(function () {
        return findAddStartFrameButton();
      }, 8000, 100).then(function (addStartBtn) {
        console.log("[Vibes] paso: click en 'Add start frame'...");
        realClick(addStartBtn);
      });
    }
    return opened
      .then(function () {
        return waitFor(function () {
          var dlg = findOpenDialog();
          return dlg ? findThumbnailByAlt(fileName, dlg) : null;
        }, 10000, 120);
      })
      .then(function (img) {
        console.log("[Vibes] paso: miniatura encontrada, seleccionandola...");
        // Sin wrapper button/[role=button] en este dialog (confirmado en vivo) -- el click
        // real tiene que caer sobre el <img> mismo, closest() siempre da null aca y con el
        // fallback "|| img" alcanza.
        var clickTarget = img.closest("button") || img.closest('[role="button"]') || img;
        realClick(clickTarget);
        // Escopado al dialog de este img (Radix Dialog.Content) -- evita matchear por
        // error algun otro boton azul de la pagina si el dialog no se detecta, cae a
        // document entero (findAddToVideoButton ya maneja el fallback).
        var dialogScope = img.closest('[role="dialog"]') || img.closest('[role="alertdialog"]');
        return waitFor(function () {
          var btn = findAddToVideoButton(dialogScope);
          return btn && !btn.disabled ? btn : null;
        }, 5000, 120);
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

  // SEL_CREATE_NEW_BTN depende de un solo data-analytics-id (telemetria interna de
  // Vibes, no un contrato estable) -- sin fallback, un cambio de ese atributo tira
  // un error inmediato sin reintento (ensureProjectViaDom corre antes de cualquier
  // cola). El regex es de MEJOR ESFUERZO, no confirmado en vivo como findAddToVideoButton.
  function findCreateNewButton() {
    var primary = document.querySelector(SEL_CREATE_NEW_BTN);
    if (primary) return primary;
    var fallback = findButtonByPattern(/create new|new project|\+\s*new|nuevo proyecto|crear nuevo/i);
    if (fallback) _logFallbackOnce("Create new");
    return fallback;
  }

  function ensureProjectViaDom() {
    var existing = currentProjectId();
    if (existing) return Promise.resolve(existing);
    var btn = findCreateNewButton();
    if (!btn) {
      return Promise.reject(
        new Error("No se encontro el boton 'Create new' -- deja esta pestana en https://vibes.ai/projects")
      );
    }
    btn.click();
    return waitFor(currentProjectId, 15000, 150);
  }

  function typePrompt(text) {
    return waitFor(findEditor, 15000, 120).then(function (editor) {
      editor.focus();
      document.execCommand("selectAll", false, null);
      document.execCommand("insertText", false, text);
      return editor;
    });
  }

  // Mismo riesgo que findCreateNewButton, agravado porque clickGenerate espera hasta
  // 45s (el timeout mas largo del archivo) antes de rendirse si el selector deja de
  // matchear. El boton real es un icono sin texto visible -- findButtonByText/Pattern
  // no sirven aca, el fallback es por aria-label. MEJOR ESFUERZO, no confirmado en vivo.
  function findGenerateButton() {
    var primary = document.querySelector(SEL_GENERATE_BTN);
    if (primary) return primary;
    var fallback =
      document.querySelector('button[aria-label="Send message" i]') ||
      document.querySelector(
        'button[aria-label*="generat" i], button[aria-label*="enviar" i], button[aria-label*="generar" i]'
      );
    if (fallback) _logFallbackOnce("Generate");
    return fallback;
  }

  function clickGenerate() {
    var logged = false;
    return waitFor(function () {
      var btn = findGenerateButton();
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
    }, 45000, 150).then(function (btn) {
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

  // Varios jobs en paralelo comparten el MISMO projectId (un solo compositor), asi que sin
  // deduplicar, N jobs esperando en simultaneo generan N fetches identicos por tick de poll --
  // eso satura /batches y contribuye a los 500 que devuelve vibes.ai bajo carga. Cacheamos por
  // un instante corto (bien por debajo del intervalo de poll de 3000ms) para que todos los
  // waiters activos reusen la misma peticion en vuelo en vez de disparar la suya propia.
  var BATCHES_CACHE_MS = 1200;
  var batchesCache = {};

  // vibes.ai devuelve 500 en /batches con mucha frecuencia bajo su propia carga (no es
  // culpa nuestra, confirmado revisando la consola manualmente) -- sin reintento, un solo
  // 500 tira la respuesta de ese ciclo entero y hay que esperar 3s (el intervalo de poll)
  // para el siguiente intento. Reintentar aca mismo, en el momento, aprovecha mejor las
  // ventanas cortas en las que el backend SI responde bien.
  function fetchBatchesWithRetry(projectId, attempt) {
    attempt = attempt || 0;
    return apiFetch("/api/projects/" + projectId + "/batches?limit=6&offset=0").then(function (r) {
      if (!r.ok && attempt < 3) {
        return new Promise(function (resolve) {
          setTimeout(resolve, 350);
        }).then(function () {
          return fetchBatchesWithRetry(projectId, attempt + 1);
        });
      }
      return r;
    });
  }

  function listBatches(projectId) {
    var cached = batchesCache[projectId];
    var now = Date.now();
    if (cached && now - cached.ts < BATCHES_CACHE_MS) {
      return cached.promise;
    }
    var promise = fetchBatchesWithRetry(projectId).then(function (r) {
      var batches = (r.data && (r.data.batches || r.data.items || r.data)) || [];
      return Array.isArray(batches) ? batches : [];
    });
    batchesCache[projectId] = { ts: now, promise: promise };
    return promise;
  }

  // Escribe el prompt, adjunta la imagen de referencia (si hay) y hace clic en Generate --
  // el "envio" en si. Devuelve el set de ids de batch que YA existian antes del clic, para
  // que quien llama identifique el batch propio DESPUES, sin bloquear esta cola. Rapido a
  // proposito: nada de sondeos largos aca adentro (ver identifyBatch/trackAndWait mas abajo
  // para el porque). El texto se escribe DESPUES de adjuntar la imagen porque el flujo de
  // "Start, end frame" (abrir panel, elegir miniatura, Add to video) re-renderiza el
  // compositor y borra lo que ya se hubiera escrito antes.
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

  // Identifica el batch EXACTO recien creado por este job (id que no estaba en beforeIds).
  // Se llama justo despues de que sendOneMessage libera sendQueue -- arranca a sondear en el
  // mismo instante en que el siguiente job recien empieza el suyo, y como JS es de un solo
  // hilo, ese primer sondeo corre antes de que el siguiente job tenga tiempo real de red/DOM
  // para crear su propio batch. Por eso el primer batch nuevo que aparece aca es, en la
  // practica, inequivocamente el nuestro -- sin esto, dos jobs en paralelo sobre el mismo
  // proyecto pueden ver el MISMO batch nuevo y descargar el mismo video repetido cada uno.
  function identifyBatch(projectId, beforeIds, timeoutMs) {
    return pollAsync(
      function () {
        return listBatches(projectId).then(function (batches) {
          for (var i = 0; i < batches.length; i++) {
            if (batches[i] && batches[i].id && !beforeIds[batches[i].id]) {
              return batches[i].id;
            }
          }
          return null;
        });
      },
      Date.now() + timeoutMs,
      400
    );
  }

  // Espera a que el batch identificado por batchId (id exacto, no ambiguo) termine
  // (isComplete) y devuelve su video. Se corre SIN bloquear sendQueue -- por eso varias de
  // estas pueden estar activas a la vez, una por cada job/slot ya enviado.
  function waitForVideos(projectId, batchId, deadlineTs) {
    return pollAsync(
      function () {
        return listBatches(projectId).then(function (batches) {
          var fresh = null;
          for (var i = 0; i < batches.length; i++) {
            if (batches[i] && batches[i].id === batchId) {
              fresh = batches[i];
              break;
            }
          }
          if (!fresh) return null;
          if (fresh.isComplete || fresh.is_complete) {
            // GET /api/generation-batches/{id}/stream (SSE) confirmado en vivo que trae
            // los videos en "items", NO en "content" (ver _handle_complete_event en
            // vibes_client.py) -- este es el REST /batches, un endpoint distinto, pero
            // un timeout real observado en vivo (2026-07-20: isComplete nunca detectado
            // pese a que la imagen y el batch se crearon bien) apunta a la misma mezcla
            // de nombres aca. Se prueban los dos, "items" primero.
            var items = fresh.items;
            if (!Array.isArray(items)) items = fresh.content;
            if (!Array.isArray(items)) items = [];
            var urls = items.map(extractUrl).filter(Boolean);
            // vibes.ai siempre genera 4 variantes por batch aunque solo se pida un
            // video -- nos quedamos solo con la primera para que 1 slot = 1 video
            // descargado (igual que meta.ai), en vez de descargar la misma 4 veces.
            if (urls.length > 0) return urls.slice(0, 1);
            console.log(
              "[Vibes] paso: batch " + batchId + " isComplete pero sin URLs extraibles -- fresh=" +
                JSON.stringify(fresh).slice(0, 500)
            );
          }
          return null;
        });
      },
      deadlineTs,
      3000
    );
  }

  // Identifica el batch EXACTO de este envio (por id, no por exclusion) y espera su video --
  // todo esto corre por fuera de sendQueue, asi que no atrasa el envio del siguiente job. Si
  // vibes.ai nunca crea el batch (probable 500 en su propio POST /api/generate/videos -- pasa
  // seguido con su backend degradado), reintenta el envio completo desde cero encolandolo de
  // nuevo en sendQueue (el reintento si vuelve a tocar el DOM, asi que debe respetar el orden).
  function trackAndWait(projectId, prompt, imageInfo, beforeIds, deadlineTs, retriesLeft, startTs) {
    startTs = startTs || Date.now();
    return identifyBatch(projectId, beforeIds, 10000).then(
      function (batchId) {
        console.log(
          "[Vibes] tiempo: batch identificado (" + batchId + ") a los " +
            ((Date.now() - startTs) / 1000).toFixed(1) + "s de enviado"
        );
        return waitForVideos(projectId, batchId, deadlineTs).then(function (urls) {
          console.log(
            "[Vibes] tiempo: video listo (batch " + batchId + ") a los " +
              ((Date.now() - startTs) / 1000).toFixed(1) + "s de enviado"
          );
          return urls;
        });
      },
      function () {
        if (retriesLeft > 0) {
          console.log(
            "[Vibes] paso: vibes.ai no creo el batch (probable 500 en /generate/videos), reintentando envio (" +
              retriesLeft +
              " intento(s) restante(s))..."
          );
          var retry = sendQueue.then(function () {
            return sendOneMessage(projectId, prompt, imageInfo);
          });
          sendQueue = retry.then(
            function () {},
            function () {},
          );
          return retry.then(function (newBeforeIds) {
            return trackAndWait(projectId, prompt, imageInfo, newBeforeIds, deadlineTs, retriesLeft - 1, startTs);
          });
        }
        throw new Error("vibes.ai nunca creo el batch tras reintentos (500 en /generate/videos)");
      }
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
    var t0 = Date.now();

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
              waiters.push(trackAndWait(projectId, job.prompt, imageInfo, beforeIds, deadlineTs, 2));
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
        console.log(
          "[Vibes] tiempo: envio (DOM) completo a los " + ((Date.now() - t0) / 1000).toFixed(1) + "s -- esperando video(s)..."
        );
        return Promise.all(waiters);
      })
      .then(function (results) {
        var allUrls = [];
        results.forEach(function (urls) {
          allUrls = allUrls.concat(urls);
        });
        console.log(
          "[Vibes] Listo req=" + requestId.slice(0, 8) + " " + allUrls.length + " video(s) en " +
            ((Date.now() - t0) / 1000).toFixed(1) + "s totales"
        );
        sendResult({ requestId: requestId, status: 200, videos: allUrls });
      })
      .catch(function (err) {
        console.log(
          "[Vibes] Error generando req=" + requestId.slice(0, 8) + ": " + err.message + " (a los " +
            ((Date.now() - t0) / 1000).toFixed(1) + "s)"
        );
        sendResult({ requestId: requestId, status: 0, error: err.message });
      });
  }

  // El fetch real al bridge Python vive en vibes_relay.js (ISOLATED world, con
  // privilegios de extension) -- este postMessage es lo unico que cruza de vuelta
  // hacia alla. Namespaceado con __vibesRelay para no chocar con otros postMessage
  // de la pagina real de vibes.ai.
  function sendResult(payload) {
    window.postMessage({ __vibesRelay: true, type: "VIBES_RESULT", payload: payload }, "*");
  }

  // Jobs entrantes: vibes_relay.js los recibe de /api/vibes/poll y los reenvia aca
  // porque solo este script (MAIN world) tiene acceso al DOM real del compositor.
  window.addEventListener("message", function (event) {
    if (event.source !== window) return;
    var data = event.data;
    if (!data || data.__vibesRelay !== true || data.type !== "VIBES_JOB") return;
    runGenerate(data.job);
  });

  console.log("[Vibes] bridge v6 activo (DOM texto/generate + upload-media HTTP)");
})();
