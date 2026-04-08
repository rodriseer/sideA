import json
import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import branding
from bundle_paths import get_runtime_base_dir
from google.cloud import vision
from google.cloud.vision_v1 import types

from user_settings import get_saved_credentials_path

try:
    from google.auth.exceptions import DefaultCredentialsError
except ImportError:
    DefaultCredentialsError = Exception  # fallback if google-auth structure changes


logger = logging.getLogger(__name__)

CREDENTIALS_ERROR_MESSAGE = branding.MSG_VISION_CREDENTIALS_REQUIRED

DEFAULT_CREDENTIALS_PATH = Path("keys") / "vision-key.json"


def validate_service_account_json_file(path: str) -> Tuple[bool, str]:
    """
    Return (ok, error_message). Ensures the file looks like a Google service account key
    (not an API key or unrelated JSON).
    """
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError:
        return False, "That file is not valid JSON."
    except OSError as exc:
        return False, f"Could not read the file: {exc}"
    if not isinstance(data, dict):
        return False, "That file is not a valid credentials file."
    if data.get("type") != "service_account":
        return (
            False,
            "Please choose a Google Cloud service account JSON file (from Google Cloud Console → IAM → Service accounts).",
        )
    return True, ""


def _get_app_base() -> Path:
    """Directory for optional keys/ next to the bundle (macOS) or exe (Windows)."""
    return get_runtime_base_dir()


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

    saved = get_saved_credentials_path()
    if saved:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved
        logger.info("Using credentials from app user settings: %s", saved)
        return True, "", saved

    base = _get_app_base()
    default_path = base / DEFAULT_CREDENTIALS_PATH
    if default_path.is_file():
        abs_path = str(default_path.resolve())
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = abs_path
        logger.info("Using credentials from app folder: %s", abs_path)
        return True, "", abs_path

    msg = (
        f"{branding.MSG_VISION_CREDENTIALS_REQUIRED}\n\n"
        f"{branding.CREDENTIALS_CLI_HINT}\n\n"
        f"Optional for developers: place a service account JSON next to the app at:\n  {default_path.resolve()}"
    )
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

    # Single request for performance: LABEL_DETECTION + FACE_DETECTION + TEXT_DETECTION
    features = [
        types.Feature(type_=vision.Feature.Type.LABEL_DETECTION),
        types.Feature(type_=vision.Feature.Type.FACE_DETECTION),
        types.Feature(type_=vision.Feature.Type.TEXT_DETECTION),
    ]
    response = client.annotate_image({"image": image, "features": features})

    if response.error.message:
        logger.error("Vision annotate_image error for %s: %s", image_path, response.error.message)
        raise RuntimeError(response.error.message)

    labels: List[Dict[str, Any]] = [
        {"description": label.description, "score": float(label.score)}
        for label in (response.label_annotations or [])
    ]

    faces = list(response.face_annotations or [])

    text_content = ""
    if response.text_annotations:
        text_content = response.text_annotations[0].description or ""

    return {
        "labels": labels,
        "faces": faces,
        "text": text_content,
    }

