# IMPLEMENTATION_GAPS.md

Matriz completa de brechas de implementación entre frontend (`frontend/src`) y backend (`src/presentation/routes`). Generada con `graphify-out/graph.json` como mapa inicial y **verificada leyendo cada archivo real** (no solo el grafo). Incluye todo lo pedido: "Próximamente", TODO/FIXME/mocks, componentes sin acción real, endpoints en ambas direcciones, páginas/rutas huérfanas, componentes/hooks/servicios no usados y persistencia local temporal.

Fecha: 2026-07-16. Ver también: [FRONTEND_WITHOUT_BACKEND.md](FRONTEND_WITHOUT_BACKEND.md), [BACKEND_WITHOUT_FRONTEND.md](BACKEND_WITHOUT_FRONTEND.md), [DEAD_CODE.md](DEAD_CODE.md).

---

## Metodología (resumen)

- **Grep exhaustivo** de `TODO|FIXME|HACK|NotImplemented|placeholder|mock|dummy|stub` en `frontend/src` y `src/`. Resultado: no hay marcadores reales de trabajo pendiente en comentarios — las coincidencias eran la palabra española "todo" (= "all") o el atributo HTML `placeholder`. El único stub real es `notImplemented()` en `GuionPage.tsx`.
- **Grep de `console.log`** en `frontend/src`: cero resultados.
- **`localStorage.*`**: 8 archivos. La mayoría son cachés legítimos de preferencia de UI (tema, idioma, tabs abiertas). Uno (`TareasPage.tsx`) es persistencia de datos de producto sin backend.
- **Comparación línea por línea** de cada llamada `api.get/post/put/delete` en los 20 archivos de `frontend/src/api/*.ts` contra cada ruta registrada en `src/presentation/app.py:75-99` + sus `url_prefix` reales en `src/presentation/routes/*.py`.
- **Conteo de referencias** (`grep -rl`) para cada componente en `components/*.tsx`, cada hook `useXxx` exportado, y cada función exportada de `api/*.ts`, para detectar código sin ningún consumidor.
- **`App.tsx`** comparado 1:1 contra los 18 archivos en `pages/*.tsx` (nivel raíz) para rutas/páginas huérfanas.

---

## Tabla maestra de hallazgos

