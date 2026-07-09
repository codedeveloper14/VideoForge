import threading
import time
from collections import Counter
from collections.abc import Callable

from src.infrastructure.ai_providers.whisk_client import WhiskClient
from src.utils.logger import get_logger

logger = get_logger(__name__)


def _NoOpLog(msg: str) -> None:
    pass


def _NoOpJobs(c: "WhiskClient") -> int:
    return 0


class WhiskPool:
    """Gestiona todos los clientes Whisk listos.

    - Ante un 429 / cookie invalida: pausa esa cuenta N segundos y rota.
    - Si TODAS estan en cooldown: espera silenciosamente hasta la mas proxima.
    - Limite de concurrencia por cuenta = numero real de slots configurados.
    - El log de "saturacion" solo aparece una vez cada 10s para no spamear.
    """

    def __init__(
        self,
        clients: list[WhiskClient],
        subj_path,
        jobs_for: Callable[[WhiskClient], int] = _NoOpJobs,
        log: Callable[[str], None] = _NoOpLog,
    ):
        self._clients = list(clients)
        self._subj = subj_path
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._jobs_for = jobs_for
        self._log = log

        self._cooldown: dict[str, float] = {c.label: 0.0 for c in clients}
        self._leased: set = set()

        slot_counts = Counter(self._acc_id(c) for c in clients)
        self._max_per_acc: dict[int, int] = dict(slot_counts)
        self._last_sat_log = 0.0

    @staticmethod
    def _acc_id(c: WhiskClient) -> int:
        return int(c.label[1]) if c.label[1:2].isdigit() else 0

    def _free_now(self) -> list[WhiskClient]:
        now = time.time()
        return [c for c in self._clients if c not in self._leased and self._cooldown.get(c.label, 0.0) <= now]

    def get_client(self, cancel_ev: threading.Event) -> WhiskClient | None:
        """Devuelve el siguiente cliente disponible; bloquea silenciosamente si
        todos estan en cooldown. Devuelve None si el usuario cancela."""
        with self._cond:
            while True:
                if cancel_ev.is_set():
                    return None
                free = self._free_now()
                if free:
                    free.sort(key=self._jobs_for)
                    chosen = free[0]
                    self._leased.add(chosen)
                    return chosen

                now = time.time()
                cd_vals = [v for v in self._cooldown.values() if v > now]
                wait_secs = max(0.3, min(cd_vals) - now) if cd_vals else 1.0

                if now - self._last_sat_log >= 10:
                    n_cd = sum(1 for v in self._cooldown.values() if v > now)

                    def acc_saturated(acc: int) -> bool:
                        for c in self._clients:
                            if self._acc_id(c) != acc:
                                continue
                            if c not in self._leased and self._cooldown.get(c.label, 0.0) <= now:
                                return False
                        return True

                    n_sat = sum(1 for acc in self._max_per_acc if acc_saturated(acc))
                    reason = []
                    if n_cd:
                        reason.append(f"{n_cd} en cooldown")
                    if n_sat:
                        reason.append(f"{n_sat} ctas al limite")
                    self._log(f"Esperando slot libre ({', '.join(reason) or 'saturado'})...")
                    self._last_sat_log = now

                self._cond.wait(timeout=min(wait_secs, 2.0))

    def release_client(self, client: WhiskClient) -> None:
        with self._cond:
            self._leased.discard(client)
            self._cond.notify_all()

    def mark_ok(self, client: WhiskClient) -> None:
        with self._cond:
            self._cooldown[client.label] = 0.0
            self._leased.discard(client)
            self._cond.notify_all()

    def mark_ratelimited(self, client: WhiskClient, cooldown: float = 65.0) -> None:
        with self._cond:
            self._cooldown[client.label] = time.time() + cooldown
            self._leased.discard(client)
            self._log(f"[{client.label}] Rate-limit - pausa {cooldown:.0f}s")
            self._cond.notify_all()

    def reset_client_async(self, client: WhiskClient) -> None:
        def _do():
            try:
                self._log(f"[{client.label}] Renovando sesion...")
                client.reset_session(self._subj)
                self._log(f"[{client.label}] [OK] Sesion renovada")
                with self._cond:
                    self._cooldown[client.label] = 0.0
                    self._cond.notify_all()
            except Exception as exc:
                self._log(f"[{client.label}] [ERROR] reset fallo: {exc} - cooldown 5 min")
                with self._cond:
                    self._cooldown[client.label] = time.time() + 300
                    self._cond.notify_all()

        threading.Thread(target=_do, daemon=True).start()
