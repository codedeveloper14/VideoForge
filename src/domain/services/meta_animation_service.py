import base64
import mimetypes
import queue
import subprocess
import threading
import time
import uuid as uuid_lib
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
from pathlib import Path

import requests
from requests.adapters import HTTPAdapter

from src.domain.services.project_service import sanitize_name
from src.infrastructure.ai_providers import (
    chrome_launcher,
    meta_accounts,
    meta_browser,
    meta_chrome_process,
    meta_gql_client,
    meta_verify,
    vibes_bridge,
)
from src.infrastructure.ai_providers.meta_extension_bridge import MetaExtensionBridge
from src.infrastructure.storage import project_repository
from src.utils.logger import get_logger
from src.utils.paths import get_meta_accounts_dir
from src.utils.platform_utils import open_folder

logger = get_logger(__name__)

_MAX_LOG_LINES = 1500
_META_UA = meta_gql_client.META_UA

_state = {
    "running": False,
    "log_lines": [],
    "finished": False,
    "project_dir": None,
    "images": [],
    "total": 0,
    "cancel_event": None,
    "downloaded": 0,
}
_lock = threading.Lock()

bridge = MetaExtensionBridge()
_global_state = meta_accounts.GlobalState(get_meta_accounts_dir())
_launched_procs: dict[str, "subprocess.Popen"] = {}


def _log(msg: str) -> None:
    line = f"[META] {msg}"
    with _lock:
        _state["log_lines"].append(line)
        if len(_state["log_lines"]) > _MAX_LOG_LINES:
            _state["log_lines"] = _state["log_lines"][-_MAX_LOG_LINES:]


threading.Thread(
    target=meta_chrome_process.focus_loop,
    args=(lambda: bool(_state.get("running")), lambda: int(_state.get("downloaded", 0) or 0), _log),
    daemon=True,
).start()


# ─────────────────────────────────────────────────────────────────
# Bridge de extension: API publica para las rutas
# ─────────────────────────────────────────────────────────────────


def log_message(msg: str) -> None:
    _log(msg)


def learn_ext_state(state: dict) -> None:
    _global_state.learn(state)


def get_ext_state_safe() -> dict:
    return _global_state.safe_dict()


# ─────────────────────────────────────────────────────────────────
# Sesiones
# ─────────────────────────────────────────────────────────────────


def list_sessions() -> list[dict]:
    accounts_dir = get_meta_accounts_dir()
    meta_accounts.ensure_accounts(accounts_dir)
    rows = []
    for folder in sorted(accounts_dir.iterdir()):
        if not folder.is_dir():
            continue
        active = meta_accounts.is_authenticated(folder)
        ck = meta_accounts.load_cookies_dict(folder)
        user_id = ck.get("c_user", "")
        rows.append(
            {
                "name": folder.name,
                "active": active,
                "user": (f"uid:{user_id[:12]}" if user_id else ("sin sesion" if not active else "activa")),
                "has_cookies": bool(ck),
            }
        )
    return rows


def start_account_login(account_name: str) -> str:
    accounts_dir = get_meta_accounts_dir()
    folder = meta_accounts.account_dir(accounts_dir, account_name)
    folder.mkdir(parents=True, exist_ok=True)
    _log(f"[{folder.name}] Abriendo Chrome - inicia sesion en meta.ai y cierra la ventana.")

    def _run():
        meta_browser.login_account_managed(folder, folder.name, log=_log)

    threading.Thread(target=_run, daemon=True).start()
    return folder.name


def delete_session(account_name: str) -> None:
    meta_accounts.delete_session(get_meta_accounts_dir(), account_name)


# ─────────────────────────────────────────────────────────────────
# Batch worker: modo extension (DOM automation) -- default historico
# ─────────────────────────────────────────────────────────────────


