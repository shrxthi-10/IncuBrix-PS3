from pathlib import Path
from threading import Lock
from typing import Any

import av

_original_av_open = av.open

def _compatible_av_open(*args, **kwargs):
    kwargs.pop("metadata_errors", None)
    return _original_av_open(*args, **kwargs)

av.open = _compatible_av_open

ROOT = Path(__file__).resolve().parents[2]
MODEL_NAME = "tiny"

_model = None
_model_lock = Lock()


def get_model() -> Any:
    """Load the transcription dependency/model only when audio is processed."""
    global _model

    with _model_lock:
        if _model is None:
            from faster_whisper import WhisperModel

            _model = WhisperModel(
                MODEL_NAME,
                device="cpu",
                compute_type="int8",
            )

    return _model


def transcribe_audio(audio_path: str | Path) -> dict:
    """Transcribe an audio file and return its text and detected language."""
    path = Path(audio_path).resolve()

    if not path.is_file():
        raise FileNotFoundError(f"Audio file not found: {path}")

    if path.suffix.lower() not in {".mp3", ".wav", ".m4a"}:
        raise ValueError("Supported audio formats are MP3, WAV, and M4A.")

    model = get_model()

    segments, info = model.transcribe(
        str(path),
        beam_size=1,
        vad_filter=True,
    )

    # Consume the generator to perform the transcription.
    transcript_parts = [
        segment.text.strip()
        for segment in segments
        if segment.text.strip()
    ]

    transcript = " ".join(transcript_parts).strip()

    if not transcript:
        raise ValueError(
            "No speech was detected. Please upload a clearer audio recording."
        )

    return {
        "transcript": transcript,
        "language": info.language,
        "language_probability": round(info.language_probability, 4),
        "model": MODEL_NAME,
    }