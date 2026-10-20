import asyncio
import json
import re
import shutil
import subprocess
from datetime import datetime
from pathlib import Path

import edge_tts
import imageio_ffmpeg

from app.services.scene_footage_matcher import match_script_to_footage

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs"
BROLL_DIR = ROOT / "test_inputs" / "broll"
MANIFEST = OUTPUT_DIR / "scene_manifests" / "scene_footage_manifest.json"

FFMPEG = imageio_ffmpeg.get_ffmpeg_exe()

VOICE = "en-US-AriaNeural"
WIDTH = 1280
HEIGHT = 720
FPS = 24

DEFAULT_SCRIPT = (
    "Factory automation improves production quality. "
    "Sensors monitor machine conditions. "
    "Conveyor systems transport products efficiently."
)


def run_ffmpeg(command: list[str], timeout: int = 300) -> None:
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg command failed:\n" + result.stderr[-6000:]
        )


def timestamp(seconds: float) -> str:
    total_ms = round(seconds * 1000)
    hours, remainder = divmod(total_ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, milliseconds = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{milliseconds:03}"


def split_caption(text: str) -> list[str]:
    words = text.split()
    if len(words) <= 9:
        return [text]

    midpoint = (len(words) + 1) // 2
    return [
        " ".join(words[:midpoint]),
        " ".join(words[midpoint:]),
    ]


def wrap_caption(text: str, max_words: int = 9) -> str:
    words = text.split()
    return "\n".join(
        " ".join(words[i:i + max_words])
        for i in range(0, len(words), max_words)
    )


async def create_narration(script: str, path: Path) -> None:
    voice = edge_tts.Communicate(script, VOICE, rate="+0%")
    await voice.save(str(path))


def get_audio_duration(path: Path) -> float:
    result = subprocess.run(
        [FFMPEG, "-hide_banner", "-i", str(path), "-f", "null", "-"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )

    match = re.search(
        r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)",
        result.stderr,
    )
    if not match:
        raise RuntimeError(
            "Could not determine narration duration:\n"
            + result.stderr[-2000:]
        )

    hours, minutes, seconds = match.groups()
    duration = int(hours) * 3600 + int(minutes) * 60 + float(seconds)

    if duration <= 0:
        raise RuntimeError("The narration audio has zero duration.")

    return duration


def create_subtitles(
    scenes: list[dict],
    durations: list[float],
    path: Path,
) -> None:
    current_time = 0.0
    cue_number = 1

    with path.open("w", encoding="utf-8-sig", newline="\n") as file:
        for scene, duration in zip(scenes, durations):
            phrases = split_caption(scene["narration_text"].strip())
            phrase_duration = duration / len(phrases)

            for index, phrase in enumerate(phrases):
                start = current_time + index * phrase_duration
                end = current_time + (index + 1) * phrase_duration

                file.write(f"{cue_number}\n")
                file.write(
                    f"{timestamp(start)} --> {timestamp(end)}\n"
                )
                file.write(wrap_caption(phrase) + "\n\n")
                cue_number += 1

            current_time += duration


def find_clip_path(footage: dict) -> Path:
    metadata = footage.get("metadata", {})

    local_path = metadata.get("local_path")
    if local_path:
        path = Path(local_path)
        if path.is_file():
            return path

    filename = footage.get("filename")
    if filename:
        path = BROLL_DIR / filename
        if path.is_file():
            return path

    video_id = metadata.get("video_id")
    if video_id is not None:
        path = BROLL_DIR / f"pixabay_{video_id}.mp4"
        if path.is_file():
            return path

    raise FileNotFoundError(
        "The selected footage file could not be found. "
        f"Footage record: {json.dumps(footage, ensure_ascii=False)}"
    )


def render_broll_video(script: str = DEFAULT_SCRIPT) -> dict:
    script = script.strip()
    if not script:
        raise ValueError("The narration script cannot be empty.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Unique filenames prevent overwriting previous rendered videos.
    run_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_video = OUTPUT_DIR / f"incubrix_generated_{run_id}.mp4"
    output_audio = OUTPUT_DIR / f"narration_{run_id}.mp3"
    output_srt = OUTPUT_DIR / f"subtitles_{run_id}.srt"
    concat_file = OUTPUT_DIR / f"render_list_{run_id}.txt"

    # Preserve the existing manifest before the matcher replaces it.
    if MANIFEST.exists():
        backup_manifest = (
            MANIFEST.parent / "scene_footage_manifest_before_auto_render.json"
        )
        if not backup_manifest.exists():
            shutil.copy2(MANIFEST, backup_manifest)

    # Match the footage to THIS script, not the previous example script.
    match_result = match_script_to_footage(script)
    scenes = match_result.get("scenes", [])

    if not scenes:
        raise RuntimeError("The scene matcher returned no scenes.")

    clips = []
    for scene in scenes:
        footage = scene.get("footage", {})
        if footage.get("status") != "downloaded":
            raise RuntimeError(
                f"No usable footage was selected for "
                f"scene {scene.get('scene_id')}. "
                "Check the scene manifest and footage search results."
            )
        clips.append(find_clip_path(footage))

    # Generate narration from the supplied script.
    asyncio.run(create_narration(script, output_audio))
    audio_duration = get_audio_duration(output_audio)

    # Allocate scene durations proportionally to narration word counts.
    word_counts = [
        max(1, len(scene["narration_text"].split()))
        for scene in scenes
    ]
    total_words = sum(word_counts)
    durations = [
        audio_duration * count / total_words
        for count in word_counts
    ]

    create_subtitles(scenes, durations, output_srt)

    normalized_segments = []

    for index, (clip, duration) in enumerate(zip(clips, durations), start=1):
        segment = OUTPUT_DIR / f"scene_{run_id}_{index}.mp4"

        video_filter = (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            f"fps={FPS},setsar=1,format=yuv420p"
        )

        run_ffmpeg([
            FFMPEG, "-y",
            "-stream_loop", "-1",
            "-i", str(clip),
            "-t", f"{duration:.3f}",
            "-vf", video_filter,
            "-an",
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "24",
            "-pix_fmt", "yuv420p",
            "-r", str(FPS),
            "-movflags", "+faststart",
            str(segment),
        ])

        normalized_segments.append(segment)

    with concat_file.open("w", encoding="utf-8", newline="\n") as file:
        for segment in normalized_segments:
            safe_path = segment.resolve().as_posix().replace("'", r"'\''")
            file.write(f"file '{safe_path}'\n")

    subtitle_path = output_srt.resolve().as_posix()
    subtitle_path = subtitle_path.replace(":", r"\:").replace("'", r"\'")

    subtitle_filter = (
        f"subtitles='{subtitle_path}':"
        "force_style='FontName=Arial,FontSize=22,"
        "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
        "BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=35'"
    )

    run_ffmpeg([
        FFMPEG, "-y",
        "-f", "concat",
        "-safe", "0",
        "-i", str(concat_file),
        "-i", str(output_audio),
        "-vf", subtitle_filter,
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-c:v", "libx264",
        "-preset", "ultrafast",
        "-crf", "23",
        "-pix_fmt", "yuv420p",
        "-r", str(FPS),
        "-c:a", "aac",
        "-b:a", "160k",
        "-ar", "44100",
        "-ac", "2",
        "-t", f"{audio_duration:.3f}",
        "-movflags", "+faststart",
        str(output_video),
    ])

    return {
        "status": "success",
        "output": str(output_video),
        "size_bytes": output_video.stat().st_size,
        "audio": str(output_audio),
        "audio_duration_seconds": round(audio_duration, 2),
        "subtitles": str(output_srt),
        "scene_count": len(scenes),
        "scene_durations_seconds": [round(d, 2) for d in durations],
        "manifest_path": match_result.get("manifest_path"),
        "limitations": match_result.get("limitations", []),
        "note": (
            "Video rendered. Review visual relevance, licensing, "
            "subtitle timing, and audio synchronization before submission."
        ),
    }


if __name__ == "__main__":
    print("IncuBrix Script-to-B-roll Video Engine")
    print("Enter your narration script. Press Enter on an empty line to finish.")
    print("For a single-line script, press Enter twice after entering it.\n")

    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break

        if not line.strip():
            if lines:
                break
            continue

        lines.append(line.strip())

    script = " ".join(lines) if lines else DEFAULT_SCRIPT

    try:
        result = render_broll_video(script)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"\nVIDEO GENERATION FAILED: {exc}")
        raise