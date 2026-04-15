"""
Design tokens for Photo Metadata Assistant.

Single source of truth for colors, typography, spacing, and radii.
All GUI modules import from here so the visual identity can be changed
by editing this file alone.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass


# =============================================================================
# Brand
# =============================================================================

BRAND_NAME = "Photo Metadata Assistant"
BRAND_TAGLINE = "Lightroom-safe keywords, in minutes."

# The logo mark (aperture) is generated into logo.png at build time and also
# shipped with the .exe. See tools/make_logo.py.
LOGO_FILENAME = "logo.png"


# =============================================================================
# Color palette — warm amber on deep slate. Designed for dark UIs.
# Each token is (light_mode, dark_mode) so CustomTkinter can switch; we ship
# dark-first but leave both in case the user changes appearance mode.
# =============================================================================

# Canvas / window
BG_CANVAS        = ("#F8FAFC", "#0B1220")  # window background
BG_SURFACE       = ("#FFFFFF", "#111827")  # primary cards
BG_SURFACE_2     = ("#F1F5F9", "#1F2937")  # nested cards, input wells
BG_SURFACE_MUTED = ("#E2E8F0", "#0F172A")  # subtle dividers/rows

# Borders
BORDER_SUBTLE = ("#E2E8F0", "#1F2937")
BORDER_STRONG = ("#CBD5E1", "#374151")

# Text
TEXT_PRIMARY   = ("#0F172A", "#F1F5F9")
TEXT_SECONDARY = ("#334155", "#CBD5E1")
TEXT_MUTED     = ("#64748B", "#94A3B8")
TEXT_SUBTLE    = ("#94A3B8", "#64748B")

# Brand / accent — amber evokes warm photographic light.
ACCENT          = ("#D97706", "#F59E0B")  # amber-600 / amber-500
ACCENT_HOVER    = ("#B45309", "#D97706")
ACCENT_SUBTLE   = ("#FEF3C7", "#78350F")
ACCENT_FG       = ("#FFFFFF", "#0B1220")  # text color to place ON accent fill

# Supporting semantic colors
SUCCESS         = ("#059669", "#10B981")
SUCCESS_HOVER   = ("#047857", "#059669")
SUCCESS_SUBTLE  = ("#D1FAE5", "#064E3B")

DANGER          = ("#DC2626", "#EF4444")
DANGER_SUBTLE   = ("#FEE2E2", "#7F1D1D")

WARNING         = ("#D97706", "#F59E0B")
WARNING_SUBTLE  = ("#FEF3C7", "#78350F")

INFO            = ("#2563EB", "#60A5FA")
INFO_SUBTLE     = ("#DBEAFE", "#1E3A8A")

# Neutral button (secondary actions)
NEUTRAL         = ("#E2E8F0", "#334155")
NEUTRAL_HOVER   = ("#CBD5E1", "#475569")


# =============================================================================
# Typography
# =============================================================================

def _default_family() -> str:
    """Pick a clean system sans-serif; fall back if unavailable."""
    if sys.platform.startswith("win"):
        return "Segoe UI"
    if sys.platform == "darwin":
        return "SF Pro Text"
    return "Inter"


FONT_FAMILY      = _default_family()
FONT_FAMILY_MONO = "Consolas" if sys.platform.startswith("win") else "Menlo"


@dataclass(frozen=True)
class FontSpec:
    size: int
    weight: str = "normal"  # "normal" | "bold"


# Type scale — used consistently across the app.
FONT_DISPLAY   = FontSpec(30, "bold")   # hero / app name on splash
FONT_HEADING   = FontSpec(22, "bold")   # dialog titles, card titles
FONT_SUBHEAD   = FontSpec(17, "bold")   # section headers
FONT_BODY      = FontSpec(14)           # default body
FONT_BODY_BOLD = FontSpec(14, "bold")
FONT_SMALL     = FontSpec(12)
FONT_TINY      = FontSpec(11)
FONT_BUTTON    = FontSpec(15, "bold")
FONT_BUTTON_SM = FontSpec(13, "bold")


# =============================================================================
# Spacing & radii (keep a consistent rhythm across layouts)
# =============================================================================

SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 14
SPACE_LG = 22
SPACE_XL = 32

RADIUS_SM = 6
RADIUS_MD = 10
RADIUS_LG = 14
RADIUS_XL = 20

# Fixed sizes
BUTTON_HEIGHT     = 44
BUTTON_HEIGHT_LG  = 54
BUTTON_HEIGHT_SM  = 34
INPUT_HEIGHT      = 42

WINDOW_DEFAULT_W  = 780
WINDOW_DEFAULT_H  = 780
WINDOW_MIN_W      = 640
WINDOW_MIN_H      = 640


# =============================================================================
# Helpers
# =============================================================================

def font(spec: FontSpec, family: str | None = None):
    """Build a CustomTkinter CTkFont from a FontSpec. Imported lazily to avoid
    pulling tkinter in at module load time."""
    import customtkinter as ctk
    return ctk.CTkFont(family=family or FONT_FAMILY, size=spec.size, weight=spec.weight)
