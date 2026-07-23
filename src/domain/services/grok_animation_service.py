import json
import os
import tempfile
import threading
import zipfile
from io import BytesIO
from pathlib import Path

from src.domain.services.account_slot_assigner import SlotAssigner
from src.domain.services.project_service import sanitize_name
from src.infrastructure.ai_providers import grok_process, grok_service, grok_session_bridge
from src.infrastructure.storage import project_repository
from src.utils.logger import get_logger
from src.utils.paths import get_grok_accounts_dir, get_grok_downloads_dir
from src.utils.platform_utils import open_folder

logger = get_logger(__name__)

# 10 carpetas pre-creadas por ensure_accounts_setup (account_1..account_10, ver
# grok_service.py) -- mismo limite que usa el slot assigner de la deteccion
# automatica de sesion.
_NUM_ACCOUNTS = 10

# Estado indexado por proyecto (sanitize_name) -- antes era un unico dict a
# nivel de modulo compartido por TODOS los proyectos: lanzar un batch para un
# proyecto B mataba (.terminate()) el proc de un proyecto A que seguia
# corriendo, y /log de cualquier pestana abierta leia siempre el mismo
# _state global sin importar que proyecto tenia activo. Con _batches cada
# proyecto tiene su propio proc/log_lines/regen_count y arrancar uno no toca
# a los demas.
_batches: dict[str, dict] = {}
_batches_lock = threading.Lock()
_last_project: str | None = None


def _new_batch_state() -> dict:
    return {
        "proc": None,
        "log_lines": [],
        "finished": False,
        "project_dir": None,
        "images": [],
        "total": 0,
        "regen_count": 0,
    }


def _get_batch(name: str) -> dict:
    with _batches_lock:
        return _batches.setdefault(name, _new_batch_state())


def _resolve_name(project_name: str) -> str:
    """Nombre saneado de proyecto, o el ultimo proyecto tocado si viene vacio
    (compatibilidad con llamadas que no pueden pasar el project explicito,
    p. ej. codigo legacy o un cliente que no mando el query param)."""
    name = sanitize_name(project_name or "")
    if name:
        return name
    return _last_project or ""


def _tail_process(proc, name: str):
    batch = _get_batch(name)
    try:
        for line in iter(proc.stdout.readline, b""):
            batch["log_lines"].append(line.decode("utf-8", errors="replace").rstrip())
    except Exception:
        pass
    batch["finished"] = True


# ─────────────────────────────────────────────────────────────────
# Sesiones de cuenta
# ─────────────────────────────────────────────────────────────────


def list_sessions() -> list[dict]:
    accounts_dir = get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    return grok_service.list_account_sessions(accounts_dir)


# ── Deteccion automatica de sesion via la extension (bridge de Chrome) ───────────
# grok_session_bridge.py detecta la cookie `sso` via background.js (chrome.cookies,
# ver el comentario de ese modulo) y avisa aca en cuanto hay una sesion valida.
# El listener escribe cookies_auto.json en el MISMO formato que ya produce
# grok_service.login_account_managed() -- list_account_sessions()/GrokAccountClient
# la detectan sin ningun cambio adicional, como si el usuario hubiera hecho login
# manual. La generacion (API HTTP directa) no se toca.
_slot_assigner: SlotAssigner | None = None


def _get_slot_assigner() -> SlotAssigner:
    global _slot_assigner
    if _slot_assigner is None:
        _slot_assigner = SlotAssigner(
            sidecar_dir=get_grok_accounts_dir(),
            prefix="grok_account",
            num_slots=_NUM_ACCOUNTS,
            valid_hash_prefix="gr:",
        )
    return _slot_assigner


def _sso_from_cookie_list(cookies: list) -> str:
    for c in cookies:
        if isinstance(c, dict) and c.get("name") == "sso":
            return c.get("value") or ""
    return ""


def _find_slot_for_existing_sso(accounts_dir: Path, sso: str) -> int | None:
    """Reconcilia con carpetas de cuenta que ya tenian cookies_auto.json ANTES de
    que existiera este bridge (sin sidecar hash->slot, p. ej. un login manual
    previo) -- si alguna YA tiene la MISMA cookie `sso` (misma sesion real), hay
    que reusar ese slot en vez de crear uno nuevo. Sin este chequeo, la primera
    vez que el bridge detecta una cuenta ya logueada antes, el slot con la cookie
    vieja aparece "ocupado" por otra cuenta y se duplica la misma sesion en dos
    carpetas distintas (mismo bug que se corrigio en GenTube)."""
    if not sso:
        return None
    for i in range(_NUM_ACCOUNTS):
        ck_file = accounts_dir / f"account_{i + 1}" / "cookies_auto.json"
        if not ck_file.exists():
            continue
        try:
            existing_cookies = json.loads(ck_file.read_text())
        except Exception:
            continue
        if _sso_from_cookie_list(existing_cookies) == sso:
            return i
    return None


