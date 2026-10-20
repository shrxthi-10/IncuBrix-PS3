import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent

APP_NAME = "IncuBrix Script-to-B-roll Engine"
API_PREFIX = "/api/v1"

OUTPUT_DIR = Path(
    os.getenv("OUTPUT_DIR", str(PROJECT_ROOT / "outputs"))
)

TEST_INPUT_DIR = Path(
    os.getenv("TEST_INPUT_DIR", str(PROJECT_ROOT / "test_inputs"))
)

MAX_AUDIO_SECONDS = int(os.getenv("MAX_AUDIO_SECONDS", "600"))
DEFAULT_ASPECT_RATIO = os.getenv("DEFAULT_ASPECT_RATIO", "16:9")

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
TEST_INPUT_DIR.mkdir(parents=True, exist_ok=True)