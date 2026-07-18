# FRONTEND_WITHOUT_BACKEND.md

Todo lo que existe en el frontend (`frontend/src`) y **no tiene soporte real en el backend** (`src/presentation/routes`). Verificado leyendo cada archivo — no solo el grafo de `graphify-out/graph.json`.

Ver la matriz completa con impacto/dependencias en [IMPLEMENTATION_GAPS.md](IMPLEMENTATION_GAPS.md).

---

## 1. Login con Google (OAuth)

- **Archivo**: [frontend/src/pages/LoginPage.tsx:326-339](frontend/src/pages/LoginPage.tsx#L326)
- El botón renderiza el logo de Google completo y el texto `t("login.continueWithGoogle")`. El `onClick` (línea 328) solo hace `setSoonToast(true)`.
- **Backend**: no existe ninguna ruta `oauth`/`google` en `src/presentation/routes/auth.py` (las únicas rutas de auth son `/login`, `/register`, `/change-password`, `/logout`, `/auth/me`, todas con usuario/contraseña).
- **Estado**: Solo UI. **Impacto**: Alto (primer punto de contacto de un usuario nuevo).

## 2. Login con Apple (OAuth)

- **Archivo**: [frontend/src/pages/LoginPage.tsx:340-352](frontend/src/pages/LoginPage.tsx#L340)
- Mismo patrón que Google, `onClick` en línea 342.
- **Backend**: no existe.
- **Estado**: Solo UI. **Impacto**: Alto.

## 3. Toolbar de IA en Guion (5 acciones)

- **Archivo**: [frontend/src/pages/GuionPage.tsx:296-313](frontend/src/pages/GuionPage.tsx#L296)
- Botones: "Asistente IA" (línea 299), "Mejorar guion", "Expandir", "Traducir", "Más" (mapeados en línea 304-313, todos con `onClick={notImplemented}`).
- `notImplemented()` (líneas 207-209) solo hace `setSoonToast(true)`.
- **Backend**: no existe ninguna ruta para estas acciones. El resto de Guion (`guardar`, `cargar`, `analyze_image`, `n8n_proxy`) sí está implementado y en uso.
- **Estado**: Solo UI. **Impacto**: Medio.

## 4. Generación de voz — proveedor XTTS

- **Archivo**: [frontend/src/pages/VozPage.tsx:164-168](frontend/src/pages/VozPage.tsx#L164) (lógica) y [:379-471](frontend/src/pages/VozPage.tsx#L379) (UI del selector)
- El tab "XTTS" tiene selector de 6 voces (`XTTS_VOICES`, línea 63) y de idioma (`XTTS_LANGS`, línea 64) **totalmente funcionales** — cambian estado real (`setXttsVoice`, `setXttsLang`).
- Al presionar "Generar", `handleGenerate()` detecta `provider === "xtts"` y corta a `setSoonToast(true)` **antes** de llamar a cualquier API.
- **Backend**: cero referencias a "xtts" en `src/presentation/routes/voice.py` — ni la ruta ni el servicio existen. El proveedor por defecto (IVR) sí funciona end-to-end vía `POST /voz/generar`.
- **Estado**: Parcialmente Implementada (UI 100%, acción 0%). **Impacto**: Medio.

## 5. Tareas — persistencia solo local

- **Archivo**: [frontend/src/pages/TareasPage.tsx](frontend/src/pages/TareasPage.tsx)
- CRUD completo (crear, editar, mover entre estados `todo`/`progress`/`done`, eliminar) funciona de punta a punta, pero **todo el estado vive en `localStorage`** (líneas [48](frontend/src/pages/TareasPage.tsx#L48) y [59](frontend/src/pages/TareasPage.tsx#L59), clave `STORAGE_KEY`).
- **Backend**: no existe ningún blueprint de tareas en `src/presentation/routes/` ni tabla asociada.
- **Consecuencia real**: las tareas no sincronizan entre dispositivos ni sobreviven a un borrado de datos del navegador o una reinstalación.
- **Estado**: Mock/Temporal. **Impacto**: Bajo (funciona para el usuario, pero es una isla de datos).

## 6. Wrappers de API sin ruta que los respalde de forma completa

Ninguno — todas las funciones de `frontend/src/api/*.ts` que sí se invocan desde algún componente apuntan a una ruta backend real (ver verificación exhaustiva en [IMPLEMENTATION_GAPS.md](IMPLEMENTATION_GAPS.md)). Las únicas funciones "huérfanas" (`apImagenUrl`, `editorImageUrl`, `editorAudioUrl`, `getEditorDownloadUrl`, `flowSaveCookie`, `flowMtime`) no fallan por falta de backend — el backend para ellas si existe, simplemente nadie las llama desde la UI. Estas están documentadas como código muerto en [DEAD_CODE.md](DEAD_CODE.md), no como brecha de backend.

---

### Resumen

| Feature | Archivo | Estado | Impacto |
|---|---|---|---|
| Login Google | LoginPage.tsx:328 | Solo UI | Alto |
| Login Apple | LoginPage.tsx:342 | Solo UI | Alto |
| Toolbar IA Guion | GuionPage.tsx:296-313 | Solo UI | Medio |
| Voz XTTS | VozPage.tsx:164-471 | Parcialmente Implementada | Medio |
| Tareas | TareasPage.tsx | Mock/Temporal | Bajo |
