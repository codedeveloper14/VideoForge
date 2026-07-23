"""Rastrea llamadas POST sincronas (sin hilo de fondo propio, p. ej. generar prompts o
fusionar audio) para que el panel de tareas del frontend ('/api/multitask/jobs') pueda
mostrar una actividad breve mientras corren, igual que los jobs de renderizado de
job_registry -- pero sin progreso real, solo inicio/fin."""

import threading
import time
import uuid

from flask import g, request

_tasks: dict[str, dict] = {}
_lock = threading.Lock()

TRACKED_ROUTES: dict[str, tuple[str, str]] = {
    "/api/guion/n8n_proxy": ("guion", "Generando guion y prompts..."),
    "/api/voz/generar": ("voz_gen", "Generando voz..."),
    "/api/voz/fusionar": ("voz_fus", "Fusionando audio..."),
    "/api/editor/analizar": ("editor", "Analizando proyecto..."),
    "/api/guion/analyze_image": ("guion", "Analizando imagen..."),
}
_STALE_AFTER_SECONDS = 300


def clean_old_tasks() -> None:
    now = time.time()
    with _lock:
        stale = [
            k
            for k, v in _tasks.items()
            if v["estado"] != "procesando" and now - v["inicio"] > _STALE_AFTER_SECONDS
        ]
        for k in stale:
            del _tasks[k]


def all_tasks() -> list[dict]:
    with _lock:
        return list(_tasks.values())


def register_task_tracker(app) -> None:
    @app.before_request
    def _track_start():
        for route, (tipo, msg) in TRACKED_ROUTES.items():
            if request.path.startswith(route) and request.method == "POST":
                tid = str(uuid.uuid4())[:6]
                body = request.get_json(silent=True, force=True) or {}
                proyecto = (body.get("project_name") or body.get("proyecto") or "").strip()
                with _lock:
                    _tasks[tid] = {
                        "id": tid,
                        "tipo": tipo,
                        "mensaje": msg,
                        "estado": "procesando",
                        "inicio": time.time(),
                        "proyecto": proyecto,
                        "progreso": 0,
                        "video_url": None,
                    }
                g._vf_task_id = tid
                break

    @app.after_request
    def _track_end(response):
        tid = getattr(g, "_vf_task_id", None)
        if tid:
            ok = response.status_code < 400
            with _lock:
                if tid in _tasks:
                    _tasks[tid]["estado"] = "completado" if ok else "error"
                    _tasks[tid]["progreso"] = 100 if ok else 0
        return response