def _batch_worker_ext(proj_dir: Path, prompt: str, slots: int, timeout_sec: int) -> None:
    """Chromium + extension: encola trabajos que la extension despacha via DOM."""
    images = _state.get("images", [])
    cancel_ev = _state.get("cancel_event")

    accounts_dir = get_meta_accounts_dir()
    acct_names = [f.name for f in sorted(accounts_dir.iterdir()) if f.is_dir()]

    vid_dir = proj_dir / "video"
    vid_dir.mkdir(parents=True, exist_ok=True)
    total = len(images)

    pending = []
    for i, img_meta in enumerate(images):
        stem = Path(img_meta["name"]).stem
        out_path = str(vid_dir / f"{stem}.mp4")
        if Path(out_path).exists():
            _log(f"[{i + 1}/{total}] {img_meta['name']} ya existe.")
            continue
        pending.append((i, img_meta, stem, out_path))

    _log(f"Meta AI Chromium: {len(pending)}/{total} imagen(es) - {slots} slot(s) paralelos")

    bridge.reset_for_new_batch(slots)

    accounts_valid = [n for n in acct_names if meta_accounts.is_authenticated(accounts_dir / n)]
    if not accounts_valid:
        accounts_valid = [acct_names[0]] if acct_names else ["cuenta1"]

    expected_accts = len(accounts_valid)
    _log("Esperando tabs existentes (max 1.5s)...")
    pre_start = time.time()
    ext_accounts = []
    while time.time() - pre_start < 1.5:
        if cancel_ev and cancel_ev.is_set():
            break
        ext_accounts = bridge.connected()
        if len(ext_accounts) >= expected_accts:
            _log(f"[OK] {len(ext_accounts)} tab(s) ya activas")
            break
        time.sleep(0.1)

    playwright_accounts = [
        n
        for n in accounts_valid
        if meta_chrome_process.chrome_type_for_profile(
            str(accounts_dir / n / "chromium_profile"), _launched_procs
        )
        == "playwright"
    ]
    if playwright_accounts:
        _log(f"Login en progreso para: {playwright_accounts} - esperando hasta 90s...")
        pw_wait = time.time()
        while time.time() - pw_wait < 90:
            if cancel_ev and cancel_ev.is_set():
                break
            still_pw = [
                n
                for n in playwright_accounts
                if meta_chrome_process.chrome_type_for_profile(
                    str(accounts_dir / n / "chromium_profile"), _launched_procs
                )
                == "playwright"
            ]
            if not still_pw:
                _log(f"[OK] Login finalizado en {int(time.time() - pw_wait)}s")
                time.sleep(2)
                break
            ext_accounts = bridge.connected()
            if len(ext_accounts) >= expected_accts:
                break
            time.sleep(2)

    if len(ext_accounts) >= expected_accts:
        _log(
            f"[OK] Extension ya conectada con {len(ext_accounts)} cuenta(s) - se usa eso, no se lanza Chromium"
        )
        need_launch = []
    else:
        already_running = [
            n
            for n in accounts_valid
            if meta_chrome_process.chrome_type_for_profile(
                str(accounts_dir / n / "chromium_profile"), _launched_procs
            )
            == "batch"
        ]
        need_launch = [
            n
            for n in accounts_valid
            if meta_chrome_process.chrome_type_for_profile(
                str(accounts_dir / n / "chromium_profile"), _launched_procs
            )
            == "none"
        ]
        if already_running:
            _log(f"Chrome batch detectado en: {already_running} - esperando hasta 5s...")
            pre2 = time.time()
            while time.time() - pre2 < 5:
                if cancel_ev and cancel_ev.is_set():
                    break
                ext_accounts = bridge.connected()
                if len(ext_accounts) >= len(already_running):
                    _log(f"[OK] {len(ext_accounts)} tab(s)")
                    break
                time.sleep(0.15)
            if not ext_accounts:
                _log("[WARNING] Chrome esta corriendo pero la extension no responde.")

    if need_launch:
        exe = chrome_launcher.find_chromium_exe()
        ext_dir = str(chrome_launcher.get_extension_dir())
        if not exe:
            _log("[ERROR] No se encontro Chrome/Chromium instalado.")
            _state.update(finished=True, running=False)
            return
        _log(f"Lanzando Chromium para: {need_launch} (1 ventana/cuenta)")
        for acct_name in need_launch:
            profile_dir = str(accounts_dir / acct_name / "chromium_profile")
            meta_chrome_process.clean_profile_for_fresh_start(profile_dir, log=_log)
            proc = meta_chrome_process.launch_chrome_with_extension(
                exe,
                profile_dir,
                [ext_dir],
                ["https://www.meta.ai/create"],
                extra_args=[
                    "--disable-features=PrivateNetworkAccessSendPreflights,"
                    "PrivateNetworkAccessRespectPreflightResults,BlockInsecurePrivateNetworkRequests",
                    "--disable-background-timer-throttling",
                    "--disable-renderer-backgrounding",
                    "--disable-backgrounding-occluded-windows",
                    "--disable-background-media-suspend",
                    "--disable-sync",
                    "--disable-translate",
                    "--disable-default-apps",
                    "--disable-component-extensions-with-background-pages",
                    "--no-pings",
                    "--metrics-recording-only",
                ],
            )
            _launched_procs[profile_dir] = proc
            _log(f"[{acct_name}] 1 ventana - 1 tab - batch={slots} imgs/mensaje")
        _log(f"[OK] {len(need_launch)} ventana(s) lanzadas | ext: {ext_dir}")

    min_needed = len(accounts_valid)
    if not ext_accounts or len(ext_accounts) < min_needed:
        wait_start = time.time()
        deadline = wait_start + 240
        _log("Esperando ventana(s) Chromium... (max 4 min)")
        while time.time() < deadline:
            if cancel_ev and cancel_ev.is_set():
                break
            ext_accounts = bridge.connected()
            if len(ext_accounts) >= min_needed:
                _log(f"[OK] {len(ext_accounts)} ventana(s) listas en {int(time.time() - wait_start)}s")
                break
            if ext_accounts and bridge.create_tabs():
                _log(f"[OK] {len(ext_accounts)}/{min_needed} ventana(s) en meta.ai - procediendo")
                break
            time.sleep(0.5)
        if not ext_accounts:
            _log("[ERROR] Ninguna tab Chromium se registro en 4 min. Verifica que este en meta.ai/create.")
            _state.update(finished=True, running=False)
            return

    ext_accounts = bridge.connected()
    create_tabs = bridge.create_tabs()
    if ext_accounts and not create_tabs:
        _log(f"{len(ext_accounts)} tab(s) conectada(s) pero aun en login/cargando. Esperando hasta 2 min...")
        login_wait_start = time.time()
        while time.time() - login_wait_start < 120:
            if cancel_ev and cancel_ev.is_set():
                _state.update(finished=True, running=False)
                return
            create_tabs = bridge.create_tabs()
            if create_tabs:
                _log(f"[OK] Sesion lista en {int(time.time() - login_wait_start)}s")
                break
            time.sleep(1)
        else:
            _log("[ERROR] Timeout: las sesiones siguen expiradas despues de 2 min.")
            _state.update(finished=True, running=False)
            return

    _log(f"{len(ext_accounts)} tab(s) activa(s) ({len(create_tabs)} en /create listos)")

    n_accounts = max(1, len(ext_accounts))
    concurrency = slots * n_accounts
    _log(f"Pipeline: {n_accounts} tab(s) x {slots} imgs/batch --> {concurrency} generaciones simultaneas")

    done_count = [0]
    count_lock = threading.Lock()

    dl_queue: queue.Queue = queue.Queue()
    dl_workers_n = 20
    dl_session = requests.Session()
    dl_session.headers.update(
        {"User-Agent": _META_UA, "Referer": "https://www.meta.ai/", "Accept": "video/mp4,video/*,*/*"}
    )
    dl_adapter = HTTPAdapter(pool_connections=dl_workers_n, pool_maxsize=dl_workers_n * 2, max_retries=3)
    dl_session.mount("https://", dl_adapter)
    dl_session.mount("http://", dl_adapter)

    def download_one(url: str, out_path: str, i: int, stem: str):
        for attempt in range(3):
            try:
                _log(f"[{i + 1}/{total}] Descargando: {url[:70]}...")
                r = dl_session.get(url, timeout=120, stream=True)
                r.raise_for_status()
                with open(out_path, "wb") as fh:
                    for chunk in r.iter_content(4 << 20):
                        if chunk:
                            fh.write(chunk)
                fsize = Path(out_path).stat().st_size if Path(out_path).exists() else 0
                if fsize < 1024:
                    raise RuntimeError(f"Archivo muy pequeno: {fsize} bytes")
                with count_lock:
                    done_count[0] += 1
                _state["downloaded"] = done_count[0]
                _log(f"[OK] [{i + 1}/{total}] {stem}.mp4 ({done_count[0]}/{total} listo(s))")
                return
            except Exception as exc:
                if attempt < 2:
                    time.sleep(1.5 * (attempt + 1))
                else:
                    _log(f"[ERROR] [{i + 1}/{total}] {stem} - Descarga: {exc}")

    def dl_worker():
        while True:
            item = dl_queue.get()
            if item is None:
                dl_queue.task_done()
                break
            try:
                download_one(*item)
            finally:
                dl_queue.task_done()

    dl_workers = [threading.Thread(target=dl_worker, daemon=True) for _ in range(dl_workers_n)]
    for w in dl_workers:
        w.start()

    pending_reqs = []
    for i, img_meta, stem, out_path in pending:
        rid, ev = bridge.enqueue_job(img_meta.get("path", ""), prompt)
        pending_reqs.append((ev, i, img_meta, stem, out_path, rid))

    _log(f"{len(pending_reqs)} job(s) pre-cargados en cola - {concurrency} tab(s) tomando 1 job cada vez")

    def collect_result(item, retry=0):
        ev, i, img_meta, stem, out_path, rid = item
        deadline = time.time() + timeout_sec
        grace_end = None
        wait_ticks = 0
        while not ev.wait(timeout=1.0):
            wait_ticks += 1
            if wait_ticks == 180 and not bridge.is_still_queued(rid):
                _log(f"[{i + 1}/{total}] {rid[:8]} sigue esperando (3 min)...")
            if cancel_ev and cancel_ev.is_set():
                if grace_end is None:
                    grace_end = time.time() + 300
                    _log(f"[{i + 1}/{total}] {rid[:8]} Detener recibido - esperando resultado (hasta 5 min)")
                if time.time() >= grace_end:
                    bridge.cancel_job(rid)
                    _log(f"[{i + 1}/{total}] {rid[:8]} cancelado (grace 5 min expirado)")
                    return
            if time.time() >= deadline:
                bridge.cancel_job(rid)
                _log(f"[ERROR] [{i + 1}/{total}] {stem} - Timeout extension")
                return

        result = bridge.pop_result(rid)
        if result is None:
            _log(f"[WARNING] [{i + 1}/{total}] {rid[:8]} evento sin resultado")
            return
        url = result.get("url") or ""
        err = result.get("error") or ""
        if url and out_path:
            dl_queue.put((url, out_path, i, stem))
        elif retry < 2 and not (cancel_ev and cancel_ev.is_set()):
            _log(f"[{i + 1}/{total}] {stem} - sin URL (intento {retry + 1}/2) reintentando...")
            new_rid, new_ev = bridge.enqueue_job(img_meta.get("path", ""), prompt)
            collect_result((new_ev, i, img_meta, stem, out_path, new_rid), retry + 1)
        else:
            _log(f"[ERROR] [{i + 1}/{total}] {stem} - {err if err else 'sin URL ni error'}")

    monitor_start = time.time()

    def progress_monitor():
        last_done = -1
        while not _state.get("finished"):
            time.sleep(20)
            if _state.get("finished"):
                break
            cur_done = done_count[0]
            n_dl_pending = dl_queue.qsize()
            elapsed = int(time.time() - monitor_start)
            if cur_done < total:
                change = f"+{cur_done - last_done}" if last_done >= 0 and cur_done > last_done else ""
                _log(
                    f"[{elapsed}s] {cur_done}/{total} descargados{change} - {n_dl_pending} descarga pendiente"
                )
            last_done = cur_done

    threading.Thread(target=progress_monitor, daemon=True).start()

    def verify_loop():
        while not _state.get("finished"):
            time.sleep(25)
            if _state.get("finished"):
                break
            meta_verify.verify_batch_fix(images, vid_dir, log=_log)

    threading.Thread(target=verify_loop, daemon=True).start()

    with ThreadPoolExecutor(max_workers=len(pending_reqs) or 1) as ex:
        futures = [ex.submit(collect_result, item) for item in pending_reqs]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                _log(f"[WARNING] Collector excepcion: {exc}")

    for _ in range(dl_workers_n):
        dl_queue.put(None)
    for w in dl_workers:
        w.join()

    meta_verify.verify_batch_fix(images, vid_dir, log=_log)

    _state.update(finished=True, running=False)
    _log(f"Meta AI finalizado: {done_count[0]}/{total} videos.")


