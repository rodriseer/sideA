"""
Per-user application configuration (credentials path, etc.).

Uses a writable user data directory so packaged / PyInstaller builds work when the
app lives in Program Files (no writes beside the .exe required).

Primary config file: config.json (migrates legacy settings.json if present).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, Optional

from branding import APP_CONFIG_SLUG

CONFIG_FILENAME = "config.json"
LEGACY_SETTINGS_FILENAME = "settings.json"


def _slug() -> str:
    """Stable per-user folder name; set APP_CONFIG_SLUG in branding.py."""
    s = (APP_CONFIG_SLUG or "").strip()
    return "".join(c if c.isalnum() else "_" for c in s).strip("_") or "PhotoMetadataApp"


def get_settings_dir() -> Path:
    """Writable per-user directory for config.json (works with PyInstaller onefile)."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA", "")
        if base:
            return Path(base) / _slug()
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / _slug()
    return Path.home() / ".config" / _slug()


def get_config_path() -> Path:
    """Path to the local app config file (config.json)."""
    return get_settings_dir() / CONFIG_FILENAME


def get_settings_path() -> Path:
    """Alias for get_config_path() (backward compatibility)."""
    return get_config_path()


def _legacy_settings_path() -> Path:
    return get_settings_dir() / LEGACY_SETTINGS_FILENAME


def _default_settings() -> Dict[str, Any]:
    return {
        "google_application_credentials_path": "",
    }


def _migrate_legacy_if_needed() -> None:
    """If only settings.json exists, copy it to config.json once."""
    new_path = get_config_path()
    old_path = _legacy_settings_path()
    if new_path.is_file() or not old_path.is_file():
        return
    try:
        with open(old_path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            merged = _default_settings()
            merged.update(data)
            new_path.parent.mkdir(parents=True, exist_ok=True)
            with open(new_path, "w", encoding="utf-8") as f:
                json.dump(merged, f, indent=2)
    except Exception:
        pass


def load_settings() -> Dict[str, Any]:
    _migrate_legacy_if_needed()
    path = get_config_path()
    if not path.is_file():
        return _default_settings()
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return _default_settings()
        out = _default_settings()
        out.update(data)
        return out
    except Exception:
        return _default_settings()


def save_settings(settings: Dict[str, Any]) -> None:
    path = get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2)


def get_saved_credentials_path() -> Optional[str]:
    """Absolute path to the saved service-account JSON if the file still exists."""
    raw = (load_settings().get("google_application_credentials_path") or "").strip()
    if not raw:
        return None
    p = Path(raw)
    return str(p.resolve()) if p.is_file() else None


def get_configured_credentials_path_raw() -> str:
    """Path string stored in config (may be missing on disk)."""
    return (load_settings().get("google_application_credentials_path") or "").strip()


def is_saved_credentials_file_missing() -> bool:
    """True if config lists a path but that file is not found (moved or deleted)."""
    raw = get_configured_credentials_path_raw()
    if not raw:
        return False
    return not Path(raw).is_file()


def set_saved_credentials_path(path: str) -> None:
    settings = load_settings()
    settings["google_application_credentials_path"] = (path or "").strip()
    save_settings(settings)


def apply_saved_credentials_to_environment() -> None:
    """
    Apply the saved Google Cloud service-account JSON path from config.json.

    If config holds a valid file path, sets GOOGLE_APPLICATION_CREDENTIALS for this
    process (in-app choice wins). If not, leaves an already-valid env var in place
    (CLI / developer use). PyInstaller-safe: config lives under the user data dir.
    """
    saved = get_saved_credentials_path()
    if saved:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = saved
        return
    existing = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS", "").strip()
    if existing and Path(existing).is_file():
        return
