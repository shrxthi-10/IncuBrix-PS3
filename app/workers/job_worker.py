import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.audio_transcriber import transcribe_audio
from app.services.job_manager import update_job
from app.services.scene_footage_matcher import match_script_to_footage
from app.services.video_renderer import render_video, probe_duration

ROOT = Path(__file__).resolve().parents[2]
INPUT_DIR = ROOT / "test_inputs"
OUTPUT_DIR = ROOT / "outputs" / "rendered_videos"
SUBTITLE_DIR = ROOT / "outputs" / "subtitles"

EXECUTOR = ThreadPoolExecutor(max_workers=2)

VOICES = {
    "en": "en-US-AriaNeural",
    "en-us": "en-US-AriaNeural",
    "en-gb": "en-GB-SoniaNeural",
    "ta": "ta-IN-PallaviNeural",
    "hi": "hi-IN-SwaraNeural",
}


def seconds_to_srt_time(seconds: float) -> str:
    milliseconds = round(seconds * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds_part, milliseconds = divmod(remainder, 1000)

    return (
        f"{hours:02}:{minutes:02}:{seconds_part:02},"
        f"{milliseconds:03}"
    )


def create_subtitles(
    scenes: list[dict],
    duration: float,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    total_weight = sum(
        max(len(scene.get("narration_text", "").split()), 1)
        for scene in scenes
    )

    cursor = 0.0
    lines = []

    for index, scene in enumerate(scenes, start=1):
        words = max(
            len(scene.get("narration_text", "").split()),
            1,
        )
        scene_duration = duration * words / total_weight
        end = duration if index == len(scenes) else cursor + scene_duration

        lines.extend([
            str(index),
            (
                f"{seconds_to_srt_time(cursor)} --> "
                f"{seconds_to_srt_time(end)}"
            ),
            scene.get("narration_text", ""),
            "",
        ])
        cursor = end

    output_path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    return output_path


def generate_narration(
    script: str,
    language: str,
    output_path: Path,
) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    voice = VOICES.get(
        language.lower(),
        VOICES["en"],
    )

    command = [
        sys.executable,
        "-m",
        "edge_tts",
        "--text",
        script,
        "--voice",
        voice,
        "--write-media",
        str(output_path),
    ]

    subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=True,
        timeout=180,
    )

    if not output_path.is_file() or output_path.stat().st_size == 0:
        raise RuntimeError("Narration generation produced no audio file.")

    return output_path


def process_job(job_id: str) -> None:
    try:
        job = update_job(
            job_id,
            status="running",
            progress=5,
            error=None,
            result=None,
        )

        if not job:
            return

        request_data = job["request"]
        input_type = request_data.get("input_type", "text")
        script = request_data.get("script", "").strip()

        update_job(job_id, progress=10)

        if input_type == "audio":
            audio_path = Path(request_data["audio_path"])

            transcription = transcribe_audio(audio_path)
            script = transcription["transcript"]

            update_job(
                job_id,
                progress=25,
                transcript=script,
                transcription={
                    "language": transcription["language"],
                    "language_probability": transcription[
                        "language_probability"
                    ],
                    "model": transcription["model"],
                },
            )

        else:
            if not script:
                raise ValueError("The script cannot be empty.")

            audio_path = INPUT_DIR / f"narration_{job_id}.mp3"

            generate_narration(
                script,
                request_data.get("narration_language", "en"),
                audio_path,
            )

        update_job(job_id, progress=35)

        match_result = match_script_to_footage(script)
        scenes = match_result.get("scenes", [])

        if not scenes:
            raise RuntimeError(
                "The script planner returned no scenes."
            )

        clip_paths = []

        for scene in scenes:
            footage = scene.get("footage", {})
            metadata = footage.get("metadata", {})
            local_path = metadata.get("local_path")

            if footage.get("status") == "downloaded" and local_path:
                clip_path = Path(local_path)

                if clip_path.is_file():
                    clip_paths.append(clip_path)

        if not clip_paths:
            raise RuntimeError(
                "No usable B-roll clips were found. Check the footage "
                "API key, internet connection, and scene-footage manifest."
            )

        if len(clip_paths) != len(scenes):
            raise RuntimeError(
                f"Only {len(clip_paths)} of {len(scenes)} scenes have "
                "footage. Rendering stopped to avoid silently omitting "
                "parts of the narration."
            )

        update_job(job_id, progress=60)

        audio_duration = probe_duration(audio_path)

        subtitle_path = SUBTITLE_DIR / f"{job_id}.srt"

        create_subtitles(
            scenes,
            audio_duration,
            subtitle_path,
        )

        update_job(job_id, progress=70)

        output_name = f"{job_id}.mp4"

        manifest = render_video(
            narration_path=audio_path,
            clip_paths=clip_paths,
            output_name=output_name,
            subtitle_path=subtitle_path,
        )

        result = {
            "video_file": manifest["output_file"],
            "manifest_file": manifest["manifest_file"],
            "subtitle_file": str(subtitle_path),
            "duration_seconds": manifest["output_duration_seconds"],
            "resolution": manifest["resolution"],
            "scene_count": manifest["scene_count"],
            "input_type": input_type,
            "transcript": script if input_type == "audio" else None,
            "warnings": [
                "Footage selection uses metadata keyword matching.",
                "Subtitle timing is estimated, not word-level aligned.",
                "Human visual relevance review is still required.",
            ],
        }

        update_job(
            job_id,
            status="succeeded",
            progress=100,
            result=result,
            error=None,
        )

    except Exception as exc:
        update_job(
            job_id,
            status="failed",
            progress=0,
            error={
                "code": "JOB_PROCESSING_FAILED",
                "message": str(exc),
                "retryable": True,
                "details": {},
            },
        )


def enqueue_job(job_id: str) -> None:
    EXECUTOR.submit(process_job, job_id)