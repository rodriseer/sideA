"""
Side_A - Lightroom-safe metadata tagging assistant.

Processes images with Google Vision, classifies into photographer-friendly
categories, and generates metadata + keyword suggestion outputs only.

This tool does not move or rename your original files.
"""

import logging
import os
import random
import argparse
from xml.etree import ElementTree as ET
from typing import Callable, Dict, List, Optional, Tuple

from classifier import CATEGORIES, classify_image
from metadata import append_metadata_row, append_suggested_keywords_row, current_timestamp_iso
from organizer import ensure_output_dirs, write_xmp_sidecar, xmp_sidecar_path_for_image
from vision_client import analyze_image, check_vision_credentials, get_vision_client


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("side_a")


INPUT_DIR = "input_images"
OUTPUT_DIR = "side_a_outputs"

SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
    # Common RAW extensions (best-effort; may not be analyzable by Vision directly)
    ".dng",
    ".cr2",
    ".cr3",
    ".nef",
    ".arw",
    ".raf",
    ".rw2",
    ".orf",
    ".srw",
}

RAW_EXTENSIONS = {
    ".cr2",
    ".cr3",
    ".nef",
    ".arw",
    ".orf",
    ".rw2",
    ".raf",
    ".dng",
}


def _is_image_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in SUPPORTED_EXTENSIONS


def _is_raw_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in RAW_EXTENSIONS


def _is_credentials_error(err_msg: str) -> bool:
    lower = err_msg.lower()
    return any(
        p in lower
        for p in (
            "credentials",
            "default credentials",
            "authentication",
            "google_application_credentials",
            "could not automatically determine",
            "your default credentials were not found",
        )
    )


def get_input_images(input_dir: str) -> List[str]:
    """Return list of image file paths in the given directory (recursive)."""
    if not os.path.exists(input_dir):
        return []

    images = []
    for root, _, files in os.walk(input_dir):
        for name in files:
            if _is_image_file(name):
                images.append(os.path.join(root, name))
    return images


def get_raw_files(input_dir: str) -> List[str]:
    """Return list of RAW file paths in the given directory (recursive)."""
    if not os.path.exists(input_dir):
        return []
    raws: List[str] = []
    for root, _, files in os.walk(input_dir):
        for name in files:
            if _is_raw_file(name):
                raws.append(os.path.join(root, name))
    return raws


def validate_xmp_keywords(xmp_path: str, expected_keywords: List[str]) -> Tuple[bool, str]:
    """
    Validate:
      - file exists
      - dc:subject contains expected keywords (case-insensitive)
    """
    if not os.path.isfile(xmp_path):
        return False, "XMP does not exist"

    try:
        tree = ET.parse(xmp_path)
        root = tree.getroot()
    except Exception as exc:
        return False, f"Invalid XML: {exc}"

    ns = {
        "dc": "http://purl.org/dc/elements/1.1/",
        "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#",
    }
    li_nodes = root.findall(".//dc:subject/rdf:Bag/rdf:li", namespaces=ns)
    found = {(n.text or "").strip().lower() for n in li_nodes if (n.text or "").strip()}
    expected = {k.strip().lower() for k in expected_keywords if k and k.strip()}

    missing = sorted([k for k in expected if k not in found])
    if missing:
        return False, f"Missing keywords in dc:subject: {', '.join(missing[:10])}"
    return True, "OK"


_GENERIC_TAGS = {
    "image",
    "photo",
    "snapshot",
    "stock photography",
    "wallpaper",
}

_BODY_PART_TAGS = {
    "forehead",
    "chin",
    "neck",
    "skin",
    "eyebrow",
    "eyelash",
    "nose",
    "mouth",
    "lip",
    "lips",
    "ear",
    "hand",
    "finger",
    "arm",
    "leg",
    "shoulder",
    "hair",
}

_TECHNICAL_TAGS = {
    "human body",
    "organism",
    "vertebrate",
    "mammal",
    "textile",
}

# Canonicalize similar concepts into a single keyword.
_TAG_SYNONYMS: Dict[str, str] = {
    # formal wear
    "suit": "formal wear",
    "blazer": "formal wear",
    "coat": "formal wear",
    "sports jacket": "formal wear",
    "tie": "formal wear",
    "tuxedo": "formal wear",
    # performance / stage
    "stage": "performance",
    "theatre": "performance",
    "theater": "performance",
    "performance": "performance",
    "concert": "performance",
    "speaker": "performance",
    "presentation": "performance",
    # clothing
    "outerwear": "clothing",
    "jacket": "clothing",
}

