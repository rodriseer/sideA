"""
Side_A - Photo organization pipeline.

Processes images with Google Vision, classifies into photographer-friendly
categories, and organizes into folders. Metadata CSV is optional (debug only).
"""

import logging
import os
from typing import Callable, Dict, List, Optional

from classifier import CATEGORIES, classify_image, summarize_labels
from metadata import append_metadata_row, current_timestamp_iso
from organizer import copy_to_category
from vision_client import analyze_image, check_vision_credentials, get_vision_client


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
)
logger = logging.getLogger("side_a")


INPUT_DIR = "input_images"
OUTPUT_DIR = "organized_output"

SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".gif"}

# Set to True for debugging (writes metadata.csv)
WRITE_METADATA = os.environ.get("SIDE_A_DEBUG", "").lower() in ("1", "true", "yes")


def _is_image_file(filename: str) -> bool:
    _, ext = os.path.splitext(filename)
    return ext.lower() in SUPPORTED_EXTENSIONS


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
    """Return list of image file paths in the given directory."""
    if not os.path.exists(input_dir):
        os.makedirs(input_dir, exist_ok=True)
        return []

    images = []
    for entry in os.listdir(input_dir):
        full_path = os.path.join(input_dir, entry)
        if os.path.isfile(full_path) and _is_image_file(entry):
            images.append(full_path)
    return images


def process_image(
    image_path: str,
    output_dir: str,
    client,
    write_metadata: bool,
    metadata_csv_path: Optional[str],
) -> str:
    """Process one image. Returns the category it was assigned to."""
    analysis = analyze_image(image_path, client=client)
    labels = analysis.get("labels", [])
    faces = analysis.get("faces", [])
    ocr_text = analysis.get("text", "") or ""

    face_count = len(faces)
    category = classify_image(labels, face_count, ocr_text)

    copy_to_category(image_path, output_dir, category)

    if write_metadata and metadata_csv_path:
        top_labels, confidence_summary = summarize_labels(labels)
        row = {
            "filename": os.path.basename(image_path),
            "original_path": os.path.abspath(image_path),
            "new_path": os.path.abspath(os.path.join(output_dir, category, os.path.basename(image_path))),
            "category": category,
            "top_labels": top_labels,
            "face_count": str(face_count),
            "confidence_summary": confidence_summary,
            "date_processed": current_timestamp_iso(),
        }
        append_metadata_row(metadata_csv_path, row)

    return category


def run_processing(
    input_dir: str,
    output_dir: str,
    status_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int, Optional[str], Optional[str]], None]] = None,
    write_metadata: bool = False,
) -> tuple[bool, str, Optional[Dict]]:
    """
    Run the photo organization pipeline.

    Returns:
        (success, message, summary_dict)
        summary_dict: {"total": N, "folders": [...], "by_category": {...}}
    """
    def status(msg: str) -> None:
        logger.info("%s", msg)
        if status_callback:
            status_callback(msg)

    try:
        status("Scanning photos...")
        images = get_input_images(input_dir)

        if not images:
            return False, "No supported image files were found in this folder.", None

        status(f"Found {len(images)} photo(s).")
        status("Connecting to Google Vision...")

        ok, cred_msg, _ = check_vision_credentials()
        if not ok:
            return False, cred_msg, None

        client = get_vision_client()

        status("Creating folders...")
        from organizer import ensure_category_dirs
        ensure_category_dirs(output_dir)

        metadata_csv_path = os.path.join(output_dir, "metadata.csv") if write_metadata else None

        total = len(images)
        by_category: Dict[str, int] = {c: 0 for c in CATEGORIES}

        for i, image_path in enumerate(images, 1):
            status(f"Processing {i} of {total}...")
            try:
                category = process_image(
                    image_path,
                    output_dir=output_dir,
                    client=client,
                    write_metadata=write_metadata,
                    metadata_csv_path=metadata_csv_path,
                )
                by_category[category] = by_category.get(category, 0) + 1
                if progress_callback:
                    progress_callback(i, total, image_path, category)
            except Exception as exc:
                logger.error("Failed to process %s: %s", image_path, exc)
                status(f"  Skipped: {os.path.basename(image_path)}")
                if progress_callback:
                    progress_callback(i, total, image_path, None)

        folders_created = [c for c in CATEGORIES if by_category.get(c, 0) > 0]
        summary = {
            "total": total,
            "folders": folders_created,
            "by_category": {k: v for k, v in by_category.items() if v > 0},
        }

        status("Done!")
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
        f"Folders created: {len(summary['folders'])}",
        "",
        "Images per category:",
    ]
    for cat, count in sorted(summary.get("by_category", {}).items(), key=lambda x: -x[1]):
        lines.append(f"  • {cat}: {count}")
    return "\n".join(lines)


def main() -> None:
    logger.info("Starting Side_A automatic photo organization.")
    success, msg, summary = run_processing(
        INPUT_DIR,
        OUTPUT_DIR,
        write_metadata=WRITE_METADATA,
    )
    if not success:
        logger.error("%s", msg)
    else:
        logger.info("%s", format_summary(summary) if summary else msg)


if __name__ == "__main__":
    main()
