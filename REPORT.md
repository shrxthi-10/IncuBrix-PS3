# IncuBrix Script-to-B-roll Video Engine — Technical Report

## 1. Project Overview

This project implements a local API-based engine that accepts a written script, generates narration, selects stock footage using metadata and keyword matching, adds subtitles, and renders a narrated B-roll video.

The system is intended as a prototype for automated script-to-video generation. Visual relevance and licensing still require human review.

## 2. Implemented Features

- FastAPI application with versioned routes under `/api/v1`.
- Health and readiness endpoints.
- Asynchronous job submission and status polling.
- Idempotency-Key support for job submissions.
- Standardized JSON error responses.
- Text-to-speech narration using Edge TTS.
- English, Hindi, and Tamil voice options configured in the worker.
- Sentence-based scene planning.
- Pixabay video search and footage download.
- Metadata-based scene-to-footage matching.
- FFmpeg-based video rendering with normalized 1280x720 output, 25 fps, H.264 video, and AAC audio.
- Generated subtitle files with estimated timing.
- Per-job output and scene-manifest files.
- Batch submission and polling through a Python batch runner.
- Automated API and video-validation unit tests.
- OpenAPI 3.1 specification.

## 3. System Workflow

1. A client submits a script, narration language, and aspect ratio to the API.
2. The API validates the request and checks the idempotency key.
3. The job is queued for background processing.
4. The worker generates narration audio.
5. The script is divided into sentence-based scenes.
6. The footage matcher searches Pixabay and ranks available footage using metadata keywords.
7. Downloaded clips are passed to the renderer.
8. FFmpeg normalizes and combines the clips with narration and subtitles.
9. The output video, subtitle file, and manifests are saved locally.
10. The client polls the job endpoint to retrieve its status and result.

## 4. Architecture

The main components are:

- `app/main.py`: FastAPI routes and error handling.
- `app/config.py`: application paths and configuration.
- `app/services/job_manager.py`: job state and idempotency management.
- `app/services/scene_planner.py`: sentence-based scene planning.
- `app/services/scene_footage_matcher.py`: metadata-based footage selection.
- `app/services/footage_downloader.py`: Pixabay search and downloads.
- `app/services/video_renderer.py`: subtitle preparation and FFmpeg rendering.
- `app/workers/job_worker.py`: background job processing.
- `tests/`: automated tests.
- `openapi.yaml`: API contract.
- `batch_runner.py`: batch execution utility.

## 5. Test Results

The latest local automated test run completed with:

- Tests passed: 11
- Tests failed: 0
- Runtime: approximately 0.74 seconds
- Warning: a Starlette deprecation warning concerning the use of `httpx` with its test client.

Additional manually generated videos have been checked for non-zero duration and the presence of video and audio streams. Sample outputs include village, water-cycle, pizza, and batch-generated videos.

These results establish basic local functionality. They do not establish production readiness or independently verified semantic relevance.

## 6. Known Limitations

- Job state and idempotency records are held in memory and may be lost when the process restarts.
- Footage selection relies on text and metadata keywords; it does not independently confirm the visual contents of every selected clip.
- Subtitle timing is estimated rather than aligned to individual spoken words.
- Downloaded stock footage requires human review of the applicable licence, attribution requirements, and permitted use.
- Outputs are saved locally; public result URLs and S3-compatible object storage have not been verified as implemented.
- Docker Compose startup has not been verified in this environment.
- No independent human-rating study, concurrency benchmark, or measured production-cost evaluation has been completed.
- Partial scene replacement and partial rerender timing have not been verified.

## 7. Next Improvements

1. Persist job records and idempotency keys in a database.
2. Add durable queue processing and recovery after failures.
3. Add media upload and URL input support.
4. Add S3-compatible storage and result download URLs.
5. Improve footage relevance with visual or vision-language evaluation.
6. Improve subtitle alignment using speech timestamps.
7. Add explicit licence verification and source-attribution reporting.
8. Validate Docker Compose and one-command startup.
9. Add broader integration tests and concurrency measurements.
10. Evaluate scene relevance using a documented human-rating protocol.

## 8. Conclusion

The prototype demonstrates a local end-to-end workflow from written script to narrated, subtitled B-roll video, supported by a versioned API, job polling, batch processing, and automated tests. Further work is required before claiming full compliance with every integration standard or production-level reliability.