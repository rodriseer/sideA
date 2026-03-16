import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from google.cloud import vision
from google.cloud.vision_v1 import types

try:
    from google.auth.exceptions import DefaultCredentialsError
except ImportError:
    DefaultCredentialsError = Exception  # fallback if google-auth structure changes


logger = logging.getLogger(__name__)

CREDENTIALS_ERROR_MESSAGE = (
    "Google Vision is not configured on this computer yet."
)

DEFAULT_CREDENTIALS_PATH = Path("keys") / "vision-key.json"


def _get_app_base() -> Path:
    """Return the app/project base directory (works for script and PyInstaller exe)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def ensure_credentials() -> Tuple[bool, str, Optional[str]]:
    """
    Ensure GOOGLE_APPLICATION_CREDENTIALS is set before creating the Vision client.

    1. If GOOGLE_APPLICATION_CREDENTIALS is already set, use it.
    2. If not set, look for keys/vision-key.json relative to the app location.
    3. If found, set the env var automatically.

    Returns:
        (ok, message, credential_path) - ok is True if credentials are configured.
        credential_path is the path being used (for logging), or None on failure.
    """
    existing = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if existing:
        path = Path(existing)
        if path.is_file():
            logger.info("Using credentials from GOOGLE_APPLICATION_CREDENTIALS: %s", existing)
            return True, "", existing
        logger.warning("GOOGLE_APPLICATION_CREDENTIALS points to missing file: %s", existing)

    base = _get_app_base()
    default_path = base / DEFAULT_CREDENTIALS_PATH
    if default_path.is_file():
        abs_path = str(default_path.resolve())
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
        logger.info("Using credentials from app folder: %s", abs_path)
        return True, "", abs_path

    msg = (
        "Google Vision is not configured on this computer yet.\n\n"
        "Place your service account key at:\n  %s\n\n"
        "Or set the GOOGLE_APPLICATION_CREDENTIALS environment variable."
    ) % str(default_path)
    logger.warning("Credentials not found at %s", default_path)
    return False, msg, None


def check_vision_credentials() -> Tuple[bool, str, Optional[str]]:
    """
    Verify that Google Vision credentials are available before processing.

    First calls ensure_credentials() to auto-set GOOGLE_APPLICATION_CREDENTIALS
    from keys/vision-key.json if not already set. Then validates with ADC.

    Returns:
        (ok, message, credential_path) - credential_path is set on success for display.
    """
    ok, msg, cred_path = ensure_credentials()
    if not ok:
        return False, msg, None

    try:
        import google.auth
        google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-vision"])
        return True, "", cred_path
    except DefaultCredentialsError:
        return False, CREDENTIALS_ERROR_MESSAGE, None
    except Exception as exc:
        err = str(exc).lower()
        if (
            "credentials" in err
            or "default credentials" in err
            or "authentication" in err
            or "google_application_credentials" in err
        ):
            return False, CREDENTIALS_ERROR_MESSAGE, None
        raise


def get_vision_client() -> vision.ImageAnnotatorClient:
    """
    Return a Google Cloud Vision ImageAnnotatorClient instance.

    Assumes GOOGLE_APPLICATION_CREDENTIALS is set in the environment.
    """
    return vision.ImageAnnotatorClient()


def _read_image_bytes(image_path: str) -> bytes:
    with open(image_path, "rb") as image_file:
        return image_file.read()


def analyze_image(
    image_path: str,
    client: Optional[vision.ImageAnnotatorClient] = None,
) -> Dict[str, Any]:
    """
    Analyze an image with Google Cloud Vision.

    Returns a dict with:
      - labels: List[Dict[description, score]]
      - faces: List[Dict] (currently only count is typically needed)
      - text: str (concatenated text, if any)
    """
    if client is None:
        client = get_vision_client()

    content = _read_image_bytes(image_path)
    image = types.Image(content=content)

    labels_result = client.label_detection(image=image)
    faces_result = client.face_detection(image=image)
    text_result = client.text_detection(image=image)

    if labels_result.error.message:
        logger.error("Label detection error for %s: %s", image_path, labels_result.error.message)
        raise RuntimeError(labels_result.error.message)

    if faces_result.error.message:
        logger.error("Face detection error for %s: %s", image_path, faces_result.error.message)
        raise RuntimeError(faces_result.error.message)

    if text_result.error.message:
        logger.error("Text detection error for %s: %s", image_path, text_result.error.message)
        raise RuntimeError(text_result.error.message)

    labels: List[Dict[str, Any]] = [
        {"description": label.description, "score": float(label.score)}
        for label in labels_result.label_annotations
    ]

    faces = list(faces_result.face_annotations)

    text_content = ""
    if text_result.text_annotations:
        # The first entry is usually the full text.
        text_content = text_result.text_annotations[0].description or ""

    return {
        "labels": labels,
        "faces": faces,
        "text": text_content,
    }

