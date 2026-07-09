"""Automatizacion real de Chromium para Flow: lanza un browser con la extension
cargada (--load-extension) para que el usuario inicie sesion, con las mismas
protecciones anti-deteccion que Grok/Whisk/Meta ya usan. Solo se usa como fallback
cuando no hay un Chrome real del usuario ya conectado al bridge (ver
flow_animation_service._pick_account, que siempre prioriza Chrome real)."""

import json
import os
import threading
import time
import uuid
from pathlib import Path

from src.infrastructure.ai_providers.chrome_launcher import find_chromium_exe, get_extension_dir
from src.utils.logger import get_logger
from src.utils.paths import get_flow_profiles_dir

logger = get_logger(__name__)

FLOW_URL = "https://labs.google/fx/tools/flow"

_pw_start_sem = threading.Semaphore(1)

_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/136.0.0.0 Safari/537.36"
)


def profile_dir(account_idx: int) -> Path:
    return get_flow_profiles_dir() / f"flow_profile_{account_idx}"


def reset_profile_fingerprint(
    profile_path: str, account_idx: int = 0, reset_rate_limit: bool = False, log=None
) -> None:
    """Resetea el fingerprint del perfil (cookies de tracking, localStorage/IndexedDB
    de reCAPTCHA, client_id). reset_rate_limit=True tambien limpia cookies de sesion
    de aisandbox-pa (para recuperarse de un 429 persistente)."""
    default_dir = os.path.join(profile_path, "Default")
    if not os.path.isdir(default_dir):
        return

    cookies_db = os.path.join(default_dir, "Network", "Cookies")
    if not os.path.isfile(cookies_db):
        cookies_db = os.path.join(default_dir, "Cookies")
    if os.path.isfile(cookies_db):
        try:
            import sqlite3

            conn = sqlite3.connect(cookies_db, timeout=5)
            cur = conn.cursor()
            if reset_rate_limit:
                cur.execute(
                    """
                    DELETE FROM cookies
                    WHERE host_key LIKE '%aisandbox%'
                       OR host_key LIKE '%labs.google%'
                       OR host_key LIKE '%apis.google%'
                       OR (host_key LIKE '%google%' AND name IN (
                           'NID','SOCS','AEC','__utmz','_ga',
                           '__Secure-3PAPISID','__Secure-3PSID',
                           'HSID','SSID','APISID','SAPISID'
                       ))
                """
                )
            else:
                cur.execute(
                    """
                    DELETE FROM cookies
                    WHERE host_key LIKE '%labs.google%'
                       OR host_key LIKE '%aisandbox%'
                       OR host_key LIKE '%apis.google%'
                       OR (host_key LIKE '%google%' AND name IN ('NID','SOCS','AEC','__utmz','_ga'))
                """
                )
            deleted = cur.rowcount
            conn.commit()
            conn.close()
            if deleted > 0 and log:
                log(
                    f"[Flow] Perfil {account_idx}: {deleted} cookies limpiadas "
                    f"({'rate limit' if reset_rate_limit else 'reCAPTCHA'})"
                )
        except Exception:
            pass

    ldb_dir = os.path.join(default_dir, "Local Storage", "leveldb")
    if os.path.isdir(ldb_dir):
        import glob

        for ldb in glob.glob(os.path.join(ldb_dir, "*")):
            try:
                with open(ldb, "rb") as f:
                    content = f.read(512)
                if (
                    b"labs.google" in content
                    or b"aisandbox" in content
                    or b"GCAP" in content
                    or b"recaptcha" in content
                ):
                    os.remove(ldb)
            except Exception:
                pass

    import glob
    import shutil

    for pat in ("*labs.google*", "*aisandbox*"):
        for idb in glob.glob(os.path.join(default_dir, "IndexedDB", pat)):
            try:
                shutil.rmtree(idb, ignore_errors=True)
            except Exception:
                pass

    ls_path = os.path.join(profile_path, "Local State")
    ls = {}
    if os.path.isfile(ls_path):
        try:
            with open(ls_path, encoding="utf-8") as f:
                ls = json.load(f)
        except Exception:
            pass
    ls.setdefault("user_experience_metrics", {})["client_id"] = str(uuid.uuid4())
    try:
        with open(ls_path, "w", encoding="utf-8") as f:
            json.dump(ls, f)
    except Exception:
        pass

    for nf in ("Network Persistent State", "TransportSecurity"):
        try:
            os.remove(os.path.join(default_dir, nf))
        except Exception:
            pass


