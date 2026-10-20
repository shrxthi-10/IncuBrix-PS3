import json
import os
import re
from pathlib import Path
from typing import Any

import requests
from dotenv import load_dotenv

# Load project environment variables without hardcoding API credentials.
ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")

API_KEY = os.getenv("PIXABAY_API_KEY")
API_URL = "https://pixabay.com/api/videos/"

BROLL_DIR = ROOT / "test_inputs" / "broll"
METADATA_DIR = ROOT / "outputs" / "clip_metadata"

REQUEST_TIMEOUT = (15, 120)
MAX_RESULTS = 20

# Words that are common in prompts but contribute little to topic matching.
STOP_WORDS = {
    "a", "an", "the", "and", "or", "but", "for", "to", "of",
    "in", "on", "at", "by", "with", "from", "into", "over",
    "under", "near", "is", "are", "was", "were", "be", "being",
    "this", "that", "these", "those", "it", "its", "their",
    "they", "them", "we", "our", "you", "your", "i", "my",
    "show", "shows", "showing", "about", "video", "footage",
    "clip", "scene", "real", "beautiful", "best", "high",
    "quality", "view", "shot", "visual", "visuals",
}

# Basic variants help common singular/plural matches.
# This is deliberately simple, not a full linguistic stemmer.
WORD_VARIANTS = {
    "flowers": "flower",
    "birds": "bird",
    "animals": "animal",
    "children": "child",
    "people": "person",
    "persons": "person",
    "villages": "village",
    "forests": "forest",
    "trees": "tree",
    "leaves": "leaf",
    "machines": "machine",
    "factories": "factory",
    "buses": "bus",
    "cars": "car",
    "trucks": "truck",
    "robots": "robot",
    "sensors": "sensor",
    "conveyors": "conveyor",
    "fruits": "fruit",
    "vegetables": "vegetable",
    "farmers": "farmer",
    "fields": "field",
    "mountains": "mountain",
    "rivers": "river",
    "beaches": "beach",
    "buildings": "building",
    "dancers": "dancer",
    "musicians": "musician",
    "dogs": "dog",
    "cats": "cat",
    "horses": "horse",
    "fishes": "fish",
}