# Serializa TODO el cuerpo de _on_bridge_session -- ver el comentario identico en
# gentube_animation_service.py (bug confirmado en produccion 2026-07-23): sin este
# lock, dos llamadas casi simultaneas pueden leer cookies_auto.json a mitad de
# la escritura de la otra, fallar la reconciliacion por sso, y crear una carpeta
# de cuenta duplicada para la misma sesion real.
_bridge_session_lock = threading.Lock()


def _write_json_atomic(path: Path, data) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _on_bridge_session(account_hash: str, meta: dict) -> None:
    cookies = meta.get("cookies") or []
    if not cookies:
        return
    with _bridge_session_lock:
        accounts_dir = get_grok_accounts_dir()
        grok_service.ensure_accounts_setup(accounts_dir)

        def _slot_taken(i: int) -> bool:
            return (accounts_dir / f"account_{i + 1}" / "cookies_auto.json").exists()

        idx = _find_slot_for_existing_sso(accounts_dir, _sso_from_cookie_list(cookies))
        if idx is not None:
            # Reconciliado con una carpeta que ya existia en disco -- registrar el
            # atajo en memoria para que la PROXIMA deteccion de este mismo hash no
            # vuelva a escanear el disco entero.
            _get_slot_assigner().bind(account_hash, idx)
        else:
            idx = _get_slot_assigner().assign_slot(account_hash, slot_taken_on_disk=_slot_taken)
        if idx is None:
            logger.info(
                "[grok] Sin slots libres (limite %d) - sesion detectada via extension descartada", _NUM_ACCOUNTS
            )
            return

        folder = accounts_dir / f"account_{idx + 1}"
        folder.mkdir(parents=True, exist_ok=True)
        cookie_list = [
            {
                "name": c.get("name"),
                "value": c.get("value"),
                "domain": ".grok.com",
                "path": "/",
                "httpOnly": bool(c.get("httpOnly", False)),
                "secure": bool(c.get("secure", True)),
            }
            for c in cookies
            if isinstance(c, dict) and c.get("name") and c.get("value")
        ]
        if not cookie_list:
            return
        already_active = (folder / "cookies_auto.json").exists()
        _write_json_atomic(folder / "cookies_auto.json", cookie_list)
        _get_slot_assigner().write_sidecar(idx, account_hash, {})
        if not already_active:
            logger.info("[grok] Sesion detectada automaticamente via extension -> %s", folder.name)


grok_session_bridge.add_session_listener(_on_bridge_session)


def start_account_login(account_name: str) -> None:
    """Lanza el login (Playwright, ventana visible) en un hilo de fondo."""
    accounts_dir = get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    folder = grok_service.account_dir(accounts_dir, account_name)
    folder.mkdir(parents=True, exist_ok=True)
    logger.info("Abriendo Chrome — inicia sesion en grok.com y espera a que la ventana se cierre sola.")

    def _run():
        ok, message = grok_service.login_account_managed(folder, folder.name)
        logger.info(message)

    threading.Thread(target=_run, daemon=True).start()


def delete_session(account_name: str) -> None:
    accounts_dir = get_grok_accounts_dir()
    grok_service.delete_account_session(accounts_dir, account_name)


# Fallback automatico (ver unificacion de deteccion de sesion, Flow de referencia):
# si al arrancar un lote no hay NINGUNA cuenta con sesion utilizable, abrimos Chrome
# automaticamente para la primera cuenta en vez de exigir que el usuario vaya a
# Sesiones y apriete "Login" a mano. Cooldown por cuenta para no reabrir una ventana
# en cada intento fallido consecutivo.
_auto_login_last_attempt: dict[str, float] = {}
_AUTO_LOGIN_COOLDOWN = 60.0


def _trigger_auto_login_if_needed(accounts_dir) -> None:
    import time

    sessions = grok_service.list_account_sessions(accounts_dir)
    if any(s.get("active") for s in sessions):
        return
    target = sessions[0]["name"] if sessions else "account_1"
    now = time.time()
    if now - _auto_login_last_attempt.get(target, 0) < _AUTO_LOGIN_COOLDOWN:
        return
    _auto_login_last_attempt[target] = now
    logger.info("[grok] Sin sesion disponible - abriendo Chrome automaticamente para %s", target)
    start_account_login(target)


