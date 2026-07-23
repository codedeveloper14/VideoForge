"""Generaliza _assign_slot_for_hash/los sidecars account_N.bridge.json de
flow_animation_service.py (lineas 125-189 de ese modulo, sin tocar) para los bridges
nuevos que necesitan el mismo problema resuelto: la extension manda un account_hash
anonimo (no sabe a que cuenta local del usuario corresponde), y hay que mapearlo a un
slot 0..N-1 estable entre reinicios del backend, sin que dos hashes distintos jamas
terminen compartiendo el mismo slot.

Qwen y Vibes NO usan esto: Qwen ya conoce el nombre real de la cuenta local (viene en
la URL, `?imperio_qwen_account=`), y Vibes tiene una unica cuenta fija -- solo GenTube
y Grok (cuentas anonimas 0..9) lo necesitan."""

import json
import threading
import time
from pathlib import Path
from typing import Callable


class SlotAssigner:
    def __init__(
        self,
        sidecar_dir: Path,
        prefix: str,
        num_slots: int,
        valid_hash_prefix: str | None = None,
    ):
        self._sidecar_dir = Path(sidecar_dir)
        self._prefix = prefix
        self._num_slots = num_slots
        self._valid_hash_prefix = valid_hash_prefix
        self._hash_to_idx: dict[str, int] = {}
        self._lock = threading.Lock()

    def _sidecar_path(self, idx: int) -> Path:
        return self._sidecar_dir / f"{self._prefix}_{idx}.bridge.json"

    def read_sidecar(self, idx: int) -> dict | None:
        path = self._sidecar_path(idx)
        if not path.is_file():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return None
        # Sidecar de un formato de hash viejo/invalido: nunca vuelve a conectarse,
        # asi que lo limpiamos para no desperdiciar el slot para siempre (mismo
        # criterio que _load_bridge_session en flow_animation_service.py).
        if self._valid_hash_prefix and not str(data.get("account_hash", "")).startswith(self._valid_hash_prefix):
            try:
                path.unlink()
            except Exception:
                pass
            return None
        return data

    def write_sidecar(self, idx: int, account_hash: str, meta: dict | None = None) -> None:
        payload = {"account_hash": account_hash, "ts": time.time()}
        if meta:
            payload.update(meta)
        try:
            self._sidecar_dir.mkdir(parents=True, exist_ok=True)
            self._sidecar_path(idx).write_text(json.dumps(payload), encoding="utf-8")
        except Exception:
            pass

    def assign_slot(
        self,
        account_hash: str,
        slot_taken_on_disk: Callable[[int], bool] = lambda i: False,
    ) -> int | None:
        """Devuelve el slot estable para `account_hash`, reservando el primer libre
        la primera vez que se ve ese hash. `slot_taken_on_disk(i)` debe indicar si el
        slot i ya esta ocupado por OTRO medio (p. ej. cookie ya guardada a mano) --
        un slot asi nunca se pisa. Devuelve None si no queda ningun slot libre."""
        with self._lock:
            if account_hash in self._hash_to_idx:
                return self._hash_to_idx[account_hash]
            # Reservados en memoria en esta corrida del proceso, aunque su sidecar
            # en disco todavia no se haya escrito -- evita que dos hashes nuevos
            # registrandose casi al mismo tiempo lean el mismo estado "libre" en
            # disco y terminen compartiendo indice.
            reserved = set(self._hash_to_idx.values())
            for i in range(self._num_slots):
                if i in reserved:
                    continue
                existing = self.read_sidecar(i)
                if existing and existing.get("account_hash") == account_hash:
                    self._hash_to_idx[account_hash] = i
                    return i
            for i in range(self._num_slots):
                if i in reserved:
                    continue
                if slot_taken_on_disk(i) or self.read_sidecar(i):
                    continue
                self._hash_to_idx[account_hash] = i
                return i
            return None