| # | Módulo | Archivo | Línea | Descripción | Estado | Impacto | Dependencias para completar |
|---|---|---|---|---|---|---|---|
| 1 | Autenticación | [frontend/src/pages/LoginPage.tsx:328](frontend/src/pages/LoginPage.tsx#L328) | 328 | Botón "Continuar con Google" — `onClick={() => setSoonToast(true)}`, no dispara ningún flujo OAuth | Solo UI | Alto | Credenciales OAuth de Google Cloud Console, endpoint backend `/api/auth/oauth/google`, callback handler |
| 2 | Autenticación | [frontend/src/pages/LoginPage.tsx:342](frontend/src/pages/LoginPage.tsx#L342) | 342 | Botón "Continuar con Apple" — mismo patrón | Solo UI | Alto | Apple Developer "Sign in with Apple" (ya comprado, ver memoria `project_code_signing`), endpoint backend equivalente |
| 3 | Guion | [frontend/src/pages/GuionPage.tsx:207-209](frontend/src/pages/GuionPage.tsx#L207) | 207-313 | `notImplemented()` — helper que alimenta 5 botones de toolbar (Asistente IA, Mejorar, Expandir, Traducir, Más), todos con `onClick={notImplemented}` | Solo UI | Medio | Definir qué modelo/endpoint de IA hará cada acción; el guion principal (`n8n_proxy`, `analyze_image`) ya funciona, esto es una capa extra |
| 4 | Voz | [frontend/src/pages/VozPage.tsx:164-168](frontend/src/pages/VozPage.tsx#L164) | 165-167 | `handleGenerate()` corta con el toast si `provider === "xtts"`, nunca llama a la API | Parcialmente Implementada | Medio | Backend: 0% construido (`src/presentation/routes/voice.py` no tiene ninguna referencia a "xtts"). Frontend: 100% (selector de 6 voces + idioma ya funcional) |
| 5 | Voz | [frontend/src/pages/VozPage.tsx:379-471](frontend/src/pages/VozPage.tsx#L379) | 379-471 | Selector de voces/idiomas XTTS — totalmente interactivo, `setXttsVoice`/`setXttsLang` cambian estado real, pero no hay acción final posible | Solo UI (para el resultado final) | Medio | Igual que #4 |
| 6 | Tareas | [frontend/src/pages/TareasPage.tsx](frontend/src/pages/TareasPage.tsx) | 48, 59 | CRUD completo de tareas (crear/editar/mover/completar) pero persistido únicamente en `localStorage`, sin tabla ni endpoint en backend | Mock/Temporal | Bajo | Modelo `Task` en BD, blueprint `tasks_bp` (`GET/POST/PUT/DELETE /api/tasks`), migración de esquema |
| 7 | Flow (Imagen) | [frontend/src/pages/imagen/FlowPanel.tsx:646-653](frontend/src/pages/imagen/FlowPanel.tsx#L646) | 646-653 | El `<details>` "Ver log completo" renderiza `logLines` de estado local (acumulado por polling de `flowStatus`), **no** llama a `flowFullLog()` — el wrapper y la ruta backend `/api/flow/full-log` existen pero no se usan desde aquí | Parcialmente Implementada | Bajo | Ninguna — es una decisión de diseño (polling incremental vs. log completo bajo demanda); si se quiere usar, solo hace falta cablear el botón |
| 8 | Flow (Imagen) | [frontend/src/pages/imagen/FlowPanel.tsx:567](frontend/src/pages/imagen/FlowPanel.tsx#L567) | 567-587 | Lista de `chromiumProfiles` renderizada por fila, pero solo existe un botón global "Reiniciar Chromium" (`handleResetChromium`, línea 252); no hay acción por-fila que llame a `flowResetChromiumProfile(idx)` aunque el wrapper y la ruta `POST /api/flow/reset-chromium-profile` existen | Parcialmente Implementada | Bajo | Agregar botón de reinicio individual por fila en la UI existente |
| 9 | Idea2Video | [frontend/src/api/idea2video.ts:109](frontend/src/api/idea2video.ts#L109) | 109 | `apImagenUrl()` — función exportada, nunca importada por ninguna página; el backend `GET /api/idea2video/ap_imagen` tampoco se consume desde ningún otro punto | Código Muerto | Bajo | Ninguna, o eliminar ambos lados si la miniatura de autopilot ya no se muestra |
| 10 | Editor | [frontend/src/api/editor.ts:47-52](frontend/src/api/editor.ts#L47) | 47-52 | `editorImageUrl()`/`editorAudioUrl()` — funciones exportadas sin consumidores; `SceneCard.tsx:68` usa `scene.imagen_url` (URL ya armada por el backend en el JSON de respuesta) en vez de construirla con el helper | Código Muerto (el helper; la ruta backend probablemente sí se golpea vía la URL embebida) | Bajo | Ninguna — eliminar el helper o unificar con el campo `imagen_url` del payload |
| 11 | Editor | [frontend/src/api/editor.ts:204-206](frontend/src/api/editor.ts#L204) | 204-206 | `getEditorDownloadUrl()` sin consumidores — el editor reutiliza en su lugar `getRenderDownloadUrl`/`/api/descargar_render/<job_id>` directamente | Código Muerto | Bajo | Eliminar |
| 12 | Flow (Imagen) | [frontend/src/api/flow.ts:60-63](frontend/src/api/flow.ts#L60) | 60-63 | `flowSaveCookie()` sin consumidores — no existe UI de pegado manual de cookie (backend `POST /api/flow/save-cookie` sigue registrado) | Código Muerto | Bajo | Si se necesita login manual por cookie, construir el modal; si no, eliminar función + ruta |
| 13 | Flow (Imagen) | [frontend/src/api/flow.ts:146-148](frontend/src/api/flow.ts#L146) | 146-148 | `flowMtime()` sin consumidores | Código Muerto | Bajo | Eliminar o cablear a un poll de "imagen actualizada" |
| 14 | Componentes | [frontend/src/components/FormField.tsx](frontend/src/components/FormField.tsx) | 1-14 | Componente completo, exportado, **cero imports** en todo el frontend | Código Muerto | Bajo | Eliminar, o adoptarlo en `LoginPage`/`RegisterPage` (que actualmente repiten el mismo `<input>` a mano) |
| 15 | Componentes | [frontend/src/components/TopTabBar.tsx](frontend/src/components/TopTabBar.tsx) | 1-146 | Componente completo (barra de pestañas), **nunca importado** — `AppLayout.tsx` implementa su propia barra de tabs inline usando `useWorkspace()` (línea 267) en su lugar | Código Muerto | Medio | Ninguna para funcionar; decidir si se borra o si reemplaza la barra inline de `AppLayout` |
| 16 | Componentes | [frontend/src/components/ProjectPickerModal.tsx](frontend/src/components/ProjectPickerModal.tsx) | 1-100 | Solo lo importa `TopTabBar.tsx` (línea 5) — que a su vez está muerto → todo el subárbol es inalcanzable | Código Muerto | Bajo | Igual que #15 |
| 17 | Contexto | [frontend/src/context/TabsContext.tsx](frontend/src/context/TabsContext.tsx) | 1-55 | `TabsProvider` se monta globalmente en `App.tsx:31` (lee/escribe `localStorage` en cada carga de la app) pero su único consumidor, `useTabs()`, solo se llama desde `TopTabBar.tsx:43` — que está muerto. El Provider corre en cada render sin que nada lo muestre | Código Muerto (zombie) | Medio | Eliminar `TabsProvider` de `App.tsx` junto con `TopTabBar`/`ProjectPickerModal`, o revivirlo si se decide restaurar esa UI |
| 18 | Endpoints backend huérfanos | Ver [BACKEND_WITHOUT_FRONTEND.md](BACKEND_WITHOUT_FRONTEND.md) | — | `meta_bp` completo (~19 rutas), `usage_bp` (2 rutas, sí usado internamente por `usage_service.py`), `GET /proyectos/imagen_file`, `GET /flow/profile-dump` | Código Muerto (meta) / Backend-interno (usage) / Sin consumo (resto) | Bajo–Medio | Ver documento dedicado |
| 19 | Endpoints frontend→backend | — | — | **Ninguno encontrado.** Las ~100 rutas activamente consumidas por `frontend/src/api/*.ts` tienen contraparte exacta y registrada en `src/presentation/app.py` | N/A | — | — |
| 20 | Páginas/rutas | [frontend/src/App.tsx](frontend/src/App.tsx) | 32-62 | Los 18 archivos de `pages/*.tsx` (raíz) mapean 1:1 contra las rutas declaradas; no hay páginas huérfanas ni rutas sin página | N/A | — | — |

---

## Leyenda de Estado

- **Solo UI**: se ve y se puede interactuar, pero no ejecuta ninguna acción real (backend o frontend).
- **Pendiente Backend**: el frontend está listo, falta la ruta/servicio en `src/`.
- **Pendiente Frontend**: el backend existe y funciona, falta cablear la UI.
- **Parcialmente Implementada**: una parte del flujo funciona, otra parte no (ej. selector completo pero acción final bloqueada).
- **Código Muerto**: existe en el repo, no lo usa nadie ni nada lo renderiza/importa.
- **Mock/Temporal**: funciona, pero con datos que no persisten donde deberían (localStorage en vez de backend).

## Resumen por impacto

| Impacto | Cantidad | Ítems |
|---|---|---|
| Crítico | 0 | — |
| Alto | 2 | OAuth Google, OAuth Apple |
| Medio | 4 | Toolbar IA Guion, XTTS (x2 filas), TopTabBar/TabsContext zombie |
| Bajo | 12 | Resto (código muerto puntual, wrappers sin cablear, endpoints huérfanos) |
