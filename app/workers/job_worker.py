import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from app.services.job_manager import update_job
from app.services.scene_footage_matcher import match_script_to_footage
from app.services.video_renderer import render_video

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
    hours, milliseconds = divmod(milliseconds, 3_600_000)
    minutes, milliseconds = divmod(milliseconds, 60_000)
    whole_seconds, milliseconds = divmod(milliseconds, 1000)
    return (
        f"{hours:02}:{minutes:02}:"
        f"{whole_seconds:02},{milliseconds:03}"
    )


def create_subtitles(scenes: list[dict], duration: float, path: Path) -> None:
    """Create approximate scene-timed subtitles from narration text."""
    if not scenes:
        raise ValueError("No scenes are available for subtitles.")

    weights = [
        max(len(scene.get("narration_text", "").strip()), 1)
        for scene in scenes
    ]
    total_weight = sum(weights)
    current_time = 0.0
    entries = []

    for index, (scene, weight) in enumerate(zip(scenes, weights), start=1):
        end_time = (
            duration
            if index == len(scenes)
            else current_time + duration * weight / total_weight
        )
        text = scene.get("narration_text", "").strip()
        if text:
            entries.append(
                f"{index}\n"
                f"{seconds_to_srt_time(current_time)} --> "
                f"{seconds_to_srt_time(end_time)}\n"
                f"{text}\n"
            )
        current_time = end_time

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(entries), encoding="utf-8-sig")


def generate_narration(script: str, language: str, output_path: Path) -> None:
    voice = VOICES.get(language.lower(), VOICES["en"])
    output_path.parent.mkdir(parents=True, exist_ok=True)

    import sys

    command = [
        sys.executable, "-m", "edge_tts",
        "--text", script,
        "--voice", voice,
        "--write-media", str(output_path),
    ]
    result = subprocess.run(command, capture_output=True, text=True)

    if result.returncode != 0 or not output_path.is_file():
        raise RuntimeError(
            "Narration generation failed: " + result.stderr[-2000:]
        )


def process_job(job_id: str) -> None:
    try:
        job = update_job(
            job_id, status="running", progress=5, error=None, result=None
        )
        if not job:
            return

        request_data = job["request"]
        script = request_data["script"].strip()
        language = request_data.get("narration_language", "en")

        if not script:
            raise ValueError("The script cannot be empty.")

        update_job(job_id, progress=10)

        narration_path = INPUT_DIR / f"narration_{job_id}.mp3"
        generate_narration(script, language, narration_path)

        update_job(job_id, progress=30)

        match_result = match_script_to_footage(script)
        scenes = match_result.get("scenes", [])

        if not scenes:
            raise RuntimeError("The script planner returned no scenes.")

        clip_paths = []
        matched_scenes = []

        for scene in scenes:
            footage = scene.get("footage", {})
            metadata = footage.get("metadata", {})
            local_path = metadata.get("local_path")

            if footage.get("status") == "downloaded" and local_path:
                clip_path = Path(local_path)
                if clip_path.is_file():
                    clip_paths.append(clip_path)
                    matched_scenes.append(scene)

        if not clip_paths:
            raise RuntimeError(
                "No usable B-roll clips were found. "
                "Check the footage API key, internet connection, "
                "and scene-footage manifest."
            )

        if len(clip_paths) != len(scenes):
            raise RuntimeError(
                f"Only {len(clip_paths)} of {len(scenes)} scenes "
                "have footage. Rendering stopped to avoid silently "
                "omitting parts of the narration."
            )

        update_job(job_id, progress=60)

        # Subtitle timing is estimated from each scene's text length.
        # It is not forced-aligned to the exact spoken words.
        from app.services.video_renderer import probe_duration

        audio_duration = probe_duration(narration_path)
        subtitle_path = SUBTITLE_DIR / f"{job_id}.srt"
        create_subtitles(scenes, audio_duration, subtitle_path)

        update_job(job_id, progress=70)

        output_name = f"{job_id}.mp4"
        manifest = render_video(
            narration_path=narration_path,
            clip_paths=clip_paths,
            output_name=output_name,
            subtitle_path=subtitle_path,
        )

        update_job(
            job_id,
            status="succeeded",
            progress=100,
            result={
                "video_file": manifest["output_file"],
                "manifest_file": manifest["manifest_file"],
                "subtitle_file": str(subtitle_path),
                "duration_seconds": manifest["output_duration_seconds"],
                "resolution": manifest["resolution"],
                "scene_count": manifest["scene_count"],
                "warnings": [
                    "Footage selection uses metadata keyword matching.",
                    "Subtitle timing is estimated, not word-level aligned.",
                    "Human visual relevance review is still required.",
                ],
            },
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