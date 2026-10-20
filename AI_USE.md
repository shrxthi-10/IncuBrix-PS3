# AI Use and Tool Disclosure

## 1. Project Summary

The IncuBrix Script-to-B-roll Video Engine is a prototype that converts a written script into narrated video using stock footage, subtitles, and automated video rendering.

## 2. AI-Assisted Development

ChatGPT was used as an AI-assisted development and learning tool during implementation. Assistance included:

- Breaking the project requirements into implementation steps.
- Drafting and revising Python code and configuration.
- Explaining API routes, background jobs, and idempotency.
- Helping debug runtime errors and test failures.
- Drafting project documentation and test procedures.

The project author is responsible for reviewing, running, testing, and understanding the submitted implementation.

## 3. Runtime Services and Tools

| Tool or service | Purpose | Important qualification |
|---|---|---|
| FastAPI | HTTP API and request validation | Local application framework |
| Edge TTS | Generate narration from text | Requires network access and depends on the external service |
| Pixabay API | Search for stock footage | Requires a valid API key and network access |
| FFmpeg | Normalize and render video and audio | Local media-processing dependency |
| Python and pytest | Application runtime and automated tests | Local development and verification |

The prototype uses metadata and keyword matching to select footage. It does not currently implement a separately validated vision-language model that independently confirms each scene's visual meaning.

## 4. Human Review

Human review remains necessary for:

- Scene-to-footage relevance.
- Subtitle timing and readability.
- Video and audio quality.
- Stock-footage licensing and attribution.
- Safety, privacy, visible people, and trademarks.
- Final acceptance of generated outputs.

## 5. Testing and Evidence

The latest recorded automated test run completed with 11 tests passed and no failures. Several sample videos were also generated and checked for video and audio streams.

These checks demonstrate basic prototype functionality; they do not establish production reliability, independent semantic accuracy, licence clearance, or compliance with every assessment requirement.

## 6. Limitations and Transparency

- Narration generation depends on an external text-to-speech service.
- Footage retrieval depends on the external Pixabay API.
- Scene relevance is estimated from text and metadata.
- Subtitle timing is estimated rather than word-aligned.
- Job state is currently held in memory.
- Docker Compose startup and production deployment have not been verified.
- No independent scene-relevance rating study or concurrency benchmark has been completed.

## 7. Data and Credentials

API keys and other secrets must be kept in a local `.env` file and excluded from version control. Do not include secrets in screenshots, logs, documentation, source manifests, or the public demonstration.

## 8. Declaration

This document describes the AI-assisted development process and the known runtime services used by the prototype. Any additional models, services, datasets, or generated assets introduced later must be added to this disclosure before submission.