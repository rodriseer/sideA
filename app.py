"""
Lightroom-safe metadata tagging pipeline (CLI).

User-facing strings live in branding.py.
"""

import logging
import os
import random
import argparse
import traceback
import time
from pathlib import Path
from xml.etree import ElementTree as ET
from typing import Callable, Dict, List, Optional, Tuple

import branding
from classifier import CATEGORIES, classify_image
from metadata import append_metadata_row, append_suggested_keywords_row, current_timestamp_iso
from organizer import ensure_output_dirs, write_xmp_sidecar, xmp_sidecar_path_for_image
from user_settings import apply_saved_credentials_to_environment
from vision_client import analyze_image, check_vision_credentials, get_vision_client


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("side_a")


INPUT_DIR = "input_images"
OUTPUT_DIR = branding.OUTPUTS_SUBFOLDER

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


def _extension_upper(path: str) -> str:
    return os.path.splitext(path)[1].lstrip(".").upper()


def _verify_readable_bytes(path: str) -> None:
    """
    Verify the file can be opened and read as bytes (basic sanity check).
    """
    with open(path, "rb") as f:
        _ = f.read(512)


def _generate_preview_jpeg_for_analysis(original_path: str, output_dir: str) -> str:
    """
    RAW/DNG fallback: generate a JPEG preview for Vision analysis only.
    The original file remains untouched.
    """
    try:
        import rawpy  # type: ignore
        import numpy as np  # type: ignore
        from PIL import Image
    except Exception as exc:
        raise RuntimeError(
            "RAW preview fallback requires rawpy + numpy + Pillow. "
            "Install dependencies and retry."
        ) from exc

    previews_dir = os.path.join(output_dir, "temp_previews")
    os.makedirs(previews_dir, exist_ok=True)

    base = os.path.splitext(os.path.basename(original_path))[0]
    preview_path = os.path.join(previews_dir, f"{base}.preview.jpg")

    with rawpy.imread(original_path) as raw:
        rgb = raw.postprocess(output_bps=8, no_auto_bright=True, use_camera_wb=True)
    if not isinstance(rgb, np.ndarray):
        raise RuntimeError("RAW preview conversion failed (no RGB data).")

    img = Image.fromarray(rgb)
    # Reduce size for faster upload/analysis (performance-focused).
    img.thumbnail((1600, 1600))
    img.save(preview_path, format="JPEG", quality=85, optimize=True)
    return preview_path


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
    keep_previews: bool,
) -> Tuple[str, int, bool, bool]:
    """
    Process one image.

    Returns:
        (category, tag_count, faces_detected, failed)
    """
    # RAW/DNG handling:
    # - verify bytes are readable
    # - attempt Vision analysis on original path
    # - if not reliable, fall back to JPEG preview conversion for analysis only
    start_total = time.perf_counter()
    _verify_readable_bytes(image_path)

    ext = os.path.splitext(image_path)[1].lower()
    tag_source = "original"
    analysis_source = "original"
    preview_path: Optional[str] = None

    # RAW/DNG performance path: ALWAYS analyze a preview JPEG instead of the RAW/DNG.
    if ext in RAW_EXTENSIONS:
        tag_source = "preview_fallback"
        analysis_source = "preview"
        start_prev = time.perf_counter()
        preview_path = _generate_preview_jpeg_for_analysis(image_path, output_dir=output_dir)
        preview_seconds = time.perf_counter() - start_prev
        logger.info("Preview generation: %.3fs (%s)", preview_seconds, os.path.basename(image_path))

        start_api = time.perf_counter()
        analysis = analyze_image(preview_path, client=client)
        api_seconds = time.perf_counter() - start_api
        logger.info("Vision API request: %.3fs (%s)", api_seconds, os.path.basename(image_path))
    else:
        start_api = time.perf_counter()
        analysis = analyze_image(image_path, client=client)
        api_seconds = time.perf_counter() - start_api
        logger.info("Vision API request: %.3fs (%s)", api_seconds, os.path.basename(image_path))
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
    processing_seconds = time.perf_counter() - start_total

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
            "tag_source": tag_source,
            "analysis_source": analysis_source,
            "processing_seconds": f"{processing_seconds:.3f}",
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

    # Cleanup preview unless configured to keep it
    if preview_path and not keep_previews:
        try:
            os.remove(preview_path)
        except Exception:
            pass

    return category, len(cleaned_tags), face_count > 0, False


