import re
from typing import Any


def split_into_sentences(script: str) -> list[str]:
    """Split a script into readable sentence-based units."""
    cleaned = re.sub(r"\s+", " ", script).strip()

    if not cleaned:
        raise ValueError("The script cannot be empty.")

    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return [sentence.strip() for sentence in sentences if sentence.strip()]


def describe_visual(sentence: str) -> str:
    """Create a basic visual-search description from a sentence."""
    text = sentence.strip().rstrip(".!?")
    return f"Relevant real-world B-roll footage illustrating: {text}"


def plan_scenes(script: str) -> list[dict[str, Any]]:
    """Create a first-pass scene plan while preserving all script sentences."""
    sentences = split_into_sentences(script)
    scenes = []

    for index, sentence in enumerate(sentences, start=1):
        scenes.append({
            "scene_id": index,
            "narration_text": sentence,
            "visual_query": describe_visual(sentence),
            "start_seconds": None,
            "end_seconds": None,
            "duration_seconds": None,
        })

    return scenes


if __name__ == "__main__":
    sample_script = (
        "Smart factories use sensors to monitor machines. "
        "Automated systems detect faults before equipment fails. "
        "Predictive maintenance helps reduce unexpected downtime."
    )

    for scene in plan_scenes(sample_script):
        print(f"\nScene {scene['scene_id']}")
        print("Narration:", scene["narration_text"])
        print("Visual query:", scene["visual_query"])