def playwright_login(account_idx: int, log, on_closed) -> None:
    """Abre Chromium con la extension de Flow cargada para que el usuario inicie
    sesion. Bloqueante -- correr en un hilo. on_closed() se llama cuando el browser
    se cierra (por cualquiera de los 3 mecanismos de deteccion: evento de Playwright,
    watchdog de PID via psutil, o paginas vacias -- ninguno es 100% confiable solo
    en un .exe compilado con PyInstaller, de ahi la triple redundancia)."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log(f"[Flow Acc{account_idx + 1}] [ERROR] Playwright no instalado.")
        on_closed()
        return

    ext_dir = str(get_extension_dir())
    if not os.path.isfile(os.path.join(ext_dir, "manifest.json")):
        log(f"[Flow Acc{account_idx + 1}] [ERROR] manifest.json no encontrado en: {ext_dir}")
        on_closed()
        return

    exe = find_chromium_exe()
    if not exe:
        log(
            f"[Flow Acc{account_idx + 1}] [ERROR] No se encontro Chrome/Chromium. "
            f"Ejecuta: python -m playwright install chromium"
        )
        on_closed()
        return

    profile_path = str(profile_dir(account_idx))
    default_dir = os.path.join(profile_path, "Default")

    # Limpieza del perfil (no-fatal -- si falla, igual se lanza Chromium). Solo se
    # borran archivos de sesion (evita el banner "restore from crash"); NUNCA se
    # tocan Visited Links/Trust Tokens/Local Storage/IndexedDB, porque reCAPTCHA
    # Enterprise necesita esos datos para confiar en la sesion -- borrarlos hace
    # que el perfil parezca "fresco" y dispara PUBLIC_ERROR_UNUSUAL_ACTIVITY.
    try:
        os.makedirs(default_dir, exist_ok=True)
        for sl in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
            try:
                os.remove(os.path.join(profile_path, sl))
            except Exception:
                pass
        for sf in ("Last Session", "Last Tabs", "Current Session", "Current Tabs", "Last Browser"):
            try:
                os.remove(os.path.join(default_dir, sf))
            except Exception:
                pass
        net_dir = os.path.join(default_dir, "Network")
        for f in ("Reporting and NEL", "Reporting and NEL-journal", "Network Persistent State"):
            try:
                os.remove(os.path.join(net_dir, f))
            except Exception:
                pass
        ls_path = os.path.join(profile_path, "Local State")
        if os.path.isfile(ls_path):
            try:
                with open(ls_path, encoding="utf-8") as fh:
                    ls = json.load(fh)
                ls.setdefault("user_experience_metrics", {})["client_id"] = str(uuid.uuid4())
                with open(ls_path, "w", encoding="utf-8") as fh:
                    json.dump(ls, fh)
            except Exception:
                pass
        ext_folder = os.path.join(default_dir, "Extensions")
        if os.path.isdir(ext_folder):
            import shutil

            try:
                shutil.rmtree(ext_folder, ignore_errors=True)
            except Exception:
                pass
        os.makedirs(os.path.join(default_dir, "Network"), exist_ok=True)
        prefs_path = os.path.join(default_dir, "Preferences")
        prefs = {}
        if os.path.isfile(prefs_path):
            try:
                with open(prefs_path, encoding="utf-8") as fh:
                    prefs = json.load(fh)
            except Exception:
                pass
        prefs.setdefault("profile", {}).update({"exit_type": "Normal", "exited_cleanly": True})
        prefs.setdefault("session", {}).update({"restore_on_startup": 4, "startup_urls": [FLOW_URL]})
        try:
            with open(prefs_path, "w", encoding="utf-8") as fh:
                json.dump(prefs, fh)
        except Exception:
            pass
    except Exception as exc:
        log(f"[Flow Acc{account_idx + 1}] limpieza perfil error (no-fatal): {exc}")

    log(f"[Flow Acc{account_idx + 1}] Abriendo Chromium...")

    try:
        # Serializar arranque: cada perfil espera su turno para lanzar Playwright,
        # y se libera apenas Chrome esta abierto y estable (no al terminar la sesion).
        _pw_start_sem.acquire()
        sem_released = [False]

        def _release_sem():
            if not sem_released[0]:
                sem_released[0] = True
                _pw_start_sem.release()

        with sync_playwright() as pw:
            ctx = pw.chromium.launch_persistent_context(
                profile_path,
                headless=False,
                executable_path=exe,
                ignore_default_args=["--disable-extensions", "--enable-automation"],
                args=[
                    f"--load-extension={ext_dir}",
                    f"--disable-extensions-except={ext_dir}",
                    "--disable-blink-features=AutomationControlled",
                    "--exclude-switches=enable-automation",
                    "--disable-automation",
                    f"--user-agent={_UA}",
                    # Sin estas flags, Chrome 98+ bloquea fetch/WebSocket a loopback
                    # desde https://labs.google (Private Network Access policy),
                    # y la extension no puede hablar con el bridge local.
                    "--disable-features=PrivateNetworkAccessSendPreflights,"
                    "PrivateNetworkAccessRespectPreflightResults,"
                    "BlockInsecurePrivateNetworkRequests",
                    "--no-sandbox",
                    "--disable-session-crashed-bubble",
                    "--hide-crash-restore-bubble",
                    "--disable-background-mode",
                ],
            )
            log(f"[Flow Acc{account_idx + 1}] Chromium abierto")
            _release_sem()

            try:
                ctx.add_init_script(
                    "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
                    "try{delete navigator.__proto__.webdriver;}catch(_){}"
                    "if(typeof window.chrome==='undefined'){"
                    "  window.chrome={runtime:{},app:{isInstalled:false},"
                    "  loadTimes:function(){},csi:function(){},cast:{}};"
                    "}"
                )
            except Exception:
                pass

            try:
                page = ctx.pages[0] if ctx.pages else ctx.new_page()
                if FLOW_URL not in (page.url or ""):
                    page.goto(FLOW_URL, wait_until="domcontentloaded", timeout=30000)
            except Exception:
                pass

            closed_ev = threading.Event()
            ctx.on("close", lambda: closed_ev.set())

            chrome_pid_found = [None]
            prof_norm = profile_path.lower().replace("\\", "/")

            def _find_pid_early():
                try:
                    import psutil

                    for _ in range(12):
                        if closed_ev.is_set():
                            return
                        for p in psutil.process_iter(["pid", "cmdline"]):
                            try:
                                cmd_n = " ".join(p.info.get("cmdline") or []).lower().replace("\\", "/")
                                if prof_norm in cmd_n and "--type=" not in cmd_n:
                                    chrome_pid_found[0] = p.pid
                                    log(f"[Flow Acc{account_idx + 1}] PID detectado: {p.pid}")
                                    return
                            except Exception:
                                pass
                        time.sleep(1)
                except Exception:
                    pass

            threading.Thread(target=_find_pid_early, daemon=True).start()

            def _psutil_watchdog():
                for _ in range(30):
                    if closed_ev.is_set():
                        return
                    if chrome_pid_found[0]:
                        break
                    time.sleep(0.5)
                if chrome_pid_found[0]:
                    try:
                        import psutil

                        psutil.Process(chrome_pid_found[0]).wait()
                    except Exception:
                        pass
                    log(f"[Flow Acc{account_idx + 1}] PID {chrome_pid_found[0]} termino.")
                    closed_ev.set()
                else:
                    try:
                        import psutil

                        while not closed_ev.is_set():
                            time.sleep(3)
                            still_alive = False
                            for p in psutil.process_iter(["pid", "cmdline"]):
                                try:
                                    cmd_n = " ".join(p.info.get("cmdline") or []).lower().replace("\\", "/")
                                    if prof_norm in cmd_n and "--type=" not in cmd_n:
                                        still_alive = True
                                        break
                                except Exception:
                                    pass
                            if not still_alive:
                                log(f"[Flow Acc{account_idx + 1}] Watchdog polling: Chrome cerrado.")
                                closed_ev.set()
                    except ImportError:
                        pass
                    except Exception:
                        closed_ev.set()

            threading.Thread(target=_psutil_watchdog, daemon=True).start()

            def _pages_watcher():
                for _ in range(30):
                    if closed_ev.is_set():
                        return
                    try:
                        if ctx.pages:
                            break
                    except Exception:
                        return
                    time.sleep(0.5)
                while not closed_ev.is_set():
                    time.sleep(1)
                    try:
                        n = len(ctx.pages)
                    except Exception:
                        closed_ev.set()
                        return
                    if n == 0:
                        time.sleep(3)
                        try:
                            if len(ctx.pages) == 0:
                                log(f"[Flow Acc{account_idx + 1}] Ventana cerrada (0 paginas).")
                                closed_ev.set()
                        except Exception:
                            closed_ev.set()
                        return

            threading.Thread(target=_pages_watcher, daemon=True).start()
            closed_ev.wait()

            on_closed()
            log(f"[Flow Acc{account_idx + 1}] Chromium cerrado.")

    except Exception as exc:
        try:
            _release_sem()
        except Exception:
            pass
        logger.exception("[Flow Acc%d] excepcion en playwright_login", account_idx + 1)
        log(f"[Flow Acc{account_idx + 1}] EXCEPCION: {exc}")
        on_closed()
