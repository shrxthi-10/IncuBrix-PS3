import hashlib
import json
import logging
import time
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
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from app.config import (
    APP_NAME,
    API_PREFIX,
    MAX_AUDIO_SECONDS,
    OUTPUT_DIR,
    TEST_INPUT_DIR,
)
from app.services.job_manager import create_job, get_job
from app.services.video_renderer import probe_duration
from app.workers.job_worker import enqueue_job

app = FastAPI(
    title=APP_NAME,
    version="0.3.0",
    description="API for generating narrated videos with matched B-roll.",
)

VIDEO_OUTPUT_DIR = OUTPUT_DIR / "rendered_videos"
VIDEO_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

app.mount(
    "/outputs/videos",
    StaticFiles(directory=str(VIDEO_OUTPUT_DIR)),
    name="rendered-videos",
)

ALLOWED_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a"}
logger = logging.getLogger("incubrix.api")
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


def error_response(status_code: int, error: dict) -> JSONResponse:
    """Return errors using the assessment's required envelope."""
    return JSONResponse(status_code=status_code, content={"error": error})


@app.middleware("http")
async def add_trace_id(request: Request, call_next):
    trace_id = request.headers.get("X-Correlation-ID", str(uuid4()))
    started = time.perf_counter()
    status_code = 500
    try:
        response = await call_next(request)
        status_code = response.status_code
        response.headers["X-Correlation-ID"] = trace_id
        return response
    finally:
        path_parts = request.url.path.strip("/").split("/")
        job_id = path_parts[-1] if len(path_parts) >= 4 and path_parts[-2] == "jobs" else None
        logger.info(json.dumps({
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": "INFO",
            "event": "http_request_completed",
            "method": request.method,
            "path": request.url.path,
            "status_code": status_code,
            "job_id": job_id,
            "correlation_id": trace_id,
            "duration_ms": round((time.perf_counter() - started) * 1000, 2),
        }, separators=(",", ":")))


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
def job_status(job_id: str, request: Request):
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

    response = job.copy()
    result = job.get("result")

    if job.get("status") == "succeeded" and result:
        response["result"] = result.copy()
        video_path = VIDEO_OUTPUT_DIR / f"{job_id}.mp4"

        if video_path.is_file():
            base_url = str(request.base_url).rstrip("/")
            response["result"]["video_url"] = (
                f"{base_url}/outputs/videos/{job_id}.mp4"
            )

    return response


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

    return error_response(exc.status_code, error)


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
):
    return error_response(
        422,
        api_error(
            "VALIDATION_ERROR",
            "The request contains missing or invalid fields.",
            {"errors": exc.errors()},
        ),
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    return error_response(
        500,
        api_error(
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