def run_processing(
    input_dir: str,
    output_dir: str,
    status_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, Optional[str], Optional[str]], None]] = None,
    keep_previews: bool = False,
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
        apply_saved_credentials_to_environment()
        status(branding.MSG_PIPELINE_ANALYZING)
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
        errors_log_path = os.path.join(output_dir, "errors.log")
        if not os.path.exists(errors_log_path):
            with open(errors_log_path, "w", encoding="utf-8") as f:
                f.write("filename\tfull_path\textension\terror_message\ttraceback_summary\n")

        total = len(images)
        by_category: Dict[str, int] = {c: 0 for c in CATEGORIES}
        failed_images = 0
        faces_detected_images = 0
        total_tag_count = 0
        processed_successfully = 0

        for i, image_path in enumerate(images, 1):
            src = "preview" if os.path.splitext(image_path)[1].lower() in RAW_EXTENSIONS else "original"
            status(f"Tagging {i} of {total} ({src}): {os.path.basename(image_path)}")
            try:
                category, tag_count, faces_detected, _failed = process_image(
                    image_path,
                    output_dir=output_dir,
                    client=client,
                    metadata_csv_path=metadata_csv_path,
                    suggested_keywords_csv_path=suggested_keywords_csv_path,
                    optional_xmp_dir=optional_xmp_dir,
                    keep_previews=keep_previews,
                )
                by_category[category] = by_category.get(category, 0) + 1
                total_tag_count += tag_count
                processed_successfully += 1
                if faces_detected:
                    faces_detected_images += 1
                if progress_callback:
                    progress_callback(i, total, image_path, category)
            except Exception as exc:
                logger.exception("Failed to process %s", image_path)
                failed_images += 1
                status(f"Skipped (failed): {os.path.basename(image_path)}")
                tb_summary = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__, limit=6)).replace("\n", "\\n")
                with open(errors_log_path, "a", encoding="utf-8") as f:
                    f.write(
                        f"{os.path.basename(image_path)}\t{os.path.abspath(image_path)}\t{_extension_upper(image_path)}\t"
                        f"{str(exc).replace(chr(9),' ').replace(chr(10),' ').replace(chr(13),' ')}\t{tb_summary}\n"
                    )
                if progress_callback:
                    progress_callback(i, total, image_path, None)

        avg_tags = (total_tag_count / max(1, (total - failed_images))) if total else 0.0

        # Write run summary report
        run_summary_path = os.path.join(output_dir, "run_summary.txt")
        try:
            with open(run_summary_path, "w", encoding="utf-8") as f:
                f.write(f"{branding.RUN_SUMMARY_HEADER}\n")
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
                "errors_log": os.path.abspath(errors_log_path),
            },
            "failed": failed_images,
            "faces_detected_images": faces_detected_images,
            "avg_tags_per_image": avg_tags,
            "processed_successfully": processed_successfully,
        }

        status("Tagging complete.")
        status("Metadata exported successfully.")
        status(branding.MSG_PIPELINE_COMPLETE_ORIGINALS)
        status(branding.MSG_PIPELINE_COMPLETE_OUTPUTS)
        status(f"Processed successfully: {processed_successfully}")
        status(f"Failed: {failed_images}")
        if failed_images:
            status("See errors.log for details")
        return True, "", summary

    except Exception as exc:
        err_msg = str(exc)
        logger.exception("Processing failed")
        if _is_credentials_error(err_msg):
            return False, branding.MSG_VISION_CREDENTIALS_REQUIRED, None
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
        "",
        branding.APP_SAFETY_NOTE,
        branding.SUMMARY_OUTPUTS_NOTE,
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

    apply_saved_credentials_to_environment()
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

    apply_saved_credentials_to_environment()
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

        # In test mode, prefer preview analysis for RAWs (performance/path realism).
        try:
            preview_path = _generate_preview_jpeg_for_analysis(
                raw_path, output_dir=os.path.join(input_dir, branding.OUTPUTS_SUBFOLDER)
            )
            analysis = analyze_image(preview_path, client=client)
            labels = analysis.get("labels", [])
            faces = analysis.get("faces", [])
            ocr_text = analysis.get("text", "") or ""
            try:
                os.remove(preview_path)
            except Exception:
                pass
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
    parser = argparse.ArgumentParser(
        description=f"{branding.APP_NAME} — Lightroom-safe metadata tagging (CLI)"
    )
    parser.add_argument("--input", default=INPUT_DIR, help="Input folder to scan")
    parser.add_argument("--output", default=OUTPUT_DIR, help="Output folder for CSV/report outputs")
    parser.add_argument(
        "--mode",
        default="run",
        choices=["run", "test-xmp-raw", "demo-sample"],
        help="Run pipeline or RAW-focused XMP integration test",
    )
    parser.add_argument("--limit", type=int, default=0, help="Limit files in test mode (0 = no limit)")
    parser.add_argument("--keep-previews", action="store_true", help="Keep temp preview JPEGs after processing")
    args = parser.parse_args()

    if args.mode == "demo-sample":
        demo_print_sample(args.input)
        return

    if args.mode == "test-xmp-raw":
        raise SystemExit(run_xmp_raw_test(args.input, limit=(args.limit or None)))

    logger.info("Starting %s (CLI).", branding.APP_NAME)
    success, msg, summary = run_processing(args.input, args.output, keep_previews=args.keep_previews)
    if not success:
        logger.error("%s", msg)
    else:
        logger.info("%s", format_summary(summary) if summary else msg)


if __name__ == "__main__":
    main()