# ─────────────────────────────────────────────────────────────────
# Animacion por lote
# ─────────────────────────────────────────────────────────────────


def start_batch(
    project_name: str,
    images: list[tuple[str, object]],
    prompt: str,
    slots: int,
    aspect_ratio: str,
    video_length: int,
    resolution: str,
) -> dict:
    """`images` es una lista de (filename, file_storage) donde file_storage tiene .save(path)."""
    global _last_project

    name = sanitize_name(project_name)
    if not name:
        raise ValueError("Selecciona un proyecto en la barra superior antes de animar.")

    batch = _get_batch(name)
    # Solo mata un batch previo DEL MISMO proyecto (reinicio) -- nunca el de
    # otro proyecto que este corriendo en paralelo.
    if batch["proc"] and batch["proc"].poll() is None:
        batch["proc"].terminate()

    proj_dir = project_repository.create_project(name)
    accounts_dir = get_grok_accounts_dir()
    grok_service.ensure_accounts_setup(accounts_dir)
    try:
        _trigger_auto_login_if_needed(accounts_dir)
    except Exception:
        logger.exception("[grok] fallback de auto-login fallo")

    if not images:
        raise ValueError("No se recibieron imagenes")

    img_dir = proj_dir / "imagen"
    img_dir.mkdir(parents=True, exist_ok=True)
    images_meta = []
    for i, (filename, file_storage) in enumerate(images):
        dest = img_dir / filename
        if not dest.exists():
            file_storage.save(str(dest))
        images_meta.append({"index": i + 1, "name": filename, "path": str(dest)})

    stage_names = [m["name"] for m in images_meta]

    (proj_dir / "guion").mkdir(parents=True, exist_ok=True)
    (proj_dir / "guion" / "config.txt").write_text(
        f"prompt: {prompt}\nslots: {slots}\naspect_ratio: {aspect_ratio}\n"
        f"video_length: {video_length}\nresolution: {resolution}\n"
    )

    batch.update(
        {
            "log_lines": [],
            "finished": False,
            "project_dir": str(proj_dir),
            "images": images_meta,
            "total": len(images_meta),
            "regen_count": 0,
        }
    )
    _last_project = name

    stage_list_path = proj_dir / "guion" / "animate_this_run.json"
    stage_list_path.write_text(json.dumps(stage_names))

    proc = grok_process.spawn_worker(
        [
            str(img_dir),
            "--output-dir",
            str(proj_dir / "video"),
            "--filter-file",
            str(stage_list_path),
            "--slots",
            str(slots),
            "--prompt",
            prompt,
            "--aspect-ratio",
            aspect_ratio,
            "--video-length",
            str(video_length),
            "--resolution",
            resolution,
        ],
        cwd=accounts_dir.parent,
    )
    batch["proc"] = proc

    threading.Thread(target=_tail_process, args=(proc, name), daemon=True).start()

    return {"ok": True, "pid": proc.pid, "project_dir": str(proj_dir), "project_name": name}


