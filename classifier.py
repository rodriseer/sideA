"""
Classifier for photographer-friendly categories.

Maps Google Vision labels to simple folder categories:
Outdoor, Indoor, Photobooth, Portrait, Group, Other
"""

from typing import Dict, List, Tuple

# Category order for priority (first match wins in some cases)
CATEGORIES = ("Photobooth", "Group", "Portrait", "Outdoor", "Indoor", "Other")

PHOTOBOOTH_INDICATORS = {
    "photo booth",
    "photobooth",
    "photo booth strip",
    "instant camera",
    "polaroid",
    "frame",
    "collage",
    "poster",
    "text",
}

PORTRAIT_INDICATORS = {
    "person",
    "face",
    "portrait",
    "selfie",
    "human",
    "headshot",
}

GROUP_INDICATORS = {
    "crowd",
    "group",
    "people",
    "audience",
    "team",
}

INDOOR_INDICATORS = {
    "indoor", "room", "furniture", "ceiling", "floor", "wall", "walls",
    "interior", "building", "studio", "lighting",
}

OUTDOOR_INDICATORS = {
    "outdoor",
    "nature",
    "sky",
    "tree",
    "grass",
    "park",
    "beach",
    "mountain",
    "landscape",
    "ocean",
    "forest",
    "sunlight",
    "city",
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

    Categories: Outdoor, Indoor, Photobooth, Portrait, Group, Other
    """
    labels = [_normalize_label(item["description"]) for item in label_data]
    label_set = set(labels)
    ocr_lower = (ocr_text or "").strip().lower()

    # Photobooth: explicit label or OCR cue
    if any(ind in ocr_lower for ind in ("photo booth", "photobooth")) or _count_matches(labels, PHOTOBOOTH_INDICATORS) > 0:
        return "Photobooth"

    # Group: many people
    if face_count >= 3 or _count_matches(labels, GROUP_INDICATORS) > 0:
        return "Group"

    # Portrait: 1-2 faces, person-focused
    if 1 <= face_count <= 2:
        if _count_matches(labels, PORTRAIT_INDICATORS) > 0 or "person" in label_set or "face" in label_set:
            return "Portrait"

    # Outdoor / Indoor
    if _count_matches(labels, OUTDOOR_INDICATORS) > 0:
        return "Outdoor"

    if _count_matches(labels, INDOOR_INDICATORS) > 0:
        return "Indoor"

    return "Other"


def summarize_labels(label_data: List[Dict[str, float]], top_k: int = 5) -> Tuple[str, str]:
    """Return (top_labels, confidence_summary) for metadata/debugging."""
    sorted_labels = sorted(label_data, key=lambda x: x.get("score", 0.0), reverse=True)
    top = sorted_labels[:top_k]
    top_labels = ", ".join(label["description"] for label in top)
    confidence_summary = "; ".join(
        f"{label['description']}({label['score']:.2f})" for label in top
    )
    return top_labels, confidence_summary