# ─────────────────────────────────────────────────────────────────
# Batch worker: vibes.ai (Meta desplazo aqui la generacion de video, en
# reemplazo de meta.ai). Sin DOM, sin GraphQL manual: la extension hace
# fetch() directo a la API interna de vibes.ai con la cookie de sesion real
# del navegador -- el backend solo lanza/reusa la pestana y espera UN
# resultado con las URLs de los videos ya generados.
# ─────────────────────────────────────────────────────────────────


def _batch_worker_vibes(proj_dir: Path, prompt: str, slots: int, timeout_sec: int) -> None:
    """A diferencia de ext/http (que lanzan su propio Chromium con un perfil dedicado
    por cuenta), vibes.ai usa la sesion real del navegador que el usuario ya tiene
    abierto -- no tiene sentido lanzar un perfil nuevo en blanco, porque nunca vendria
    con sesion iniciada. Este worker solo espera a que la extension (cargada en el
    Chrome real del usuario, con una pestana en vibes.ai) se registre.

    Cada imagen se manda como un job independiente: la extension la adjunta como
    "ingredient" (imagen de referencia) en el compositor real de vibes.ai antes de
    escribir el prompt y generar -- igual que el usuario lo haria a mano."""
    images = _state.get("images", [])
    cancel_ev = _state.get("cancel_event")
    vid_dir = proj_dir / "video"
    vid_dir.mkdir(parents=True, exist_ok=True)
    total = len(images)

    _log(f"Vibes.ai: {total} imagen(es) - {slots} video(s) c/u - prompt: {prompt[:80]}")

    connected = vibes_bridge.connected_accounts()
    if not connected:
        _log(
            "Esperando a que la extension se conecte (abre/refresca una pestana en "
            "vibes.ai con sesion iniciada, max 60s)..."
        )
        wait_start = time.time()
        while time.time() - wait_start < 60:
            if cancel_ev and cancel_ev.is_set():
                _state.update(finished=True, running=False)
                return
            connected = vibes_bridge.connected_accounts()
            if connected:
                _log(f"[OK] Extension conectada en {int(time.time() - wait_start)}s")
                break
            time.sleep(1)
        if not connected:
            _log(
                "[ERROR] La extension no se conecto. Abre https://vibes.ai/ en tu "
                "navegador (con sesion iniciada) y verifica que la extension este "
                "activa y recargada, luego refresca esa pestana."
            )
            _state.update(finished=True, running=False)
            return

    if len(connected) > 1:
        _log(f"[OK] {len(connected)} cuentas de vibes.ai conectadas: reparto round-robin entre ellas.")
    session = requests.Session()
    session.headers.update({"User-Agent": _META_UA, "Referer": "https://vibes.ai/"})
    downloaded_total = 0
    dl_lock = threading.Lock()

    # La extension solo tiene UN compositor (una pestana real de vibes.ai), asi que el
    # "envio" de cada mensaje es secuencial de por si (lo serializa vibes_bridge.js con su
    # propia cola) -- pero la ESPERA de cada video no tiene por que bloquear el envio del
    # siguiente. Por eso encolamos varias imagenes a la vez (como meta.ai con sus multiples
    # ventanas Chromium) en vez de esperar el resultado de una antes de mandar la proxima.
    def process_one(i: int, img_meta: dict) -> None:
        nonlocal downloaded_total
        if cancel_ev and cancel_ev.is_set():
            return
        img_path = Path(img_meta.get("path", ""))
        try:
            img_bytes = img_path.read_bytes()
        except Exception as exc:
            _log(f"[ERROR] [{i + 1}/{total}] No se pudo leer {img_meta.get('name')}: {exc}")
            return
        mime = mimetypes.guess_type(img_path.name)[0] or "image/jpeg"
        account_hash = connected[i % len(connected)]

        rid = str(uuid_lib.uuid4())
        ev = vibes_bridge.register_result_waiter(rid)
        job = {
            "requestId": rid,
            "account": account_hash,
            "prompt": prompt,
            "slots": slots,
            "timeoutSec": timeout_sec,
            "projectName": f"{proj_dir.name}-{i + 1:03d}",
            "imageBase64": base64.b64encode(img_bytes).decode("ascii"),
            "imageMime": mime,
            "imageName": img_meta.get("name") or f"{i + 1:05d}.jpg",
        }
        vibes_bridge.enqueue_request(job)
        _log(f"[{i + 1}/{total}] Job encolado ({img_meta.get('name')}, cuenta={account_hash})")

        deadline = time.time() + timeout_sec + 30
        result = None
        while time.time() < deadline:
            if cancel_ev and cancel_ev.is_set():
                break
            ev.wait(timeout=2.0)
            ev.clear()
            result = vibes_bridge.try_pop_result(rid)
            if result is not None:
                break
        vibes_bridge.remove_from_queue(rid)
        vibes_bridge.cleanup_waiter(rid)

        if not result:
            _log(f"[ERROR] [{i + 1}/{total}] Sin respuesta de vibes.ai (timeout).")
            return
        if result.get("status") != 200 or result.get("error"):
            _log(f"[ERROR] [{i + 1}/{total}] vibes.ai: {result.get('error', 'fallo desconocido')}")
            return

        urls = result.get("videos") or []
        stem = Path(img_meta["name"]).stem
        for j, url in enumerate(urls):
            if cancel_ev and cancel_ev.is_set():
                break
            try:
                resp = session.get(url, timeout=120)
                resp.raise_for_status()
                suffix = f"_{j + 1}" if len(urls) > 1 else ""
                out_path = vid_dir / f"{stem}{suffix}.mp4"
                out_path.write_bytes(resp.content)
                with dl_lock:
                    downloaded_total += 1
                    _state["downloaded"] = downloaded_total
                _log(f"[{i + 1}/{total}] Descargado: {out_path.name}")
            except Exception as exc:
                _log(f"[ERROR] [{i + 1}/{total}] Descarga fallo para video {j + 1}: {exc}")

    # Sin tope artificial: el "envio" real ya lo serializa vibes_bridge.js con su
    # propia sendQueue (un solo compositor). Limitar los hilos de Python aqui solo
    # provoca que la imagen N+1 no se encole hasta que una de las N anteriores
    # termine su generacion COMPLETA (no solo el envio), causando pausas largas.
    concurrency = total or 1
    _log(f"Enviando {total} generacion(es) (envio serializado por la extension, espera en paralelo)...")
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(process_one, i, img_meta) for i, img_meta in enumerate(images)]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                _log(f"[WARNING] Excepcion en worker: {exc}")

    _log(f"Listo: {downloaded_total} video(s) descargados.")
    _state.update(finished=True, running=False)


