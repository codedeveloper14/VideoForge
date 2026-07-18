# DEAD_CODE.md

Componentes, contextos y funciones de API que existen en el repo pero no tienen ningún consumidor real. Verificado con `grep -rl` de cada nombre exportado contra todo `frontend/src` (no solo el grafo), confirmando que el único archivo que menciona el símbolo es su propia definición.

Ver también [IMPLEMENTATION_GAPS.md](IMPLEMENTATION_GAPS.md) para impacto/dependencias de cada uno.

---

## 1. Subárbol completo huérfano: `TopTabBar` → `ProjectPickerModal` → `TabsContext`

Este es el hallazgo más significativo: un sistema de pestañas completo, construido y montado, pero **inalcanzable en runtime**.

- **[frontend/src/components/TopTabBar.tsx](frontend/src/components/TopTabBar.tsx)** (146 líneas) — nunca importado por ninguna página ni layout. `grep` de `TopTabBar` en todo `frontend/src` solo encuentra su propia definición (línea 41).
- **[frontend/src/components/ProjectPickerModal.tsx](frontend/src/components/ProjectPickerModal.tsx)** — su único importador es `TopTabBar.tsx:5`, que ya está muerto. Todo el subárbol cae junto.
- **[frontend/src/context/TabsContext.tsx](frontend/src/context/TabsContext.tsx)** — el caso más delicado: `TabsProvider` **sí está montado** en [frontend/src/App.tsx:31](frontend/src/App.tsx#L31), envolviendo toda la app. Lee/escribe `localStorage` en cada carga (líneas 19 y 35). Pero su único consumidor, `useTabs()` (línea 50), solo se llama desde `TopTabBar.tsx:43` — muerto. Es un **Provider zombie**: corre en cada render, ocupa memoria y hace I/O a `localStorage`, sin que nada lo muestre.
- **Qué lo reemplazó**: `AppLayout.tsx` implementa su propia barra de pestañas inline usando `useWorkspace()` de [WorkspaceContext.tsx](frontend/src/context/WorkspaceContext.tsx) (ver `AppLayout.tsx:267,293`) — ese es el sistema realmente en uso.

**Acción recomendada**: eliminar `TopTabBar.tsx`, `ProjectPickerModal.tsx`, `TabsContext.tsx` y el `<TabsProvider>` de `App.tsx:31,63`; o si `ProjectPickerModal` tiene alguna utilidad de UI deseable, migrarlo para que lo use `AppLayout`/`WorkspaceContext` en vez de `TabsContext`.

---

## 2. Componente huérfano: `FormField`

- **[frontend/src/components/FormField.tsx](frontend/src/components/FormField.tsx)** — componente completo (envuelve `<input>` con label), exportado por defecto, **cero imports** en todo el proyecto.
- `LoginPage.tsx` y `RegisterPage.tsx` repiten manualmente el mismo patrón de `<input>` + `<label>` con clases Tailwind idénticas en cada campo, en vez de reutilizar este componente.
- **Acción recomendada**: adoptarlo en Login/Register (reduce duplicación) o eliminarlo si se decide no estandarizar.

---

## 3. Funciones de API sin ningún consumidor

Confirmado con un barrido de todos los `export function`/`export const` en `frontend/src/api/*.ts` contra el resto del árbol:

| Función | Archivo | Ruta backend que dejaría de golpearse |
|---|---|---|
| `apImagenUrl()` | [idea2video.ts:109](frontend/src/api/idea2video.ts#L109) | `GET /api/idea2video/ap_imagen` (tampoco consumida por nadie más — ver [BACKEND_WITHOUT_FRONTEND.md](BACKEND_WITHOUT_FRONTEND.md)) |
| `editorImageUrl()` | [editor.ts:47](frontend/src/api/editor.ts#L47) | `GET /api/editor/imagen/<proj>/<file>` — probablemente sigue viva vía `scene.imagen_url` embebida por el backend en el JSON (ver `SceneCard.tsx:68`), solo el helper TS es redundante |
| `editorAudioUrl()` | [editor.ts:51](frontend/src/api/editor.ts#L51) | Igual que arriba, para audio |
| `getEditorDownloadUrl()` | [editor.ts:204](frontend/src/api/editor.ts#L204) | El editor usa `getRenderDownloadUrl` en su lugar; la ruta backend sigue viva por ese otro camino |
| `flowSaveCookie()` | [flow.ts:60](frontend/src/api/flow.ts#L60) | `POST /api/flow/save-cookie` |
| `flowResetChromiumProfile()` | [flow.ts:89](frontend/src/api/flow.ts#L89) | `POST /api/flow/reset-chromium-profile` |
| `flowFullLog()` | [flow.ts:134](frontend/src/api/flow.ts#L134) | `GET /api/flow/full-log` |
| `flowMtime()` | [flow.ts:146](frontend/src/api/flow.ts#L146) | `GET /api/flow/mtime` |

**Acción recomendada**: eliminar `apImagenUrl`, `editorImageUrl`, `editorAudioUrl`, `getEditorDownloadUrl` sin más (son redundantes o no tienen caso de uso). Para las 4 de `flow.ts`, decidir primero si la funcionalidad correspondiente (cookie manual, reset por perfil, log completo, mtime) se quiere exponer en la UI — si no, eliminar función + ruta backend juntas.

---

## 4. Backend huérfano relacionado

No repetido aquí en detalle — ver [BACKEND_WITHOUT_FRONTEND.md](BACKEND_WITHOUT_FRONTEND.md) para el blueprint `meta_bp` completo (~19 rutas muertas tras la migración a Vibes) y las rutas sueltas sin consumo.

---

## 5. Lo que se buscó y NO se encontró (para que quede registrado)

- **`console.log`**: cero ocurrencias en `frontend/src`.
- **Comentarios `TODO`/`FIXME`/`HACK`**: cero — todas las coincidencias de "todo" eran la palabra española, no el marcador en inglés.
- **`throw new Error("Not implemented")`** o equivalente: cero.
- **Páginas sin ruta / rutas sin página**: cero — los 18 archivos de `pages/*.tsx` (raíz) mapean exactamente contra `App.tsx:32-62`.
- **Hooks custom sin uso**: los 4 hooks exportados (`useAuth`, `useTheme`, `useTabs`, `useWorkspace`) tienen consumidor — `useTabs` es el caso límite (ver sección 1: su único consumidor está muerto, así que en la práctica tampoco se ejecuta nunca, pero técnicamente "tiene un import").
- **Componentes**: de 11 en `components/`, 8 están en uso activo (`ActiveJobsPopup`, `ComingSoonToast`, `GuionHeaderArt`, `HeaderArt`, `PipelineStepper`, `ProtectedRoute`, `Select`, `UpdateNotice`); 3 están muertos (sección 1 y 2).

---

### Resumen

| Categoría | Cantidad | Severidad de limpieza |
|---|---|---|
| Componentes huérfanos | 3 (`TopTabBar`, `ProjectPickerModal`, `FormField`) | Baja (no rompen nada, ocupan bundle) |
| Contexto zombie (montado, sin efecto visible) | 1 (`TabsContext`/`TabsProvider`) | Media (hace I/O innecesario en cada carga) |
| Funciones de API sin consumidor | 8 | Baja |
| Rutas backend sin ningún consumidor | ~22 (`meta_bp` + sueltas) | Baja |