_SUBJECT_HINTS = {
    "person",
    "people",
    "human",
    "face",
    "man",
    "woman",
    "child",
    "boy",
    "girl",
    "baby",
    "couple",
    "group",
    "family",
    "dog",
    "cat",
}

_INDOOR_ENV_SIGNALS = {
    "interior",
    "indoor",
    "room",
    "church",
    "hall",
    "building",
    "lighting",
    "studio",
}

_OUTDOOR_ENV_SIGNALS = {
    "sky",
    "nature",
    "sunlight",
    "park",
    "beach",
    "ocean",
    "forest",
    "mountain",
    "city",
}

_EVENT_ENV_SIGNALS = {
    "performance",
    "crowd",
    "audience",
    "group",
}

_ACTION_HINTS = {
    "walking",
    "smiling",
    "posing",
    "dancing",
    "running",
    "singing",
    "talking",
    "laughing",
}

_STYLE_HINTS = {
    "candid",
    "photobooth",
    "selfie",
    "headshot",
}


def _clean_and_rank_tags(
    label_data: List[Dict[str, float]],
    *,
    max_tags: int = 7,
    min_score: float = 0.50,
) -> List[Tuple[str, float]]:
    """
    Return cleaned, ranked tags as [(tag, score), ...].

    - Removes generic tags
    - Normalizes to lowercase, trimmed
    - Removes duplicates
    - Keeps top N by score (after filtering)
    """
    cleaned: List[Tuple[str, float]] = []
    for item in label_data:
        desc = str(item.get("description", "") or "").strip().lower()
        score = float(item.get("score", 0.0) or 0.0)
        if not desc or score < min_score:
            continue
        if desc in _GENERIC_TAGS:
            continue
        if desc in _BODY_PART_TAGS:
            continue
        if desc in _TECHNICAL_TAGS:
            continue

        desc = _TAG_SYNONYMS.get(desc, desc)
        cleaned.append((desc, score))

    cleaned.sort(key=lambda x: x[1], reverse=True)

    seen = set()
    deduped: List[Tuple[str, float]] = []
    for tag, score in cleaned:
        if tag in seen:
            continue
        seen.add(tag)
        deduped.append((tag, score))
        if len(deduped) >= max_tags:
            break
    return deduped


def _comma_join(tags: List[str]) -> str:
    return ", ".join([t.strip().lower() for t in tags if t and t.strip()])


def _bucket_tags(
    cleaned_tags: List[str],
    *,
    category: str,
    face_count: int,
    ocr_text: str,
) -> Dict[str, List[str]]:
    """
    Split tags into subject/environment/action/style buckets using simple heuristics.
    """
    buckets: Dict[str, List[str]] = {
        "subject": [],
        "environment": [],
        "action": [],
        "style": [],
    }

    tag_set = set(cleaned_tags)
    ocr_lower = (ocr_text or "").lower()

    # Style rules (workflow-focused)
    if face_count == 1:
        buckets["style"].append("portrait")
        buckets["subject"].append("person")
    elif face_count == 2:
        buckets["style"].append("portrait")
        buckets["subject"] += ["people", "couple"]
    elif face_count > 2:
        buckets["style"].append("group")
        buckets["subject"] += ["people", "group"]

    # Photobooth cue (OCR or label)
    if "photo booth" in ocr_lower or "photobooth" in ocr_lower or "photobooth" in tag_set:
        buckets["style"].append("photobooth")

    for t in cleaned_tags:
        if t in _SUBJECT_HINTS:
            buckets["subject"].append(t)
        if t in _INDOOR_ENV_SIGNALS:
            buckets["environment"].append("indoor")
        if t in _OUTDOOR_ENV_SIGNALS:
            buckets["environment"].append("outdoor")
        if t in _EVENT_ENV_SIGNALS:
            buckets["environment"].append("event")
        if t in _ACTION_HINTS:
            buckets["action"].append(t)
        if t in _STYLE_HINTS:
            buckets["style"].append(t)

    # Stage/performance detected -> event style
    if "performance" in tag_set or any(t in tag_set for t in ("crowd", "audience")):
        buckets["style"].append("event")

    # Formal wear -> formal style
    if "formal wear" in tag_set:
        buckets["style"].append("formal")

    # De-dupe each bucket preserving order
    for k in list(buckets.keys()):
        seen = set()
        out: List[str] = []
        for t in buckets[k]:
            tt = t.strip().lower()
            if not tt or tt in seen:
                continue
            seen.add(tt)
            out.append(tt)
        buckets[k] = out

    return buckets