def words(text: str) -> set[str]:
    """Normalize text into lowercase searchable words."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    normalized = {
        WORD_VARIANTS.get(token, token)
        for token in tokens
        if token not in STOP_WORDS and len(token) > 1
    }
    return normalized


def search_videos(query: str, per_page: int = MAX_RESULTS) -> list[dict]:
    """Search Pixabay for video candidates."""
    if not API_KEY or API_KEY == "PASTE_YOUR_KEY_HERE":
        raise RuntimeError(
            "Configure PIXABAY_API_KEY in the project's .env file."
        )

    if not query or not query.strip():
        raise ValueError("A non-empty footage search query is required.")

    response = requests.get(
        API_URL,
        params={
            "key": API_KEY,
            "q": query.strip(),
            "video_type": "film",
            "per_page": min(max(int(per_page), 3), MAX_RESULTS),
            "safesearch": "true",
        },
        timeout=30,
    )
    response.raise_for_status()

    data = response.json()
    hits = data.get("hits", [])

    if not isinstance(hits, list):
        raise RuntimeError("Pixabay returned an unexpected search response.")

    return hits


def choose_rendition(video: dict) -> dict | None:
    """Choose a usable video rendition, preferring medium-size footage."""
    renditions = video.get("videos") or {}

    # Prefer medium for practical download sizes. Use large when medium
    # is unavailable, then smaller renditions as a fallback.
    for name in ("medium", "large", "small", "tiny"):
        rendition = renditions.get(name) or {}
        if rendition.get("url"):
            return rendition

    # Handle an unexpected API rendition layout gracefully.
    for rendition in renditions.values():
        if isinstance(rendition, dict) and rendition.get("url"):
            return rendition

    return None


def select_video(
    query: str,
    videos: list[dict],
    excluded_ids: set | None = None,
) -> dict | None:
    """
    Rank candidates using scene-query words and Pixabay tags.

    This is metadata-based keyword matching, not visual AI verification.
    """
    excluded_ids = excluded_ids or set()
    query_words = words(query)

    if not query_words:
        return None

    ranked: list[tuple[int, int, int, dict, dict, set[str]]] = []

    for video in videos:
        video_id = video.get("id")

        if video_id is None or video_id in excluded_ids:
            continue

        tags_text = str(video.get("tags") or "")
        tag_words = words(tags_text)

        if not tag_words:
            continue

        overlap = query_words & tag_words

        # Do not select completely unrelated clips just to fill a scene.
        if not overlap:
            continue

        # Score topic-specific overlap. No industrial-only or nature-only
        # exclusions are applied, so the same function supports many topics.
        score = len(overlap) * 10

        # Longer matched words often carry more topic information.
        score += sum(min(len(word), 12) for word in overlap)

        # Give a modest bonus when a candidate matches several query terms.
        if len(query_words) > 1 and overlap == query_words:
            score += 8

        rendition = choose_rendition(video)
        if rendition is None:
            continue

        width = int(rendition.get("width") or 0)
        height = int(rendition.get("height") or 0)

        # Resolution is a tie-breaker, not a reason to reject relevant clips.
        quality_bonus = 0
        if width >= 1280 and height >= 720:
            quality_bonus = 3
        elif width >= 640 and height >= 360:
            quality_bonus = 1

        score += quality_bonus

        ranked.append(
            (
                score,
                len(overlap),
                quality_bonus,
                video,
                rendition,
                overlap,
            )
        )

    if not ranked:
        return None

    # Stable ordering makes repeated test runs easier to compare.
    ranked.sort(
        key=lambda item: (
            -item[0],
            -item[1],
            -item[2],
            int(item[3].get("id") or 0),
        )
    )

    score, _, _, video, rendition, overlap = ranked[0]

    return {
        "video_id": video.get("id"),
        "tags": video.get("tags", ""),
        "duration_seconds": video.get("duration"),
        "source_page": video.get("pageURL"),
        "download_url": rendition["url"],
        "width": rendition.get("width"),
        "height": rendition.get("height"),
        "keyword_overlap_count": len(overlap),
        "matched_keywords": sorted(overlap),
        "relevance_score": score,
        "relevance_method": "topic_neutral_keyword_overlap",
        "licence_status": "requires_review",
    }


def _download_selected_video(
    selected: dict,
    query: str,
) -> dict:
    """Download one selected video safely and write its metadata."""
    BROLL_DIR.mkdir(parents=True, exist_ok=True)
    METADATA_DIR.mkdir(parents=True, exist_ok=True)

    clip_id = selected["video_id"]
    output_path = BROLL_DIR / f"pixabay_{clip_id}.mp4"
    metadata_path = METADATA_DIR / f"pixabay_{clip_id}.json"
    partial_path = output_path.with_suffix(".mp4.part")

    try:
        # Keep existing files intact; download only if this clip is missing.
        if not output_path.is_file() or output_path.stat().st_size == 0:
            partial_path.unlink(missing_ok=True)

            with requests.get(
                selected["download_url"],
                stream=True,
                timeout=REQUEST_TIMEOUT,
            ) as response:
                response.raise_for_status()

                content_type = response.headers.get(
                    "Content-Type", ""
                ).lower()

                if (
                    "text/html" in content_type
                    or "application/json" in content_type
                ):
                    raise RuntimeError(
                        "The selected URL did not return video content."
                    )

                with partial_path.open("wb") as file:
                    for chunk in response.iter_content(
                        chunk_size=256 * 1024
                    ):
                        if chunk:
                            file.write(chunk)

            if not partial_path.is_file() or partial_path.stat().st_size == 0:
                raise RuntimeError("The downloaded video file is empty.")

            # Publish the file only after a complete download.
            partial_path.replace(output_path)

    except Exception:
        partial_path.unlink(missing_ok=True)
        raise

    metadata = {
        **selected,
        "query": query,
        "local_path": str(output_path.resolve()),
        "metadata_path": str(metadata_path.resolve()),
        "licence_status": "requires_review",
    }

    metadata_path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "status": "downloaded",
        "filename": output_path.name,
        "size_bytes": output_path.stat().st_size,
        "metadata": metadata,
    }


def download_video(
    query: str,
    excluded_ids: set | None = None,
) -> dict:
    """Search, rank, download, and record a distinct candidate video."""
    excluded_ids = excluded_ids or set()

    try:
        videos = search_videos(query)
        selected = select_video(
            query,
            videos,
            excluded_ids=excluded_ids,
        )

        if selected is None:
            return {
                "status": "no_match",
                "query": query,
                "message": (
                    "No candidate matched the query tags after "
                    "duplicate exclusion. Try a more descriptive query."
                ),
            }

        return _download_selected_video(selected, query)

    except (requests.RequestException, ValueError, RuntimeError) as exc:
        return {
            "status": "error",
            "query": query,
            "message": str(exc),
            "relevance_method": "topic_neutral_keyword_overlap",
        }


def download_video_by_id(video_id: int) -> dict:
    """
    Download an exact video ID if it appears in a current Pixabay search.

    Pixabay search results are query-dependent. If the requested ID is not
    returned, this function reports that instead of choosing another clip.
    """
    if not isinstance(video_id, int) or video_id <= 0:
        return {
            "status": "invalid_id",
            "video_id": video_id,
            "message": "Video ID must be a positive integer.",
        }

    query = "video"
    try:
        videos = search_videos(query)
    except (requests.RequestException, ValueError, RuntimeError) as exc:
        return {
            "status": "error",
            "video_id": video_id,
            "message": str(exc),
        }

    selected_video = next(
        (video for video in videos if video.get("id") == video_id),
        None,
    )

    if selected_video is None:
        return {
            "status": "not_found",
            "video_id": video_id,
            "message": (
                "This ID was not returned by the current Pixabay search. "
                "No substitute video was downloaded."
            ),
        }

    rendition = choose_rendition(selected_video)
    if rendition is None:
        return {
            "status": "no_download_url",
            "video_id": video_id,
            "message": "Pixabay did not provide a usable video rendition.",
        }

    selected = {
        "video_id": video_id,
        "tags": selected_video.get("tags", ""),
        "duration_seconds": selected_video.get("duration"),
        "source_page": selected_video.get("pageURL"),
        "download_url": rendition["url"],
        "width": rendition.get("width"),
        "height": rendition.get("height"),
        "keyword_overlap_count": 0,
        "matched_keywords": [],
        "relevance_score": None,
        "relevance_method": "exact_id_lookup_not_relevance_verified",
        "licence_status": "requires_review",
    }

    try:
        result = _download_selected_video(selected, query)
        result["metadata"]["relevance_method"] = (
            "exact_id_lookup_not_relevance_verified"
        )
        return result
    except (requests.RequestException, OSError, ValueError, RuntimeError) as exc:
        return {
            "status": "error",
            "video_id": video_id,
            "message": str(exc),
        }


if __name__ == "__main__":
    test_queries = [
        "rural village people walking",
        "birds flying in a forest",
        "fresh vegetables being harvested on a farm",
        "industrial conveyor packaging machine",
    ]

    for search_query in test_queries:
        print(f"\nSearching Pixabay for: {search_query}")
        result = download_video(search_query)
        print(json.dumps(result, indent=2, ensure_ascii=False))