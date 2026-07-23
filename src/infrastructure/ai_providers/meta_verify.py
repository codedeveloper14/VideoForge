import subprocess
import tempfile
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from src.utils.logger import get_logger

logger = get_logger(__name__)

# Umbral empirico de hash de 64 bits -- bits distintos permitidos para considerar match.
MATCH_THRESHOLD = 14


def _NoOpLog(msg: str) -> None:
    pass


def img_dhash(path, hash_size: int = 8) -> int:
    """Difference-hash perceptual de una imagen (64 bits por defecto)."""
    from PIL import Image

    img = Image.open(path).convert("L").resize((hash_size + 1, hash_size), Image.BILINEAR)
    pixels = list(img.getdata())
    val = 0
    for row in range(hash_size):
        base = row * (hash_size + 1)
        for col in range(hash_size):
            val = (val << 1) | (1 if pixels[base + col] < pixels[base + col + 1] else 0)
    return val


def hash_distance(a: int, b: int) -> int:
    return bin(a ^ b).count("1")


def extract_first_frame(video_path, out_jpg) -> bool:
    """Requiere ffmpeg en el PATH del sistema."""
    try:
        r = subprocess.run(
            ["ffmpeg", "-y", "-i", str(video_path), "-vframes", "1", "-q:v", "4", str(out_jpg)],
            capture_output=True,
            timeout=15,
        )
        return r.returncode == 0 and Path(out_jpg).is_file()
    except Exception:
        return False


def verify_batch_fix(images_meta: list, vid_dir: Path, log: Callable[[str], None] = _NoOpLog) -> None:
    """Pase de correccion global: compara cada video existente contra TODAS las
    imagenes fuente del lote y corrige nombres/duplicados con emparejamiento
    greedy (mejor coincidencia global primero). Seguro de llamar repetidamente.

    Deliberadamente UN SOLO PASE GLOBAL (no incremental) para evitar condiciones
    de carrera entre workers de descarga concurrentes.
    """
    try:
        index_to_stem = {m["index"]: Path(m["name"]).stem for m in images_meta}
        source_hashes = {}
        for m in images_meta:
            p = m.get("path", "")
            if p and Path(p).is_file():
                try:
                    source_hashes[m["index"]] = img_dhash(p)
                except Exception:
                    pass
        if not source_hashes:
            return

        existing = []
        for idx, stem in index_to_stem.items():
            vp = vid_dir / f"{stem}.mp4"
            if vp.is_file():
                existing.append((idx, stem, vp))
        if not existing:
            return

        def _hash_one(item):
            idx, stem, vp = item
            with tempfile.TemporaryDirectory() as td:
                frame = Path(td) / "f.jpg"
                if not extract_first_frame(vp, frame):
                    return (idx, stem, vp, None)
                try:
                    return (idx, stem, vp, img_dhash(frame))
                except Exception:
                    return (idx, stem, vp, None)

        with ThreadPoolExecutor(max_workers=8) as ex:
            video_hashes = list(ex.map(_hash_one, existing))

        pairs = []
        for idx, stem, vp, vhash in video_hashes:
            if vhash is None:
                continue
            for cand_idx, cand_hash in source_hashes.items():
                d = hash_distance(vhash, cand_hash)
                if d <= MATCH_THRESHOLD:
                    pairs.append((d, idx, stem, vp, cand_idx))
        pairs.sort(key=lambda t: t[0])

        claimed_index = set()
        claimed_video = set()
        assignment = {}
        for d, idx, stem, vp, cand_idx in pairs:
            vkey = str(vp)
            if vkey in claimed_video or cand_idx in claimed_index:
                continue
            claimed_video.add(vkey)
            claimed_index.add(cand_idx)
            assignment[vkey] = (cand_idx, d, stem)

        for idx, stem, vp, vhash in video_hashes:
            vkey = str(vp)
            if vhash is None:
                continue
            got = assignment.get(vkey)
            if got is None:
                continue
            cand_idx, d, _stem_unused = got
            correct_stem = index_to_stem.get(cand_idx)
            if not correct_stem or correct_stem == stem:
                continue
            correct_path = vid_dir / f"{correct_stem}.mp4"
            try:
                if correct_path.exists():
                    correct_path.unlink()
                vp.rename(correct_path)
                log(
                    f"[verificador] {stem}.mp4 no coincidia con su imagen - reasignado a {correct_stem}.mp4 (dist={d})"
                )
            except Exception as exc:
                log(f"[WARNING] [verificador] no se pudo reasignar {stem}.mp4 --> {correct_stem}.mp4: {exc}")

        for idx, stem, vp, vhash in video_hashes:
            vkey = str(vp)
            if vhash is None or vkey in assignment:
                continue
            own_hash = source_hashes.get(idx)
            own_dist = hash_distance(vhash, own_hash) if own_hash is not None else None
            if own_dist is not None and own_dist <= MATCH_THRESHOLD:
                continue
            if vp.exists():
                try:
                    vp.unlink()
                    log(
                        f"[verificador] {stem}.mp4 descartado - no coincide con su propia imagen "
                        f"ni con ninguna otra del lote (dist propia={own_dist})"
                    )
                except Exception:
                    pass
    except Exception as exc:
        try:
            log(f"[WARNING] [verificador] excepcion en pase de verificacion: {exc}")
        except Exception:
            pass