def start_regen(
    project_name: str, video_name: str, prompt: str, aspect_ratio: str, video_length: int, resolution: str
) -> dict:
    global _last_project

    name = _resolve_name(project_name)
    if not name:
        raise ValueError("Sin proyecto activo")
    proj_dir = project_repository.project_dir(name)
    batch = _get_batch(name)
    batch["project_dir"] = str(proj_dir)
    _last_project = name

    batch["regen_count"] = batch.get("regen_count", 0) + 1
    batch["finished"] = False

    vid_stem = Path(video_name).stem
    img_dir = proj_dir / "imagen"
    matches = [
        p
        for p in img_dir.iterdir()
        if p.is_file()
        and p.stem == vid_stem
        and p.suffix.lower().lstrip(".") in project_repository.IMAGE_EXTS
    ]
    if not matches:
        raise FileNotFoundError(f"No hay imagen con stem {vid_stem}")
    img_path = matches[0]

    old_vid = proj_dir / "video" / video_name
    if old_vid.exists():
        old_vid.unlink()

    tmp_dir = Path(tempfile.mkdtemp())
    import shutil

    shutil.copy2(str(img_path), str(tmp_dir / img_path.name))

    accounts_dir = get_grok_accounts_dir()
    target_name = f"{img_path.stem}.mp4"

    def _run():
        video_dir = proj_dir / "video"
        snap_before = {f.name for f in video_dir.glob("*.mp4")}
        proc = grok_process.spawn_worker(
            [
                str(tmp_dir),
                "--output-dir",
                str(video_dir),
                "--slots",
                "1",
                "--prompt",
                prompt,
                "--aspect-ratio",
                aspect_ratio,
                "--video-length",
                str(video_length),
                "--resolution",
                resolution,
            ],
            cwd=accounts_dir.parent,
        )
        for line in iter(proc.stdout.readline, b""):
            batch["log_lines"].append(line.decode("utf-8", errors="replace").rstrip())
        proc.wait()

        snap_after = {f.name for f in video_dir.glob("*.mp4")}
        new_files = snap_after - snap_before
        if new_files:
            if target_name not in new_files:
                src = video_dir / sorted(new_files)[0]
                try:
                    src.rename(video_dir / target_name)
                except Exception as exc:
                    batch["log_lines"].append(f"[regen] rename error: {exc}")
            batch["log_lines"].append(f"Regen completado: {target_name}")
        else:
            dl_dir = get_grok_downloads_dir()
            dl_videos = sorted(dl_dir.glob("*.mp4"), key=lambda f: f.stat().st_mtime)
            if dl_videos:
                shutil.copy2(str(dl_videos[-1]), str(video_dir / target_name))
                batch["log_lines"].append(f"Regen completado (desde downloads): {target_name}")
            else:
                batch["log_lines"].append(f"Regen termino pero no se encontro el video: {target_name}")

        batch["regen_count"] = max(0, batch.get("regen_count", 1) - 1)
        if batch["regen_count"] == 0:
            batch["finished"] = True
        shutil.rmtree(str(tmp_dir), ignore_errors=True)

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True}


def stop(project_name: str = "") -> None:
    name = _resolve_name(project_name)
    if not name:
        return
    batch = _get_batch(name)
    if batch["proc"] and batch["proc"].poll() is None:
        batch["proc"].terminate()
    batch["finished"] = True


def get_log_state(offset: int, project_name: str = "") -> dict:
    name = _resolve_name(project_name)
    if not name:
        return {"lines": [], "next_offset": offset, "finished": True, "videos_done": 0, "videos_total": 0}
    batch = _get_batch(name)
    finished = batch["finished"] or (batch["proc"] is not None and batch["proc"].poll() is not None)
    lines = batch["log_lines"][offset:]
    video_dir = Path(batch["project_dir"]) / "video" if batch["project_dir"] else None
    try:
        videos_done = len(list(video_dir.glob("*.mp4"))) if video_dir and video_dir.is_dir() else 0
    except Exception:
        videos_done = 0
    return {
        "lines": lines,
        "next_offset": offset + len(lines),
        "finished": finished,
        "videos_done": videos_done,
        "videos_total": int(batch.get("total") or 0),
    }


# ─────────────────────────────────────────────────────────────────
# Videos generados
# ─────────────────────────────────────────────────────────────────


def list_videos(project_name: str) -> dict:
    if not project_name:
        return {"videos": [], "total": 0, "done": 0, "project_dir": "", "project_name": ""}
    name = sanitize_name(project_name)
    videos = sorted(f.name for f in project_repository.list_videos(name))
    return {
        "videos": videos,
        "total": len(videos),
        "done": len(videos),
        "project_dir": str(project_repository.project_dir(name)),
        "project_name": name,
    }


def get_video_path(project_name: str, filename: str) -> Path | None:
    if project_name:
        return project_repository.resolve_safe_file(project_name, "video", filename)
    fallback_dir = get_grok_downloads_dir()
    candidate = (fallback_dir / filename).resolve()
    try:
        candidate.relative_to(fallback_dir.resolve())
    except ValueError:
        return None
    return candidate


def _active_video_dir(project_name: str) -> Path:
    if project_name:
        return project_repository.project_dir(project_name) / "video"
    name = _last_project
    if name:
        batch = _batches.get(name)
        if batch and batch.get("project_dir"):
            return Path(batch["project_dir"]) / "video"
    return get_grok_downloads_dir()


def build_videos_zip(project_name: str) -> tuple[BytesIO, str] | None:
    video_dir = _active_video_dir(project_name)
    videos = sorted(video_dir.glob("*.mp4")) if video_dir.exists() else []
    if not videos:
        return None
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for v in videos:
            zf.write(str(v), v.name)
    buf.seek(0)
    zip_name = f"{sanitize_name(project_name) or 'grok_videos'}_videos.zip"
    return buf, zip_name


def open_videos_folder(project_name: str) -> None:
    video_dir = _active_video_dir(project_name)
    video_dir.mkdir(parents=True, exist_ok=True)
    open_folder(str(video_dir))
