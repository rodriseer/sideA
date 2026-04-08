"""
Resolve directories for PyInstaller bundles (Windows .exe, macOS .app).

- Read-only assets (background images, bundled data): search sys._MEIPASS, then
  platform-typical bundle locations, then the runtime base.
- Optional keys/vision-key.json: folder *beside* the .app on macOS (or beside the
  .exe on Windows), not inside the signed bundle.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def meipass_dir() -> Optional[Path]:
    """PyInstaller extract dir (onefile) or internal payload dir (onedir), when set."""
    if is_frozen() and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return None


def get_macos_app_bundle_path() -> Optional[Path]:
    """
    If the executable lives under Something.app/Contents/MacOS/, return the
    Something.app path.
    """
    if not is_frozen() or sys.platform != "darwin":
        return None
    p = Path(sys.executable).resolve()
    for ancestor in p.parents:
        if ancestor.suffix == ".app" and ancestor.is_dir():
            return ancestor
    return None


def get_runtime_base_dir() -> Path:
    """
    Writable-adjacent folder for optional files (e.g. keys/vision-key.json).

    macOS: parent directory of the .app (so keys can live next to the bundle).
    Windows/Linux frozen: directory containing the main executable.
    Dev: project root (this repo folder).
    """
    if not is_frozen():
        return Path(__file__).resolve().parent

    bundle = get_macos_app_bundle_path()
    if bundle is not None:
        return bundle.parent

    return Path(sys.executable).resolve().parent


def get_resource_search_dirs() -> List[Path]:
    """
    Ordered directories to search for bundled read-only assets (e.g. background.png).

    Includes _MEIPASS, macOS Contents/Resources when present, the executable
    directory, runtime base, and (in dev) ./public and project root.
    """
    dirs: List[Path] = []

    mp = meipass_dir()
    if mp is not None:
        dirs.append(mp)

    if is_frozen():
        dirs.append(Path(sys.executable).resolve().parent)
        bundle = get_macos_app_bundle_path()
        if bundle is not None:
            res = bundle / "Contents" / "Resources"
            if res.is_dir():
                dirs.append(res)
        dirs.append(get_runtime_base_dir())
    else:
        proj = Path(__file__).resolve().parent
        dirs.extend([proj / "public", proj])

    return _dedupe_preserve_order(dirs)


def _dedupe_preserve_order(paths: List[Path]) -> List[Path]:
    seen: set[str] = set()
    out: List[Path] = []
    for p in paths:
        key = str(p.resolve()) if p.exists() else str(p)
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out
