import csv
import os
from datetime import datetime, timezone
from typing import Dict


METADATA_COLUMNS = [
    "filename",
    "original_path",
    "category",
    "top_labels",
    "subject_tags",
    "environment_tags",
    "action_tags",
    "style_tags",
    "face_count",
    "confidence_summary",
    "approved",
    "date_processed",
]

SUGGESTED_KEYWORDS_COLUMNS = [
    "filename",
    "original_path",
    "suggested_keywords",
    "primary_category",
    "notes",
]


def _ensure_parent_dir(path: str) -> None:
    parent = os.path.dirname(path)
    if parent:
        os.makedirs(parent, exist_ok=True)


def append_metadata_row(csv_path: str, row: Dict[str, str]) -> None:
    """
    Append a row to the metadata CSV, creating the file and header if needed.
    """
    _ensure_parent_dir(csv_path)

    file_exists = os.path.exists(csv_path)
    with open(csv_path, mode="a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=METADATA_COLUMNS)
        if not file_exists:
            writer.writeheader()

        complete_row = {column: row.get(column, "") for column in METADATA_COLUMNS}
        writer.writerow(complete_row)


def append_suggested_keywords_row(csv_path: str, row: Dict[str, str]) -> None:
    """
    Append a row to the suggested keywords CSV, creating the file and header if needed.
    """
    _ensure_parent_dir(csv_path)

    file_exists = os.path.exists(csv_path)
    with open(csv_path, mode="a", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=SUGGESTED_KEYWORDS_COLUMNS)
        if not file_exists:
            writer.writeheader()

        complete_row = {column: row.get(column, "") for column in SUGGESTED_KEYWORDS_COLUMNS}
        writer.writerow(complete_row)


def current_timestamp_iso() -> str:
    """
    Return the current UTC timestamp in ISO 8601 format.
    """
    return datetime.now(timezone.utc).isoformat()

