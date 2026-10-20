import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VIDEO_DIR = ROOT / "outputs" / "rendered_videos"

VIDEO_NAMES = [
    "0f2b3fa5-1ea5-4e46-8e7a-84e13554bb4b.mp4",
    "c88ccfd8-ce5c-4ed2-8b62-831e57c99b3e.mp4",
    "78aa6088-6ef4-4daf-8a06-ea5fe2319870.mp4",
]


def inspect_video(path: Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe",
            "-v", "error",
            "-show_entries",
            "format=duration:stream=codec_type,width,height",
            "-of", "json",
            str(path),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(result.stdout)


def main():
    for name in VIDEO_NAMES:
        path = VIDEO_DIR / name
        print(f"\nChecking: {name}")

        if not path.is_file():
            print("FAIL: File not found")
            continue

        try:
            metadata = inspect_video(path)
            streams = metadata.get("streams", [])
            video_streams = [
                stream for stream in streams
                if stream.get("codec_type") == "video"
            ]
            audio_streams = [
                stream for stream in streams
                if stream.get("codec_type") == "audio"
            ]
            duration = float(
                metadata.get("format", {}).get("duration", 0)
            )

            valid = (
                duration > 0
                and bool(video_streams)
                and bool(audio_streams)
            )

            print(f"Duration: {duration:.2f} seconds")
            print(f"Video stream: {bool(video_streams)}")
            print(f"Audio stream: {bool(audio_streams)}")

            if video_streams:
                stream = video_streams[0]
                print(
                    f"Resolution: {stream.get('width')}x"
                    f"{stream.get('height')}"
                )

            print("PASS" if valid else "FAIL")

        except (subprocess.CalledProcessError, ValueError, json.JSONDecodeError) as exc:
            print(f"FAIL: {exc}")


if __name__ == "__main__":
    main()