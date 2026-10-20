import hashlib
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import (
    FastAPI,
    File,
    Form,
    Header,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import APP_NAME, API_PREFIX, MAX_AUDIO_SECONDS, TEST_INPUT_DIR
from app.services.job_manager import create_job, get_job
from app.services.video_renderer import probe_duration
from app.workers.job_worker import enqueue_job

app = FastAPI(
    title=APP_NAME,
    version="0.3.0",
    description="API for generating narrated videos with matched B-roll.",
)

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}
MAX_UPLOAD_BYTES = 100 * 1024 * 1024  # 100 MB


class CreateJobRequest(BaseModel):
    script: str = Field(min_length=1, max_length=50000)
    aspect_ratio: str = "16:9"
    narration_language: str = "en"


def api_error(code: str, message: str, details=None, retryable=False):
    return {
        "code": code,
        "message": message,
        "retryable": retryable,
        "details": details or {},
    }


@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    trace_id = request.headers.get("X-Correlation-ID", str(uuid4()))
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = trace_id
    return response


@app.get("/health")
def health():
    return {
        "status": "ok",
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/ready")
def ready():
    return {"status": "ready"}


@app.get(f"{API_PREFIX}/")
def api_info():
    return {
        "name": APP_NAME,
        "version": "0.3.0",
        "status": "running",
    }


@app.post(f"{API_PREFIX}/jobs", status_code=202)
def submit_script_job(
    payload: CreateJobRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    request_data = {
        **payload.model_dump(),
        "input_type": "text",
    }

    try:
        job = create_job(idempotency_key, request_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=api_error("IDEMPOTENCY_CONFLICT", str(exc)),
        )

    if job["status"] == "queued":
        enqueue_job(job["job_id"])

    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "status_url": f"{API_PREFIX}/jobs/{job['job_id']}",
    }


@app.post(f"{API_PREFIX}/jobs/audio", status_code=202)
async def submit_audio_job(
    audio: UploadFile = File(...),
    aspect_ratio: str = Form("16:9"),
    narration_language: str = Form("en"),
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    extension = Path(audio.filename or "").suffix.lower()

    if extension not in ALLOWED_AUDIO_EXTENSIONS:
        raise HTTPException(
            status_code=415,
            detail=api_error(
                "UNSUPPORTED_AUDIO_FORMAT",
                "Upload an MP3, WAV, or M4A file.",
                {"allowed_extensions": sorted(ALLOWED_AUDIO_EXTENSIONS)},
            ),
        )

    upload_dir = TEST_INPUT_DIR / "audio_uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    # Read in chunks so an excessively large upload is rejected.
    digest = hashlib.sha256()
    temporary_path = upload_dir / f"upload_{uuid4().hex}{extension}"
    total_bytes = 0

    try:
        with temporary_path.open("wb") as destination:
            while True:
                chunk = await audio.read(1024 * 1024)
                if not chunk:
                    break

                total_bytes += len(chunk)
                if total_bytes > MAX_UPLOAD_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=api_error(
                            "AUDIO_FILE_TOO_LARGE",
                            "The audio upload must not exceed 100 MB.",
                        ),
                    )

                digest.update(chunk)
                destination.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=422,
                detail=api_error("EMPTY_AUDIO_FILE", "The uploaded file is empty."),
            )

        try:
            duration = probe_duration(temporary_path)
        except Exception:
            raise HTTPException(
                status_code=422,
                detail=api_error(
                    "INVALID_AUDIO_FILE",
                    "The uploaded file could not be read as valid media.",
                ),
            )

        if duration <= 0 or duration > MAX_AUDIO_SECONDS:
            raise HTTPException(
                status_code=422,
                detail=api_error(
                    "INVALID_AUDIO_DURATION",
                    f"Audio must be longer than zero and no more than "
                    f"{MAX_AUDIO_SECONDS} seconds.",
                    {"duration_seconds": duration},
                ),
            )

        file_hash = digest.hexdigest()
        saved_path = upload_dir / f"{file_hash}{extension}"

        # Use a content-addressed filename so retries with the same
        # Idempotency-Key and same audio resolve to the same request.
        if saved_path.exists():
            temporary_path.unlink(missing_ok=True)
        else:
            temporary_path.replace(saved_path)

        request_data = {
            "script": "",
            "input_type": "audio",
            "audio_path": str(saved_path.resolve()),
            "audio_sha256": file_hash,
            "audio_duration_seconds": duration,
            "aspect_ratio": aspect_ratio,
            "narration_language": narration_language,
        }

        try:
            job = create_job(idempotency_key, request_data)
        except ValueError as exc:
            raise HTTPException(
                status_code=409,
                detail=api_error("IDEMPOTENCY_CONFLICT", str(exc)),
            )

        if job["status"] == "queued":
            enqueue_job(job["job_id"])

        return {
            "job_id": job["job_id"],
            "status": job["status"],
            "progress": job["progress"],
            "audio_duration_seconds": duration,
            "status_url": f"{API_PREFIX}/jobs/{job['job_id']}",
        }

    finally:
        temporary_path.unlink(missing_ok=True)
        await audio.close()


@app.get(f"{API_PREFIX}/jobs/{{job_id}}")
def job_status(job_id: str):
    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail=api_error(
                "JOB_NOT_FOUND",
                "No job exists with this ID.",
                {"job_id": job_id},
            ),
        )

    return job


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    if (
        isinstance(exc.detail, dict)
        and all(
            key in exc.detail
            for key in ("code", "message", "retryable", "details")
        )
    ):
        error = exc.detail
    else:
        error = api_error(
            "HTTP_ERROR",
            str(exc.detail),
            retryable=exc.status_code >= 500,
        )

    return JSONResponse(status_code=exc.status_code, content=error)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content=api_error(
            "VALIDATION_ERROR",
            "The request contains missing or invalid fields.",
            {"errors": exc.errors()},
        ),
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content=api_error(
            "INTERNAL_SERVER_ERROR",
            "An unexpected error occurred.",
            {
                "trace_id": request.headers.get(
                    "X-Correlation-ID", "unavailable"
                )
            },
            retryable=True,
        ),
    )