# ─────────────────────────────────────────────────────────────────
# Batch worker: modo HTTP directo ("learn once, HTTP forever")
# ─────────────────────────────────────────────────────────────────


def _batch_worker_http(proj_dir: Path, prompt: str, slots: int, timeout_sec: int) -> None:
    images = _state.get("images", [])
    cancel_ev = _state.get("cancel_event")

    vid_dir = proj_dir / "video"
    vid_dir.mkdir(parents=True, exist_ok=True)
    total = len(images)

    pending = []
    for i, img_meta in enumerate(images):
        stem = Path(img_meta["name"]).stem
        pending.append((i, img_meta, stem, str(vid_dir / f"{stem}.mp4")))

    accounts_dir = get_meta_accounts_dir()
    accounts = meta_accounts.tokens_for_run(accounts_dir)
    if not accounts:
        _log("[ERROR] No hay cuentas autenticadas. Usa el boton Login en el panel de sesiones.")
        _state.update(finished=True, running=False)
        return

    n_accounts = len(accounts)
    concurrency = max(1, slots) * n_accounts
    _log(
        f"Meta AI HTTP Direct: {len(pending)}/{total} imagen(es) - "
        f"{concurrency} worker(s) ({slots} slot(s) x {n_accounts} cuenta(s))"
    )

    acct_states = []
    for acct_name, cookie_list in accounts:
        acct_folder = accounts_dir / acct_name
        acct_states.append((acct_name, cookie_list, acct_folder, meta_accounts.load_api_state(acct_folder)))

    for idx in range(len(acct_states)):
        acct_name, cookie_list, acct_folder, api_state_d = acct_states[idx]
        if "_lsd" not in api_state_d and cookie_list:
            try:
                sess_lsd = requests.Session()
                sess_lsd.cookies.update(meta_gql_client.cookies_for_requests(cookie_list))
                lsd_val = meta_gql_client.fetch_lsd(sess_lsd)
                if lsd_val:
                    api_state_d = dict(api_state_d)
                    api_state_d["_lsd"] = lsd_val
                    acct_states[idx] = (acct_name, cookie_list, acct_folder, api_state_d)
                    _log(f"[{acct_name}] LSD={lsd_val[:8]}...")
                else:
                    _log(f"[{acct_name}] [WARNING] LSD no disponible - sesion expirada o cuenta bloqueada")
            except Exception as exc:
                _log(f"[{acct_name}] [WARNING] LSD fetch error: {exc}")

    needs_capture = [
        idx
        for idx, (_, _, _, api_state_d) in enumerate(acct_states)
        if not meta_accounts.http_state_complete(api_state_d)
    ]

    if needs_capture:
        _log(f"{len(needs_capture)} cuenta(s) sin tokens API - capturando con Playwright headless...")
        try:
            from playwright.sync_api import sync_playwright

            pw_available = True
        except ImportError:
            pw_available = False
            _log("[WARNING] Playwright no esta instalado. Las cuentas sin tokens seran omitidas.")

        if pw_available and not (cancel_ev and cancel_ev.is_set()):
            remaining_pending = list(pending)
            with sync_playwright() as pw:
                pw_browser = pw.chromium.launch(headless=True)
                try:
                    for idx in needs_capture:
                        if not remaining_pending or (cancel_ev and cancel_ev.is_set()):
                            break
                        acct_name, cookie_list, acct_folder, api_state_d = acct_states[idx]
                        i, img_meta, stem, out_path = remaining_pending.pop(0)
                        img_path = img_meta.get("path", "")

                        _log(
                            f"[{acct_name}] [{i + 1}/{total}] {img_meta['name']} "
                            "(captura de tokens + generacion Playwright)..."
                        )
                        res = meta_browser.generate_playwright_intercept(
                            browser=pw_browser,
                            acct_folder=acct_folder,
                            cookie_list=cookie_list,
                            api_state=api_state_d,
                            prompt=prompt,
                            image_path=img_path,
                            out_path=out_path,
                            timeout_sec=timeout_sec,
                            slot_id=idx,
                            log=_log,
                        )
                        new_st = meta_accounts.load_api_state(acct_folder)
                        if api_state_d.get("_lsd") and "_lsd" not in new_st:
                            new_st = dict(new_st)
                            new_st["_lsd"] = api_state_d["_lsd"]
                        acct_states[idx] = (acct_name, cookie_list, acct_folder, new_st)

                        if res.get("url") or res.get("saved"):
                            _log(f"[OK] [{i + 1}/{total}] {stem}.mp4 (Playwright capture+gen)")
                        else:
                            _log(f"[ERROR] [{i + 1}/{total}] {stem} - {res.get('error', 'sin URL')}")
                            if meta_accounts.http_state_complete(acct_states[idx][3]):
                                _log(
                                    f"[{i + 1}/{total}] {stem} - tokens capturados, reintentando por HTTP..."
                                )
                                remaining_pending.insert(0, (i, img_meta, stem, out_path))
                finally:
                    pw_browser.close()
            pending = remaining_pending

        if not pending:
            _log("[OK] Todos los videos generados durante la captura de tokens.")
            _state.update(finished=True, running=False)
            return

    http_accts = [entry for entry in acct_states if meta_accounts.http_state_complete(entry[3])]
    if not http_accts:
        _log(
            "[ERROR] Ninguna cuenta tiene api_state completo para modo HTTP. "
            "Instala Playwright y vuelve a dar Iniciar."
        )
        _state.update(finished=True, running=False)
        return

    _log(f"HTTP phase: {len(pending)} job(s) - {len(http_accts)} cuenta(s) - {concurrency} worker(s)")

    done_count = [0]
    job_queue: queue.Queue = queue.Queue()
    for item in pending:
        job_queue.put(item)

    monitor_start = time.time()

    def http_progress_monitor():
        while not _state.get("finished"):
            time.sleep(15)
            if _state.get("finished"):
                break
            cur = done_count[0]
            rem = job_queue.qsize()
            elapsed = int(time.time() - monitor_start)
            if cur < total or rem > 0:
                _log(f"[{elapsed}s] {cur}/{total} completados - {rem} en cola")

    threading.Thread(target=http_progress_monitor, daemon=True).start()

    def http_worker(worker_idx: int):
        acct_name, cookie_list, _af, api_state_d = http_accts[worker_idx % len(http_accts)]
        while True:
            if cancel_ev and cancel_ev.is_set():
                break
            try:
                i, img_meta, stem, out_path = job_queue.get_nowait()
            except queue.Empty:
                break
            try:
                img_path = img_meta.get("path", "")
                _log(f"[W{worker_idx}|{acct_name}] [{i + 1}/{total}] {img_meta['name']}...")
                res = meta_gql_client.generate_http(
                    cookie_list=cookie_list,
                    api_state=api_state_d,
                    prompt=prompt,
                    image_path=img_path,
                    out_path=out_path,
                    timeout_sec=timeout_sec,
                    slot_id=worker_idx,
                    send_msg_tpl_fallback=_global_state.get("send_msg_tpl"),
                    log=_log,
                )
                if res.get("saved") or res.get("url"):
                    done_count[0] += 1
                    _log(
                        f"[OK] [W{worker_idx}|{acct_name}] [{i + 1}/{total}] {stem}.mp4 ({done_count[0]}/{total})"
                    )
                else:
                    _log(
                        f"[ERROR] [W{worker_idx}|{acct_name}] [{i + 1}/{total}] {stem} - "
                        f"{res.get('error', 'sin URL')}"
                    )
            except Exception as exc:
                _log(f"[WARNING] [W{worker_idx}|{acct_name}] Excepcion en job [{i + 1}]: {exc}")
            finally:
                try:
                    job_queue.task_done()
                except Exception:
                    pass

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = [executor.submit(http_worker, w) for w in range(concurrency)]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                _log(f"[WARNING] Worker excepcion: {exc}")

    _state.update(finished=True, running=False)
    _log(f"Meta AI HTTP finalizado: {done_count[0]}/{total} videos.")


