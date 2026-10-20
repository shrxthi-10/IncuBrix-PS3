from datetime import datetime, timezone
from uuid import uuid4

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import APP_NAME, API_PREFIX
from app.services.job_manager import create_job, get_job
from app.workers.job_worker import enqueue_job

app = FastAPI(
    title=APP_NAME,
    version="0.2.0",
    description="API for generating narrated videos with matched B-roll.",
)


class CreateJobRequest(BaseModel):
    script: str = Field(min_length=1, max_length=50000)
    aspect_ratio: str = "16:9"
    narration_language: str = "en"


@app.middleware("http")
async def add_trace_id(request, call_next):
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
        "version": "0.2.0",
        "status": "running",
    }


@app.post(f"{API_PREFIX}/jobs", status_code=202)
def submit_job(
    payload: CreateJobRequest,
    idempotency_key: str = Header(alias="Idempotency-Key"),
):
    request_data = payload.model_dump()

    try:
        job = create_job(idempotency_key, request_data)
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "IDEMPOTENCY_CONFLICT",
                "message": str(exc),
                "ret ryable": False,
                "details": {},
            },
        )
    if job["status"] == "queued":
        enqueue_job(job["job_id"])
    return {
        "job_id": job["job_id"],
        "status": job["status"],
        "progress": job["progress"],
        "status_url": f"{API_PREFIX}/jobs/{job['job_id']}",
    }


@app.get(f"{API_PREFIX}/jobs/{{job_id}}")
def job_status(job_id: str):
    job = get_job(job_id)

    if job is None:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "JOB_NOT_FOUND",
                "message": "No job exists with this ID.",
                "retryable": False,
                "details": {"job_id": job_id},
            },
        )

    return job



from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi import HTTPException


@app.exception_handler(HTTPException)
async def http_error_handler(request: Request, exc: HTTPException):
    # Preserve structured errors already created by our endpoints.
    if isinstance(exc.detail, dict) and all(
        key in exc.detail
        for key in ("code", "message", "retryable", "details")
    ):
        error = exc.detail
    else:
        error = {
            "code": (
                exc.detail.get("code")
                if isinstance(exc.detail, dict) and "code" in exc.detail
                else {
                    404: "RESOURCE_NOT_FOUND",
                    409: "CONFLICT",
                    422: "VALIDATION_ERROR",
                }.get(exc.status_code, "HTTP_ERROR")
            ),
            "message": (
                exc.detail.get("message")
                if isinstance(exc.detail, dict) and "message" in exc.detail
                else str(exc.detail)
            ),
            "retryable": (
                exc.detail.get("retryable", exc.status_code >= 500)
                if isinstance(exc.detail, dict)
                else exc.status_code >= 500
            ),
            "details": (
                exc.detail.get("details", {})
                if isinstance(exc.detail, dict)
                else {}
            ),
        }

    return JSONResponse(
        status_code=exc.status_code,
        content=error,
    )


@app.exception_handler(RequestValidationError)
async def validation_error_handler(
    request: Request, exc: RequestValidationError
):
    return JSONResponse(
        status_code=422,
        content={
            "code": "VALIDATION_ERROR",
            "message": "The request contains missing or invalid fields.",
            "retryable": False,
            "details": {"errors": exc.errors()},
        },
    )


@app.exception_handler(Exception)
async def unexpected_error_handler(request: Request, exc: Exception):
    trace_id = request.headers.get("X-Correlation-ID", "unavailable")
    return JSONResponse(
        status_code=500,
        content={
            "code": "INTERNAL_SERVER_ERROR",
            "message": "An unexpected error occurred.",
            "retryable": True,
            "details": {"trace_id": trace_id},
        },
    )
