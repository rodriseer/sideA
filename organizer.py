"""
Organizer: copies images into category folders.

Categories: Events, Portraits, Crowd, Stage, Indoor, Night, Formal, Misc
"""

import os
import shutil
from typing import Literal

from classifier import CATEGORIES

Category = Literal["Events", "Portraits", "Crowd", "Stage", "Indoor", "Night", "Formal", "Misc"]


def ensure_category_dirs(base_output_dir: str) -> None:
    """Ensure all category subdirectories exist."""
    os.makedirs(base_output_dir, exist_ok=True)
    for category in CATEGORIES:
        os.makedirs(os.path.join(base_output_dir, category), exist_ok=True)


def copy_to_category(
    image_path: str,
    base_output_dir: str,
    category: Category,
) -> str:
    """
    Copy the image into the appropriate category folder.

    Returns the full path of the copied file.
    """
    ensure_category_dirs(base_output_dir)
    filename = os.path.basename(image_path)
    category_dir = os.path.join(base_output_dir, category)
    os.makedirs(category_dir, exist_ok=True)
    destination_path = os.path.join(category_dir, filename)
    shutil.copy2(image_path, destination_path)
    return destination_path