# ─────────────────────────────────────────────────────────────────
# API publica
# ─────────────────────────────────────────────────────────────────


def start_batch(
    project_name: str, images: list[tuple[str, object]], prompt: str, slots: int, mode: str, timeout_sec: int
) -> dict:
    """`images` es una lista de (filename, file_storage) donde file_storage tiene .save(path).
    `slots` determina cuantos videos se generan por cada imagen."""
    name = sanitize_name(project_name) if project_name else ""
    if not name:
        raise ValueError("Selecciona un proyecto antes de animar.")

    mode = (mode or "ext").strip().lower()
    is_vibes = mode == "vibes"
    if not images:
        raise ValueError("No se recibieron imagenes")

    proj_dir = project_repository.create_project(name)
    img_dir = proj_dir / "imagen"
    images_meta = []
    for i, (filename, file_storage) in enumerate(images):
        ext = Path(filename or "").suffix or ".jpg"
        # Guardar con nombre unico por indice (no por nombre original) -- evita que
        # dos imagenes subidas con el mismo nombre colapsen en un solo archivo.
        dest = img_dir / f"{i + 1:05d}_src{ext}"
        file_storage.save(str(dest))
        images_meta.append({"index": i + 1, "name": filename or f"{i + 1:05d}.jpg", "path": str(dest)})

    if is_vibes:
        worker_fn = _batch_worker_vibes
        mode_label = "Vibes.ai (API)"
    elif mode in ("ext", "dom", "playwright"):
        worker_fn = _batch_worker_ext
        mode_label = "Playwright DOM"
    else:
        worker_fn = _batch_worker_http
        mode_label = "http (directo)"

    (proj_dir / "guion").mkdir(parents=True, exist_ok=True)
    (proj_dir / "guion" / "config_meta.txt").write_text(
        f"prompt: {prompt}\nslots: {slots}\nmode: {mode}\n", encoding="utf-8"
    )

    cancel_ev = threading.Event()
    _state.update(
        {
            "running": True,
            "log_lines": [],
            "finished": False,
            "project_dir": str(proj_dir),
            "images": images_meta,
            "total": len(images_meta) * slots if is_vibes else len(images_meta),
            "cancel_event": cancel_ev,
            "downloaded": 0,
        }
    )
    threading.Thread(target=worker_fn, args=(proj_dir, prompt, slots, timeout_sec), daemon=True).start()

    return {
        "ok": True,
        "pid": f"meta-{int(time.time())}",
        "mode": mode_label,
        "project_dir": str(proj_dir),
        "project_name": name,
    }