def _keywords_from_buckets(buckets: Dict[str, List[str]], top_tags: List[str]) -> str:
    # Lightroom-friendly: a single comma-separated keyword list
    kws: List[str] = []
    for key in ("style", "subject", "environment", "action"):
        kws.extend(buckets.get(key, []))
    kws.extend(top_tags)

    seen = set()
    out: List[str] = []
    for k in kws:
        kk = (k or "").strip().lower()
        if not kk or kk in _GENERIC_TAGS:
            continue
        if kk in seen:
            continue
        seen.add(kk)
        out.append(kk)
    return ", ".join(out[:25])


def process_image(
    image_path: str,
    output_dir: str,
    client,
    metadata_csv_path: str,
    suggested_keywords_csv_path: str,
    optional_xmp_dir: str,
) -> Tuple[str, int, bool, bool]:
    """
    Process one image.

    Returns:
        (category, tag_count, faces_detected, failed)
    """
    analysis = analyze_image(image_path, client=client)
    labels = analysis.get("labels", [])
    faces = analysis.get("faces", [])
    ocr_text = analysis.get("text", "") or ""

    face_count = len(faces)
    category = classify_image(labels, face_count, ocr_text)

    cleaned = _clean_and_rank_tags(labels, max_tags=7, min_score=0.50)
    cleaned_tags = [t for t, _s in cleaned]
    buckets = _bucket_tags(cleaned_tags, category=category, face_count=face_count, ocr_text=ocr_text)

    top_labels = _comma_join(cleaned_tags[:7])
    confidence_summary = "; ".join([f"{t}({s:.2f})" for t, s in cleaned[:5]])
    processed_at = current_timestamp_iso()

    append_metadata_row(
        metadata_csv_path,
        {
            "filename": os.path.basename(image_path),
            "original_path": os.path.abspath(image_path),
            "category": category,
            "top_labels": top_labels,
            "subject_tags": _comma_join(buckets["subject"]),
            "environment_tags": _comma_join(buckets["environment"]),
            "action_tags": _comma_join(buckets["action"]),
            "style_tags": _comma_join(buckets["style"]),
            "face_count": str(face_count),
            "confidence_summary": confidence_summary,
            "approved": "false",
            "date_processed": processed_at,
        },
    )

    suggested_keywords = _keywords_from_buckets(buckets, cleaned_tags)
    append_suggested_keywords_row(
        suggested_keywords_csv_path,
        {
            "filename": os.path.basename(image_path),
            "original_path": os.path.abspath(image_path),
            "suggested_keywords": suggested_keywords,
            "primary_category": category,
            "notes": "auto-generated",
        },
    )

    # Lightroom XMP sidecar export (written next to the image; original is untouched)
    keyword_list = [k.strip() for k in suggested_keywords.split(",") if k.strip()]
    if category and category.lower() not in {k.lower() for k in keyword_list}:
        keyword_list.insert(0, category)

    hierarchical: List[str] = []
    if category:
        hierarchical.append(f"Category|{category}")
    for s in buckets.get("style", []):
        hierarchical.append(f"Style|{s}")
    for e in buckets.get("environment", []):
        hierarchical.append(f"Environment|{e}")
    for sub in buckets.get("subject", []):
        hierarchical.append(f"Subject|{sub}")

    xmp_path = xmp_sidecar_path_for_image(image_path)
    write_xmp_sidecar(xmp_path, keywords=keyword_list, hierarchical_keywords=hierarchical)

    return category, len(cleaned_tags), face_count > 0, False


