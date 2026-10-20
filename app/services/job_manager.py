from datetime import datetime, timezone
from threading import Lock
from uuid import uuid4

JOBS = {}
IDEMPOTENCY_KEYS = {}
LOCK = Lock()


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def create_job(idempotency_key: str, request_data: dict) -> dict:
    if not idempotency_key or not idempotency_key.strip():
        raise ValueError("An Idempotency-Key header is required.")

    with LOCK:
        existing = IDEMPOTENCY_KEYS.get(idempotency_key)

        if existing:
            old_body, job_id = existing

            if old_body != request_data:
                raise ValueError(
                    "This Idempotency-Key was already used with a different request."
                )

            return JOBS[job_id].copy()

        job_id = str(uuid4())

        job = {
            "job_id": job_id,
            "status": "queued",
            "progress": 0,
            "created_at": utc_now(),
            "updated_at": utc_now(),
            "request": request_data,
            "result": None,
            "error": None,
        }

        JOBS[job_id] = job
        IDEMPOTENCY_KEYS[idempotency_key] = (request_data.copy(), job_id)

        return job.copy()


def get_job(job_id: str):
    with LOCK:
        job = JOBS.get(job_id)
        return job.copy() if job else None


def update_job(job_id: str, **changes):
    with LOCK:
        if job_id not in JOBS:
            return None

        JOBS[job_id].update(changes)
        JOBS[job_id]["updated_at"] = utc_now()
        return JOBS[job_id].copy()