def stop() -> None:
    ev = _state.get("cancel_event")
    if ev:
        ev.set()
    _state.update(running=False, finished=True)
    cleared = bridge.clear_pending_queue()
    _log(
        f"Detener recibido - cola vaciada ({cleared} items). Descargando resultados que ya llegaron (hasta 5 min)."
    )


def get_log_state(offset: int) -> dict:
    lines = _state["log_lines"][offset:]
    video_dir = Path(_state["project_dir"]) / "video" if _state["project_dir"] else None
    try:
        videos_done = len(list(video_dir.glob("*.mp4"))) if video_dir and video_dir.is_dir() else 0
    except Exception:
        videos_done = 0
    return {
        "lines": lines,
        "next_offset": offset + len(lines),
        "finished": bool(_state["finished"]),
        "videos_done": videos_done,
        "videos_total": int(_state.get("total") or 0),
    }


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
    if _state["project_dir"]:
        video_dir = Path(_state["project_dir"]) / "video"
        candidate = (video_dir / filename).resolve()
        try:
            candidate.relative_to(video_dir.resolve())
        except ValueError:
            return None
        return candidate
    return None


def _active_video_dir(project_name: str) -> Path | None:
    if project_name:
        return project_repository.project_dir(project_name) / "video"
    if _state["project_dir"]:
        return Path(_state["project_dir"]) / "video"
    return None


