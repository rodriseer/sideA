"""
Classifier for photographer-friendly categories.

Maps Google Vision labels to simple folder categories:
Events, Portraits, Crowd, Stage, Indoor, Night, Formal, Misc
"""

from typing import Dict, List, Tuple

# Category order for priority (first match wins in some cases)
CATEGORIES = ("Events", "Portraits", "Crowd", "Stage", "Indoor", "Night", "Formal", "Misc")

EVENTS_INDICATORS = {
    "event", "celebration", "party", "wedding", "concert", "conference",
    "gathering", "festival", "ceremony", "reception", "banquet",
}

PORTRAITS_INDICATORS = {
    "person", "face", "portrait", "selfie", "human", "adult", "child",
}

CROWD_INDICATORS = {
    "crowd", "group", "people", "audience", "crowded",
}

STAGE_INDICATORS = {
    "stage", "performance", "theater", "theatre", "concert", "speaker",
    "presentation", "podium",
}

INDOOR_INDICATORS = {
    "indoor", "room", "furniture", "ceiling", "floor", "wall", "walls",
    "interior", "building",
}

NIGHT_INDICATORS = {
    "night", "nightlife", "dark", "nighttime", "evening", "dusk",
}

FORMAL_INDICATORS = {
    "suit", "formal", "business", "professional", "corporate",
    "office", "meeting",
}


def _normalize_label(description: str) -> str:
    return description.strip().lower()


def _count_matches(labels: List[str], indicators: set) -> int:
    label_set = {_normalize_label(lbl) for lbl in labels}
    return sum(1 for ind in indicators if ind in label_set)


def classify_image(
    label_data: List[Dict[str, float]],
    face_count: int,
    ocr_text: str,
) -> str:
    """
    Classify an image into a photographer-friendly category.

    Categories: Events, Portraits, Crowd, Stage, Indoor, Night, Formal, Misc
    """
    labels = [_normalize_label(item["description"]) for item in label_data]
    label_set = set(labels)

    # Crowd: many people
    if face_count >= 3 or _count_matches(labels, CROWD_INDICATORS) > 0:
        return "Crowd"

    # Portraits: 1-2 faces, person-focused
    if face_count >= 1 and face_count <= 2:
        if _count_matches(labels, PORTRAITS_INDICATORS) > 0 or "person" in label_set or "face" in label_set:
            return "Portraits"

    # Stage: performance, presentation
    if _count_matches(labels, STAGE_INDICATORS) > 0:
        return "Stage"

    # Events: celebrations, parties, weddings
    if _count_matches(labels, EVENTS_INDICATORS) > 0:
        return "Events"

    # Night
    if _count_matches(labels, NIGHT_INDICATORS) > 0:
        return "Night"

    # Formal
    if _count_matches(labels, FORMAL_INDICATORS) > 0:
        return "Formal"

    # Indoor
    if _count_matches(labels, INDOOR_INDICATORS) > 0:
        return "Indoor"

    return "Misc"


def summarize_labels(label_data: List[Dict[str, float]], top_k: int = 5) -> Tuple[str, str]:
    """Return (top_labels, confidence_summary) for metadata/debugging."""
    sorted_labels = sorted(label_data, key=lambda x: x.get("score", 0.0), reverse=True)
    top = sorted_labels[:top_k]
    top_labels = ", ".join(label["description"] for label in top)
    confidence_summary = "; ".join(
        f"{label['description']}({label['score']:.2f})" for label in top
    )
    return top_labels, confidence_summary
