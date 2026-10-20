# IncuBrix Script-to-B-roll Video Engine

An API-driven prototype that converts a written script into a narrated video using automatically selected B-roll footage, subtitles, and scene-level metadata.

## Features

- Asynchronous video-generation jobs through FastAPI.
- Job-status and progress retrieval.
- Idempotency support using the `Idempotency-Key` request header.
- Text-to-speech narration using Edge TTS.
- B-roll retrieval through the Pixabay API.
- Scene planning and metadata-based footage matching.
- Video rendering with FFmpeg.
- Subtitle generation.
- Scene manifests and render metadata.
- Batch job submission and reporting.
- Health, readiness, and API documentation endpoints.

## Technology Stack

- Python 3.12
- FastAPI and Uvicorn
- Pydantic Settings
- Edge TTS
- Pixabay API
- FFmpeg and FFprobe
- Pytest
- PyYAML
- Requests

## Project Structure

```text
IncuBrix-PS3/
├── app/
│   ├── api/
│   ├── services/
│   ├── workers/
│   ├── config.py
│   └── main.py
├── tests/
├── test_inputs/
│   ├── batch.json
│   └── broll/
├── outputs/
│   ├── rendered_videos/
│   ├── render_manifests/
│   ├── scene_manifests/
│   └── subtitles/
├── docs/
├── .env.example
├── .gitignore
├── openapi.yaml
├── batch_runner.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── SOURCES.md
├── AI_USE.md
└── REPORT.md
```

## Prerequisites

- Python 3.12 or compatible version.
- FFmpeg and FFprobe available on the system PATH.
- A Pixabay API key for footage retrieval.
- Internet connectivity for API-based footage retrieval and Edge TTS.
- Docker Desktop only if using the containerized deployment.

## Local Setup

Open a terminal in the project directory.

### 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

If PowerShell blocks activation in the current terminal:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\.venv\Scripts\Activate.ps1
```

### 2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

### 3. Configure environment variables

Copy `.env.example` to `.env` and provide the required settings, including your Pixabay API key.

Never commit `.env` or publish API keys in source code, logs, screenshots, or documentation.

### 4. Start the API

```powershell
python -m uvicorn app.main:app --reload
```

Local endpoints:

- Health: http://127.0.0.1:8000/health
- Readiness: http://127.0.0.1:8000/ready
- API information: http://127.0.0.1:8000/api/v1/
- Interactive API documentation: http://127.0.0.1:8000/docs
- Live OpenAPI JSON: http://127.0.0.1:8000/openapi.json

## Submit a Video Job

With the API running, submit a script using PowerShell:

```powershell
$body = @{
    script = "The water cycle moves water through evaporation, condensation, and precipitation."
    aspect_ratio = "16:9"
    narration_language = "en"
} | ConvertTo-Json

$key = [guid]::NewGuid().ToString()

Invoke-RestMethod `
    -Method Post `
    -Uri "http://127.0.0.1:8000/api/v1/jobs" `
    -Headers @{ "Idempotency-Key" = $key } `
    -ContentType "application/json" `
    -Body $body
```

The API returns a job ID and status URL when the job is accepted.

## Check Job Status

Replace `<JOB_ID>` with the returned job ID:

```powershell
Invoke-RestMethod `
    -Method Get `
    -Uri "http://127.0.0.1:8000/api/v1/jobs/<JOB_ID>"
```

When processing succeeds, the job result includes the generated video path and available metadata paths.

## Run the Tests

```powershell
python -m pytest -v
```

The current verified test suite contains 11 passing tests covering API behavior, idempotency, request validation, and video-validation logic.

## Batch Processing

The batch runner submits multiple scripts and polls their job status.

Example:

```powershell
python batch_runner.py
```

Check the runner's configuration and expected input file before execution. The current sample input is `test_inputs/batch.json`; the report is written to `outputs/batch_report.json`.

## Generated Outputs

Generated artifacts are written beneath `outputs/`, including:

- `rendered_videos/` — rendered MP4 videos.
- `render_manifests/` — render metadata.
- `scene_manifests/` — scene and footage-selection information.
- `subtitles/` — generated subtitle files.
- `batch_report.json` — batch execution results.

Exact paths and files depend on the submitted job and the current application configuration.

## OpenAPI Specification

The manually maintained API specification is in `openapi.yaml`.

The running FastAPI application also exposes its generated OpenAPI document at:

http://127.0.0.1:8000/openapi.json

The manually maintained specification should be checked against the live API whenever routes, request models, response models, or error handlers change.

## Known Limitations

- Footage selection currently relies on metadata and keyword relevance; it does not independently verify every clip's visual content.
- Downloaded footage and its licence or attribution information require human review before publication.
- Subtitle timings are estimated rather than fully word-aligned.
- The current job manager stores jobs in application memory; job history is not durable across application restarts.
- Local output paths are returned by the current prototype. A publicly accessible download service and S3-compatible storage have not been verified.
- Docker Compose startup has not been verified in the current development environment.
- Production concurrency, cost, and performance have not yet been benchmarked.

## Responsible Use and Source Review

Review `SOURCES.md` for source and licence information, and inspect the licence terms for every downloaded asset before redistribution.

Review `AI_USE.md` for AI-assisted development disclosures.

Do not treat metadata matching as proof that a clip is semantically relevant, properly licensed, or suitable for publication.

## Project Status

This is a working prototype under development. The local API, sample video-generation workflows, batch execution, and current automated tests have been exercised. Outstanding integration and deployment requirements must be tested separately before the system is described as production-ready.