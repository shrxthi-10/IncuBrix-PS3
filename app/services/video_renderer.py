import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUTPUT_DIR = ROOT / "outputs" / "rendered_videos"
MANIFEST_DIR = ROOT / "outputs" / "render_manifests"

VIDEO_WIDTH = 854
VIDEO_HEIGHT = 480
FPS = 25


def probe_duration(path: Path) -> float:
    command = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]
    result = subprocess.run(
        command, capture_output=True, text=True, check=True
    )
    return float(result.stdout.strip())


def escape_subtitle_path(path: Path) -> str:
    """Escape a Windows path for FFmpeg's subtitles filter."""
    value = path.resolve().as_posix()
    value = value.replace(":", r"\:")
    value = value.replace("'", r"\'")
    return value


def render_video(
    narration_path: str | Path,
    clip_paths: list[str | Path],
    output_name: str = "first_render.mp4",
    subtitle_path: str | Path | None = None,
) -> dict:
    """Render narrated video with optional burned-in SRT subtitles."""
    narration = Path(narration_path).resolve()
    clips = [Path(p).resolve() for p in clip_paths]
    subtitles = Path(subtitle_path).resolve() if subtitle_path else None

    if not narration.is_file():
        raise FileNotFoundError(f"Narration not found: {narration}")
    if not clips:
        raise ValueError("At least one video clip is required.")
    for clip in clips:
        if not clip.is_file():
            raise FileNotFoundError(f"Video clip not found: {clip}")
    if subtitles is not None and not subtitles.is_file():
        raise FileNotFoundError(f"Subtitle file not found: {subtitles}")

    audio_duration = probe_duration(narration)
    if audio_duration <= 0:
        raise ValueError("Narration duration must be positive.")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    output_path = OUTPUT_DIR / output_name
    intermediate_path = OUTPUT_DIR / f"{output_path.stem}_intermediate.mp4"

    scene_duration = audio_duration / len(clips)

    command = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "warning"]
    for clip in clips:
        command.extend(["-i", str(clip)])
    command.extend(["-i", str(narration)])

    filters = []
    for i in range(len(clips)):
        filters.append(
            f"[{i}:v]"
            f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
            "(ow-iw)/2:(oh-ih)/2:color=black,"
            "setsar=1,fps=25,format=yuv420p,"
            f"trim=duration={scene_duration:.6f},"
            "setpts=PTS-STARTPTS"
            f"[v{i}]"
        )

    video_inputs = "".join(f"[v{i}]" for i in range(len(clips)))
    filters.append(
        f"{video_inputs}concat=n={len(clips)}:v=1:a=0,"
        f"trim=duration={audio_duration:.6f},"
        "setpts=PTS-STARTPTS[vout]"
    )

    audio_index = len(clips)
    filters.append(
        f"[{audio_index}:a]"
        "aresample=48000,"
        f"atrim=duration={audio_duration:.6f},"
        "asetpts=PTS-STARTPTS[aout]"
    )

    command.extend([
        "-filter_complex", ";".join(filters),
        "-map", "[vout]",
        "-map", "[aout]",
        "-t", f"{audio_duration:.6f}",
        "-c:v", "libx264", "-threads", "1", "-preset", "ultrafast", "-crf", "28",
        "-pix_fmt", "yuv420p",
        "-c:a", "aac",
        "-b:a", "128k",
        "-movflags", "+faststart",
        str(intermediate_path),
    ])

    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0:
        raise RuntimeError(
            "FFmpeg rendering failed:\n" + completed.stderr[-5000:]
        )

    # Burn subtitles in a second pass if an SRT file was provided.
    if subtitles is not None:
        subtitle_filter = (
            f"subtitles=filename='{escape_subtitle_path(subtitles)}':"
            "force_style='FontName=Arial,FontSize=24,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
            "BorderStyle=1,Outline=2,Shadow=1,Alignment=2,MarginV=35'"
        )
        subtitle_command = [
            "ffmpeg", "-y", "-hide_banner", "-loglevel", "warning",
            "-i", str(intermediate_path),
            "-vf", subtitle_filter,
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "23",
            "-pix_fmt", "yuv420p",
            "-c:a", "copy",
            "-movflags", "+faststart",
            str(output_path),
        ]
        completed = subprocess.run(
            subtitle_command, capture_output=True, text=True
        )
        if completed.returncode != 0:
            raise RuntimeError(
                "Subtitle rendering failed:\n" + completed.stderr[-5000:]
            )
        intermediate_path.unlink(missing_ok=True)
    else:
        intermediate_path.replace(output_path)

    video_duration = probe_duration(output_path)

    manifest = {
        "output_file": str(output_path),
        "narration_file": str(narration),
        "source_clips": [str(p) for p in clips],
        "subtitle_file": str(subtitles) if subtitles else None,
        "subtitles_burned_in": subtitles is not None,
        "scene_count": len(clips),
        "scene_duration_seconds": scene_duration,
        "narration_duration_seconds": audio_duration,
        "output_duration_seconds": video_duration,
        "resolution": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}",
        "fps": FPS,
        "video_codec": "h264",
        "audio_codec": "aac",
        "render_status": "success",
        "visual_verification": "not_performed",
    }

    manifest_path = MANIFEST_DIR / f"{output_path.stem}_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    manifest["manifest_file"] = str(manifest_path)
    return manifest


if __name__ == "__main__":
    result = render_video(
        narration_path=ROOT / "test_inputs" / "sample_narration.mp3",
        clip_paths=[
            ROOT / "test_inputs" / "broll" / "pixabay_243201.mp4",
            ROOT / "test_inputs" / "broll" / "pixabay_130226.mp4",
            ROOT / "test_inputs" / "broll" / "pixabay_288051.mp4",
        ],
        output_name="village_test_auto_subtitles.mp4",
        subtitle_path=ROOT / "test_inputs" / "sample_subtitles.srt",
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))