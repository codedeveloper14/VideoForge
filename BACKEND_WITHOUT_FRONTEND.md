# BACKEND_WITHOUT_FRONTEND.md

Todo lo que existe en el backend (`src/presentation/routes/*.py`, registrado en [src/presentation/app.py:75-99](src/presentation/app.py#L75)) y **no es consumido por ningún archivo de `frontend/src/api/*.ts`** (ni por URL inline en componentes — se verificó con `grep` de `/api/` en todo `frontend/src`, no solo en la capa `api/`).

Ver la matriz completa en [IMPLEMENTATION_GAPS.md](IMPLEMENTATION_GAPS.md).

---

## 1. `meta_bp` — blueprint completo sin consumo (`/api/meta/*`)

Reemplazado por Vibes según el commit `056f0c4` ("feat: conecta el pipeline de video con Vibes (reemplaza la pestaña Meta)"). Ninguna de estas ~19 rutas de [src/presentation/routes/meta.py](src/presentation/routes/meta.py) se llama desde el frontend (no hay `api/meta.ts`, y `frontend/src/api/vibes.ts` es el reemplazo funcional con la misma forma):

```
GET/POST/OPTIONS  /api/meta/ext-register
GET/OPTIONS       /api/meta/ext-poll
POST/OPTIONS      /api/meta/ext-result
POST/OPTIONS      /api/meta/ext-learn
GET/OPTIONS       /api/meta/ext-state
POST/OPTIONS      /api/meta/ext-captured
GET   /api/meta/sesiones
POST  /api/meta/login_cuenta
POST  /api/meta/borrar_sesion
POST  /api/meta/iniciar
POST  /api/meta/detener
GET   /api/meta/log
GET   /api/meta/videos
GET   /api/meta/video
GET   /api/meta/descargar_todas
POST  /api/meta/abrir_carpeta
POST  /api/meta/launch_chrome
POST  /api/meta/open_devmode
```

- **Estado**: Código Muerto (a nivel de producto — el flujo de negocio migró a Vibes). **Impacto**: Bajo (no rompe nada, pero es superficie de ataque/mantenimiento sin propósito).
- **Dependencia para limpiar**: confirmar que ninguna extensión de navegador externa (las rutas `ext-*` sugieren una extensión de Chrome/Firefox que capturaba tokens de Meta AI) sigue apuntando a estos endpoints antes de borrarlos.

## 2. `usage_bp` — expuesto mas no llamado desde el frontend

- [src/presentation/routes/usage.py](src/presentation/routes/usage.py): `POST /api/usage/check`, `POST /api/usage/record`.
- No hay `api/usage.ts` ni ninguna llamada inline en `frontend/src`.
- **Importante — esto NO es código muerto**: `usage_service.py` (el servicio detrás de estas rutas) sí se usa activamente, pero invocado **en proceso** desde `voice_service.py` y `render_service.py` (backend llamando a backend), no vía HTTP desde el navegador. Las rutas HTTP en sí parecen ser una superficie pensada para un consumidor externo (¿app de escritorio antigua, cliente móvil futuro?) que hoy no existe.
- **Estado**: Backend-interno / sin consumo HTTP. **Impacto**: Bajo.

## 3. `GET /api/proyectos/imagen_file`

- [src/presentation/routes/projects.py:125-126](src/presentation/routes/projects.py#L125).
- No hay función equivalente en `frontend/src/api/projects.ts` ni uso inline.
- **Estado**: Sin consumo. **Impacto**: Bajo.

## 4. `GET /api/flow/profile-dump`

- [src/presentation/routes/flow.py:34-36](src/presentation/routes/flow.py#L34).
- No hay función equivalente en `frontend/src/api/flow.ts`.
- **Estado**: Sin consumo. **Impacto**: Bajo. Probablemente una ruta de debug/diagnóstico dejada para inspección manual (curl/Postman), no pensada para la UI.

## 5. `GET /api/idea2video/ap_imagen`

- [src/presentation/routes/idea2video.py:94-95](src/presentation/routes/idea2video.py#L94).
- El wrapper frontend `apImagenUrl()` existe en [frontend/src/api/idea2video.ts:109](frontend/src/api/idea2video.ts#L109) pero nunca se importa — ver [DEAD_CODE.md](DEAD_CODE.md). Doble hallazgo: ni la ruta ni su wrapper se usan.
- **Estado**: Sin consumo (ambos lados). **Impacto**: Bajo.

## 6. Rutas con wrapper frontend existente pero sin disparador en la UI real

Estas SÍ tienen tanto ruta backend como función `api/*.ts` correspondiente, pero ningún componente las invoca — la "brecha" está en la capa de UI, no en la de red:

| Ruta backend | Wrapper frontend | Por qué no se usa |
|---|---|---|
| `POST /api/flow/save-cookie` | `flowSaveCookie()` en [flow.ts:60](frontend/src/api/flow.ts#L60) | No existe modal de pegado manual de cookie en `FlowPanel.tsx` |
| `POST /api/flow/reset-chromium-profile` | `flowResetChromiumProfile()` en [flow.ts:89](frontend/src/api/flow.ts#L89) | `FlowPanel.tsx` solo tiene reset global (`handleResetChromium`, línea 252); no hay botón por-fila en la lista de perfiles (línea 567) |
| `GET /api/flow/full-log` | `flowFullLog()` en [flow.ts:134](frontend/src/api/flow.ts#L134) | El `<details>` "Ver log completo" (`FlowPanel.tsx:646-653`) usa `logLines` acumulado localmente por polling, no esta ruta |
| `GET /api/flow/mtime` | `flowMtime()` en [flow.ts:146](frontend/src/api/flow.ts#L146) | Sin consumidor |
| `GET /api/descargar_render/<job_id>` (vía editor) | `getEditorDownloadUrl()` en [editor.ts:204](frontend/src/api/editor.ts#L204) | El editor reutiliza `getRenderDownloadUrl` en su lugar; la ruta sigue viva por ese otro camino |

- **Estado**: Parcialmente Implementada / Código Muerto (según el caso, ver tabla). **Impacto**: Bajo en todos.

---

### Resumen

| Bloque | Rutas afectadas | Estado | Impacto |
|---|---|---|---|
| `meta_bp` completo | ~19 | Código Muerto | Bajo |
| `usage_bp` | 2 | Backend-interno, sin HTTP externo | Bajo |
| `proyectos/imagen_file`, `flow/profile-dump` | 2 | Sin consumo | Bajo |
| `idea2video/ap_imagen` | 1 | Sin consumo (ruta + wrapper) | Bajo |
| Wrappers sin UI (flow save-cookie / reset-profile / full-log / mtime, editor download) | 5 | Parcial / Código Muerto | Bajo |