def run_processing(
    input_dir: str,
    output_dir: str,
    status_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, Optional[str], Optional[str]], None]] = None,
) -> tuple[bool, str, Optional[Dict]]:
    """
    Run the Lightroom-safe metadata pipeline.

    Returns:
        (success, message, summary_dict)
        summary_dict: {"total": N, "by_category": {...}, "outputs": {...}}
    """
    def status(msg: str) -> None:
        logger.info("%s", msg)
        if status_callback:
            status_callback(msg)

    try:
        status("Analyzing folder (no files will be moved or modified)...")
        images = get_input_images(input_dir)

        if not images:
            return False, "No supported image files were found in this folder.", None

        status(f"Analyzing {len(images)} image(s)...")
        status("Connecting to Google Vision...")

        ok, cred_msg, _ = check_vision_credentials()
        if not ok:
            return False, cred_msg, None

        client = get_vision_client()

        status("Preparing output files...")
        metadata_csv_path, suggested_keywords_csv_path, optional_xmp_dir = ensure_output_dirs(output_dir)

        total = len(images)
        by_category: Dict[str, int] = {c: 0 for c in CATEGORIES}
        failed_images = 0
        faces_detected_images = 0
        total_tag_count = 0

        for i, image_path in enumerate(images, 1):
            status(f"Tagging {i} of {total}: {os.path.basename(image_path)}")
            try:
                category, tag_count, faces_detected, _failed = process_image(
                    image_path,
                    output_dir=output_dir,
                    client=client,
                    metadata_csv_path=metadata_csv_path,
                    suggested_keywords_csv_path=suggested_keywords_csv_path,
                    optional_xmp_dir=optional_xmp_dir,
                )
                by_category[category] = by_category.get(category, 0) + 1
                total_tag_count += tag_count
                if faces_detected:
                    faces_detected_images += 1
                if progress_callback:
                    progress_callback(i, total, image_path, category)
            except Exception as exc:
                logger.error("Failed to process %s: %s", image_path, exc)
                failed_images += 1
                status(f"Skipped (failed): {os.path.basename(image_path)}")
                if progress_callback:
                    progress_callback(i, total, image_path, None)

        avg_tags = (total_tag_count / max(1, (total - failed_images))) if total else 0.0

        # Write run summary report
        run_summary_path = os.path.join(output_dir, "run_summary.txt")
        try:
            with open(run_summary_path, "w", encoding="utf-8") as f:
                f.write("Side_A run summary\n")
                f.write("==================\n\n")
                f.write(f"total images processed: {total}\n")
                f.write(f"number of outdoor / indoor / photobooth: {by_category.get('Outdoor',0)} / {by_category.get('Indoor',0)} / {by_category.get('Photobooth',0)}\n")
                f.write(f"average number of tags per image: {avg_tags:.2f}\n")
                f.write(f"number of images with faces detected: {faces_detected_images}\n")
                f.write(f"number of failed images: {failed_images}\n")
        except Exception as exc:
            status(f"Warning: could not write run_summary.txt ({exc})")

        summary = {
            "total": total,
            "by_category": {k: v for k, v in by_category.items() if v > 0},
            "outputs": {
                "metadata_csv": os.path.abspath(metadata_csv_path),
                "suggested_keywords_csv": os.path.abspath(suggested_keywords_csv_path),
                "optional_xmp_dir": os.path.abspath(optional_xmp_dir),
                "run_summary_txt": os.path.abspath(run_summary_path),
            },
            "failed": failed_images,
            "faces_detected_images": faces_detected_images,
            "avg_tags_per_image": avg_tags,
        }

        status("Tagging complete.")
        status("Metadata exported successfully.")
        status("No files were moved or modified.")
        return True, "", summary

    except Exception as exc:
        err_msg = str(exc)
        logger.exception("Processing failed")
        if _is_credentials_error(err_msg):
            return False, "Google Vision is not configured on this computer yet.", None
        return False, err_msg, None