def build_videos_zip(project_name: str) -> tuple[BytesIO, str] | None:
    video_dir = _active_video_dir(project_name)
    if not video_dir:
        return None
    videos = sorted(video_dir.glob("*.mp4")) if video_dir.exists() else []
    if not videos:
        return None
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for v in videos:
            zf.write(str(v), v.name)
    buf.seek(0)
    proj_label = sanitize_name(project_name) if project_name else Path(_state["project_dir"]).name
    return buf, f"{proj_label}_videos_meta.zip"


def open_videos_folder(project_name: str) -> Path:
    video_dir = _active_video_dir(project_name)
    if not video_dir:
        raise ValueError("Sin proyecto activo")
    video_dir.mkdir(parents=True, exist_ok=True)
    open_folder(str(video_dir))
    return video_dir


def launch_chrome(account_name: str, slots: int) -> dict:
    """Lanza Chrome con la extension cargada como worker permanente (N pestanas)."""
    folder_name = sanitize_name(account_name) or "cuenta1"
    n_slots = max(1, min(slots, 10))

    ext_dir = chrome_launcher.get_extension_dir()
    if not (ext_dir / "meta_bridge.js").is_file():
        raise FileNotFoundError(f"meta_bridge.js no encontrado en: {ext_dir}")

    exe = chrome_launcher.find_chromium_exe()
    if not exe:
        raise FileNotFoundError("Chrome/Edge no encontrado. Instala Google Chrome.")

    accounts_dir = get_meta_accounts_dir()
    profile_dir = str(accounts_dir / folder_name / "chromium_profile")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    extensions = [str(ext_dir)]
    ck_file = accounts_dir / folder_name / "cookies_auto.json"
    if ck_file.exists() and ck_file.stat().st_size > 100:
        injector_dir = _build_cookie_injector(ck_file)
        if injector_dir:
            extensions.append(injector_dir)

    urls = ["https://www.meta.ai/create"] * n_slots
    _log(f"[{folder_name}] Lanzando Chrome - {n_slots} pestana(s) - {Path(exe).name}")

    def _monitor():
        proc = None
        try:
            proc = meta_chrome_process.launch_chrome_with_extension(exe, profile_dir, extensions, urls)
            meta_chrome_process.register_chrome_pid(proc.pid)
            _log(f"[OK] [{folder_name}] Chrome abierto - si ves login, inicia sesion en meta.ai")
            _log(f"Extension registrara {n_slots} slot(s) automaticamente")
            start = time.time()
            proc.wait()
            elapsed = time.time() - start
            if elapsed < 8:
                _log(
                    f"[WARNING] [{folder_name}] Chrome se cerro en {elapsed:.1f}s - "
                    "posiblemente el modo de desarrollador no esta activado."
                )
                _log("Usa el boton 'Modo Dev' para abrir chrome://extensions y activar el toggle.")
            else:
                _log(f"[{folder_name}] Chrome cerrado")
        except Exception as exc:
            _log(f"[ERROR] [{folder_name}] Error lanzando Chrome: {exc}")
        finally:
            if proc is not None:
                meta_chrome_process.unregister_chrome_pid(proc.pid)

    threading.Thread(target=_monitor, daemon=True).start()
    return {
        "ok": True,
        "slots": n_slots,
        "message": f"Chrome lanzando para {folder_name} ({n_slots} pestanas)",
    }


