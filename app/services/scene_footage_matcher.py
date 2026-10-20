import json
import re
from pathlib import Path

from app.services.scene_planner import plan_scenes
from app.services.footage_downloader import download_video, words

ROOT = Path(__file__).resolve().parents[2]
MANIFEST_DIR = ROOT / "outputs" / "scene_manifests"


def search_queries_for_scene(text: str) -> list[str]:
    """
    Build topic-neutral search queries from narration.
    These are keyword queries, not AI-generated visual descriptions.
    """
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    stop_words = {
        "a", "an", "the", "and", "or", "but", "for", "to", "of",
        "in", "on", "at", "by", "with", "from", "into", "over",
        "under", "is", "are", "was", "were", "be", "this", "that",
        "it", "its", "they", "their", "we", "our", "you", "your",
        "i", "my", "as", "can", "will", "helps", "help", "improves",
        "improve", "uses", "use", "using", "makes", "make", "show",
        "shows", "showing", "explains", "explained", "how", "why",
    }

    normalized = []
    for token in tokens:
        if token in stop_words or len(token) < 3:
            continue
        # Keep simple plural normalization consistent with downloader.
        token_set = words(token)
        normalized.extend(sorted(token_set) if token_set else [token])

    # Preserve first occurrence while removing duplicates.
    keywords = list(dict.fromkeys(normalized))

    if not keywords:
        return [text.strip()[:100]] if text.strip() else []

    # Search Pixabay using a short, scene-specific phrase first.
    queries = []

    if len(keywords) >= 3:
        queries.append(" ".join(keywords[:5]))

    if len(keywords) >= 2:
        queries.append(" ".join(keywords[:3]))

    queries.append(" ".join(keywords[:2]))
    queries.append(keywords[0])

    # Avoid repeating the same query.
    return list(dict.fromkeys(query for query in queries if query.strip()))


def match_script_to_footage(script: str) -> dict:
    """Plan scenes, search for distinct footage, and save a manifest."""
    scenes = plan_scenes(script)
    results = []
    used_video_ids: set[int] = set()

    for scene in scenes:
        narration = scene.get("narration_text", "").strip()
        queries = search_queries_for_scene(narration)
        footage = None
        selected_query = None
        query_errors = []

        # Do not force old industrial clips onto new scripts.
        # Each scene searches from its own narration keywords.
        for query in queries:
            try:
                candidate = download_video(
                    query,
                    excluded_ids=set(used_video_ids),
                )
            except Exception as exc:
                query_errors.append({
                    "query": query,
                    "message": str(exc),
                })
                continue

            if candidate.get("status") != "downloaded":
                query_errors.append({
                    "query": query,
                    "status": candidate.get("status"),
                    "message": candidate.get("message", "No matching clip."),
                })
                continue

            metadata = candidate.get("metadata") or {}
            video_id = metadata.get("video_id")

            if video_id is None or video_id in used_video_ids:
                continue

            footage = candidate
            selected_query = query
            used_video_ids.add(video_id)
            break

        if footage is None:
            footage = {
                "status": "no_match",
                "message": (
                    "No distinct clip matched this scene's search terms. "
                    "No unrelated fallback clip was assigned."
                ),
                "queries_checked": queries,
            }

        metadata = footage.get("metadata") or {}
        video_id = metadata.get("video_id")

        matched_keywords = metadata.get("matched_keywords", [])

        results.append({
            **scene,
            "search_queries_attempted": queries,
            "selected_search_query": selected_query,
            "query_errors": query_errors,
            "footage": footage,
            "visual_verification": "not_performed",
            "visual_role": "not visually verified",
            "semantic_match_note": (
                "Candidate selected by metadata keyword overlap. "
                "Inspect the actual video before treating it as relevant."
                if video_id is not None
                else "No candidate selected; do not substitute unrelated footage."
            ),
            "matched_keywords": matched_keywords,
            "licence_status": "requires_review",
        })

    MANIFEST_DIR.mkdir(parents=True, exist_ok=True)

    manifest = {
        "scene_count": len(results),
        "scenes": results,
        "matching_method": "scene_keywords_and_pixabay_tags",
        "limitations": [
            "Keyword matching does not establish visual relevance.",
            "Pixabay tags may be incomplete or misleading.",
            "Inspect every selected clip before submitting the final video.",
            "Review source terms and licensing before distribution.",
            "Scenes without a suitable match remain unmatched rather than "
            "being assigned unrelated footage.",
        ],
    }

    manifest_path = MANIFEST_DIR / "scene_footage_manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "manifest_path": str(manifest_path),
        **manifest,
    }


if __name__ == "__main__":
    test_script = (
        "A peaceful village wakes up as birds sing in the trees. "
        "Farmers harvest fresh vegetables from the fields. "
        "The village market fills with colorful fruits."
    )

    result = match_script_to_footage(test_script)
    print(json.dumps(result, indent=2, ensure_ascii=False))