def format_summary(summary: Dict) -> str:
    """Format summary for display."""
    lines = [
        f"Total images processed: {summary['total']}",
        "",
        "Images per category:",
    ]
    for cat, count in sorted(summary.get("by_category", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  • {cat}: {count}")
    outputs = summary.get("outputs") or {}
    if outputs:
        lines += [
            "",
            "Outputs:",
            f"  • metadata.csv: {outputs.get('metadata_csv','')}",
            f"  • suggested_keywords.csv: {outputs.get('suggested_keywords_csv','')}",
            f"  • optional_xmp/: {outputs.get('optional_xmp_dir','')}",
            f"  • run_summary.txt: {outputs.get('run_summary_txt','')}",
        ]
    lines += [
        "",
        f"Images with faces detected: {summary.get('faces_detected_images', 0)}",
        f"Failed images: {summary.get('failed', 0)}",
        f"Avg tags per image: {summary.get('avg_tags_per_image', 0.0):.2f}",
    ]
    return "\n".join(lines)


def demo_print_sample(input_dir: str, *, seed: Optional[int] = None) -> None:
    """
    Quick terminal demo helper: prints one sample's predicted category + top tags.
    """
    images = get_input_images(input_dir)
    if not images:
        print("No supported image files found.")
        return

    if seed is not None:
        random.seed(seed)
    sample = random.choice(images)

    ok, cred_msg, _ = check_vision_credentials()
    if not ok:
        print(cred_msg)
        return

    client = get_vision_client()
    analysis = analyze_image(sample, client=client)
    labels = analysis.get("labels", [])
    faces = analysis.get("faces", [])
    ocr_text = analysis.get("text", "") or ""

    face_count = len(faces)
    category = classify_image(labels, face_count, ocr_text)
    cleaned = _clean_and_rank_tags(labels, max_tags=7, min_score=0.50)
    top_tags = ", ".join([t for t, _s in cleaned[:7]])

    print("Sample image:", os.path.abspath(sample))
    print("Predicted category:", category)
    print("Top tags:", top_tags)


def run_xmp_raw_test(input_dir: str, *, limit: Optional[int] = None) -> int:
    """
    RAW-focused integration test:
      - scans RAW files
      - generates XMP sidecars next to RAW files
      - prints filename, xmp path, keywords written
      - validates that dc:subject contains those keywords
    """
    raws = get_raw_files(input_dir)
    if not raws:
        print("No RAW files found.")
        return 2

    ok, cred_msg, _ = check_vision_credentials()
    if not ok:
        print(cred_msg)
        return 2

    client = get_vision_client()
    count = 0
    failures = 0
    for raw_path in raws:
        count += 1
        if limit and count > limit:
            break

        try:
            # Best-effort analysis: some RAW formats may not be readable by Vision directly.
            analysis = analyze_image(raw_path, client=client)
            labels = analysis.get("labels", [])
            faces = analysis.get("faces", [])
            ocr_text = analysis.get("text", "") or ""
        except Exception:
            labels = []
            faces = []
            ocr_text = ""

        face_count = len(faces)
        category = classify_image(labels, face_count, ocr_text)
        cleaned = _clean_and_rank_tags(labels, max_tags=7, min_score=0.50)
        cleaned_tags = [t for t, _s in cleaned]
        buckets = _bucket_tags(cleaned_tags, category=category, face_count=face_count, ocr_text=ocr_text)
        suggested_keywords = _keywords_from_buckets(buckets, cleaned_tags)

        keyword_list = [k.strip() for k in suggested_keywords.split(",") if k.strip()]
        if category and category.lower() not in {k.lower() for k in keyword_list}:
            keyword_list.insert(0, category)

        hierarchical: List[str] = []
        if category:
            hierarchical.append(f"Category|{category}")
        for s in buckets.get("style", []):
            hierarchical.append(f"Style|{s}")
        for e in buckets.get("environment", []):
            hierarchical.append(f"Environment|{e}")
        for sub in buckets.get("subject", []):
            hierarchical.append(f"Subject|{sub}")

        xmp_path = xmp_sidecar_path_for_image(raw_path)
        write_xmp_sidecar(xmp_path, keywords=keyword_list, hierarchical_keywords=hierarchical)

        valid, msg = validate_xmp_keywords(xmp_path, keyword_list)
        status = "OK" if valid else "FAIL"
        if not valid:
            failures += 1

        print(f"RAW: {os.path.basename(raw_path)}")
        print(f"XMP: {xmp_path} [{status}]")
        print(f"Keywords: {', '.join(keyword_list)}")
        if not valid:
            print(f"Validator: {msg}")
        print("")

    return 0 if failures == 0 else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Side_A - Lightroom-safe metadata tagging assistant")
    parser.add_argument("--input", default=INPUT_DIR, help="Input folder to scan")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Output folder for CSV/report outputs")
    parser.add_argument(
        "--mode",
        default="run",
        choices=["run", "test-xmp-raw", "demo-sample"],
        help="Run pipeline or RAW-focused XMP integration test",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit files in test mode (0 = no limit)")
    args = parser.parse_args()

    if args.mode == "demo-sample":
        demo_print_sample(args.input)
        return

    if args.mode == "test-xmp-raw":
        raise SystemExit(run_xmp_raw_test(args.input, limit=(args.limit or None)))

    logger.info("Starting Side_A Lightroom-safe metadata tagging.")
    success, msg, summary = run_processing(args.input, args.output)
    if not success:
        logger.error("%s", msg)
    else:
        logger.info("%s", format_summary(summary) if summary else msg)


if __name__ == "__main__":
    main()