def _build_cookie_injector(ck_file: Path) -> str | None:
    """Extension minima que inyecta cookies guardadas y recarga las tabs de meta.ai."""
    import json
    import tempfile

    try:
        raw = json.loads(ck_file.read_text(encoding="utf-8"))
        meta_ck = [
            c
            for c in raw
            if isinstance(c, dict)
            and (
                "meta.ai" in c.get("domain", "")
                or c.get("name", "") in ("ecto_1_sess", "datr", "c_user", "sb", "xs", "fr", "ps_l", "ps_n")
            )
        ]
        if not meta_ck:
            return None
        ci_dir = Path(tempfile.mkdtemp(prefix="vf_ci_"))
        (ci_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "manifest_version": 3,
                    "name": "VF Cookie Injector",
                    "version": "1.0",
                    "permissions": ["cookies", "tabs"],
                    "host_permissions": ["https://*.meta.ai/*"],
                    "background": {"service_worker": "bg.js"},
                }
            ),
            encoding="utf-8",
        )
        (ci_dir / "bg.js").write_text(
            "const ck=" + json.dumps(meta_ck, separators=(",", ":")) + ";\n"
            "var n=0;\n"
            "function done(){n++;if(n===ck.length){\n"
            "  chrome.tabs.query({url:'https://www.meta.ai/*'},function(ts){\n"
            "    ts.forEach(function(t){chrome.tabs.reload(t.id);});\n"
            "  });\n"
            "}}\n"
            "ck.forEach(function(c){\n"
            "  chrome.cookies.set({\n"
            "    url:'https://www.meta.ai',name:c.name||'',value:c.value||'',\n"
            "    domain:c.domain||'.meta.ai',path:c.path||'/',\n"
            "    secure:!!c.secure,httpOnly:!!c.httpOnly,\n"
            "    sameSite:c.sameSite||'unspecified'\n"
            "  },done);\n"
            "});",
            encoding="utf-8",
        )
        _log(f"Inyector de cookies ({len(meta_ck)} cookies) + recarga automatica")
        return str(ci_dir)
    except Exception:
        return None


def open_devmode(account_name: str) -> dict:
    """Abre Chrome con el perfil de la cuenta pero sin extension, en chrome://extensions."""
    folder_name = sanitize_name(account_name) or "cuenta1"
    exe = chrome_launcher.find_chromium_exe()
    if not exe:
        raise FileNotFoundError("Chrome/Edge no encontrado. Instala Google Chrome.")

    accounts_dir = get_meta_accounts_dir()
    profile_dir = str(accounts_dir / folder_name / "chromium_profile")
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    import subprocess

    args = [
        exe,
        f"--user-data-dir={profile_dir}",
        "--no-first-run",
        "--no-default-browser-check",
        "chrome://extensions",
    ]
    _log(f"[{folder_name}] Abriendo Chrome en chrome://extensions (sin extension)")

    def _run():
        try:
            proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            proc.wait()
            _log(f"[{folder_name}] Chrome (modo dev) cerrado")
        except Exception as exc:
            _log(f"[ERROR] [{folder_name}] Error abriendo Chrome para modo dev: {exc}")

    threading.Thread(target=_run, daemon=True).start()
    return {"ok": True, "message": f"Chrome abierto en chrome://extensions para {folder_name}"}
