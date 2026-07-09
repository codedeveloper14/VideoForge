"""Registro en memoria de jobs de fondo (renders, transcripciones, etc.),
compartido por cualquier servicio que necesite exponer progreso via
`/api/estado/<job_id>` (y equivalentes como `/api/editor/estado/<job_id>`)."""

_jobs: dict[str, dict] = {}


def create_job(job_id: str, initial: dict) -> dict:
    _jobs[job_id] = initial
    return _jobs[job_id]


def get_job(job_id: str) -> dict | None:
    return _jobs.get(job_id)


def update_job(job_id: str, **fields) -> None:
    _jobs[job_id].update(fields)


def all_jobs() -> list[dict]:
    return list(_jobs.values())
