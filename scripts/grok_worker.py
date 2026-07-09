#!/usr/bin/env python3
"""
grok_worker.py — Multi-cuenta Grok Animator (CLI)
Las imagenes se procesan ordenadas por fecha de creacion (mas antigua primero).
El video de salida usa el mismo stem que la imagen: img_00001.jpg --> img_00001.mp4

Uso:
  python scripts/grok_worker.py /fotos --slots 3 --prompt "Cinematic slow zoom"
  python scripts/grok_worker.py /fotos --slots 3 --login   <- primer uso
"""
import argparse
import json
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from queue import Empty, Queue

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.infrastructure.ai_providers import grok_service
from src.utils.logger import get_logger, setup_logging
from src.utils.paths import get_grok_accounts_dir, get_grok_downloads_dir

setup_logging()
logger = get_logger(__name__)


def _worker(client, queue, total, success_count, lock, output_dir, pending_file):
    while True:
        try:
            idx, img = queue.get_nowait()
        except Empty:
            break
        dest = output_dir / f"{img.stem}.mp4"
        if dest.exists() and dest.stat().st_size > 10_000:
            logger.info("[%s] [%03d] Ya existe (%dKB) - skip", client.label, idx, dest.stat().st_size // 1024)
            with lock:
                success_count[0] += 1
            queue.task_done()
            continue
        logger.info("[%s] [%03d/%d] %s", client.label, idx, total, img.name)
        try:
            url = client.animate(img)
            if url:
                if client.download(url, dest, pending_file):
                    with lock:
                        success_count[0] += 1
            else:
                logger.warning("[%s] [%03d] Sin URL de video", client.label, idx)
        except Exception as exc:
            logger.error("[%s] [%03d]: %s", client.label, idx, exc)
        finally:
            queue.task_done()


def main():
    p = argparse.ArgumentParser(
        description="Grok Multi-Account Animator - orden por fecha de creacion",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    p.add_argument("images", help="Carpeta con imagenes (se ordenan por fecha de creacion)")
    p.add_argument(
        "--prompt", default="Animate this image with smooth natural motion", help="Prompt de animacion"
    )
    p.add_argument(
        "--aspect-ratio",
        default="2:3",
        choices=["1:1", "16:9", "9:16", "4:3", "3:4", "2:3", "3:2"],
        help="Aspect ratio del video (default: 2:3)",
    )
    p.add_argument("--video-length", type=int, default=6, help="Duracion en segundos (default: 6)")
    p.add_argument(
        "--resolution", default="480p", choices=["480p", "720p", "1080p"], help="Resolucion (default: 480p)"
    )
    p.add_argument(
        "--login", action="store_true", help="Re-login de todas las cuentas (abre browser por cuenta)"
    )
    p.add_argument(
        "--output-dir", default="", help="Carpeta destino para los .mp4 (default: AppData/grok_downloads)"
    )
    p.add_argument(
        "--slots",
        type=int,
        default=1,
        metavar="N",
        help=(
            "Videos en paralelo POR cuenta [1-12, default: 1]\n"
            "  --slots 1  --> 1 video/cuenta (mas estable)\n"
            "  --slots 3  --> 3 videos/cuenta (recomendado)\n"
            "  --slots 12 --> maximo permitido\n"
            "Total = cuentas x slots (ej: 3 cuentas x 3 = 9 en paralelo)"
        ),
    )
    p.add_argument("--filter-file", default="", help="JSON con lista de nombres de archivos a procesar")
    args = p.parse_args()

    if not 1 <= args.slots <= grok_service.SLOTS_MAX:
        p.error(f"--slots debe estar entre 1 y {grok_service.SLOTS_MAX} (ingresaste: {args.slots})")

    output_dir = Path(args.output_dir).resolve() if args.output_dir else get_grok_downloads_dir()
    output_dir.mkdir(parents=True, exist_ok=True)
    pending_file = output_dir / "pending_downloads.txt"

    accounts_dir = get_grok_accounts_dir()
    account_folders = sorted([d for d in accounts_dir.iterdir() if d.is_dir()])
    if not account_folders:
        for i in range(1, 4):
            (accounts_dir / f"account_{i}").mkdir(parents=True, exist_ok=True)
        account_folders = sorted([d for d in accounts_dir.iterdir() if d.is_dir()])
        logger.warning("Se creo %s con cuentas base: account_1..account_3", accounts_dir)

    if args.login:
        for folder in account_folders:
            grok_service.login_account(folder)

    all_clients = []
    for folder in account_folders:
        all_clients.extend(
            grok_service.make_clients(
                folder,
                args.slots,
                args.prompt,
                args.aspect_ratio,
                args.video_length,
                args.resolution,
                output_dir,
            )
        )
    if not all_clients:
        logger.error("Sin clientes disponibles. Ejecuta con --login primero.")
        sys.exit(1)

    images = grok_service.get_images(args.images)
    if not images:
        sys.exit(1)

    if args.filter_file:
        try:
            names = json.loads(Path(args.filter_file).read_text())
            allowed = {Path(n).stem for n in names} | {Path(n).name for n in names}
            filtered = [img for img in images if img.stem in allowed or img.name in allowed]
            logger.info("Filtrando: %d/%d imagenes", len(filtered), len(images))
            if filtered:
                images = filtered
        except Exception as exc:
            logger.warning("--filter-file ignorado: %s", exc)

    total = len(images)

    fp = grok_service.http_browser_fingerprint()
    logger.info("Cliente HTTP: Chrome 124 / sec-ch-ua-platform %s", fp["sec_ch_ua_platform"])
    logger.info("Imagenes  : %d (ordenadas por fecha de creacion)", total)
    logger.info(
        "Cuentas   : %d x %d slot(s) = %d en paralelo", len(account_folders), args.slots, len(all_clients)
    )
    logger.info("Slots     : %s", [c.label for c in all_clients])
    logger.info("Prompt    : %s", args.prompt[:60])
    logger.info("Aspect    : %s | %ss | %s", args.aspect_ratio, args.video_length, args.resolution)
    logger.info("Salida    : %s", output_dir)

    queue = Queue()
    for idx, img in enumerate(images, 1):
        queue.put((idx, img))

    success_count = [0]
    lock = threading.Lock()

    with ThreadPoolExecutor(max_workers=len(all_clients)) as ex:
        futures = [
            ex.submit(_worker, c, queue, total, success_count, lock, output_dir, pending_file)
            for c in all_clients
        ]
        for f in as_completed(futures):
            try:
                f.result()
            except Exception as exc:
                logger.error("Worker crash: %s", exc)
    queue.join()

    logger.info("[OK] Completado: %d/%d videos en %s", success_count[0], total, output_dir)


if __name__ == "__main__":
    main()
