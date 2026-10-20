import json
import subprocess
from pathlib import Path

import pytest

from tests.check_generated_videos import inspect_video


def test_inspect_video_reads_video_and_audio_metadata(monkeypatch, tmp_path):
    fake_metadata = {
        "format": {"duration": "12.5"},
        "streams": [
            {
                "codec_type": "video",
                "width": 1280,
                "height": 720,
            },
            {
                "codec_type": "audio",
            },
        ],
    }

    def fake_run(*args, **kwargs):
        return subprocess.CompletedProcess(
            args=args[0],
            returncode=0,
            stdout=json.dumps(fake_metadata),
            stderr="",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    result = inspect_video(tmp_path / "sample.mp4")

    assert float(result["format"]["duration"]) == 12.5
    assert result["streams"][0]["width"] == 1280
    assert result["streams"][1]["codec_type"] == "audio"


def test_inspect_video_reports_ffprobe_failure(monkeypatch, tmp_path):
    def fake_run(*args, **kwargs):
        raise subprocess.CalledProcessError(
            returncode=1,
            cmd=args[0],
            stderr="Invalid video file",
        )

    monkeypatch.setattr(subprocess, "run", fake_run)

    with pytest.raises(subprocess.CalledProcessError):
        inspect_video(tmp_path / "broken.mp4")