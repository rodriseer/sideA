"""
Generate the app logo (aperture mark) and write it to logo.png at the project
root. Run this whenever the brand changes:

    python tools/make_logo.py

The logo is a flat aperture with 6 blades over a rounded-square amber tile.
Pure PIL, no external assets.
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


SIZE = 512               # master size; PyInstaller ships this file
BG    = (245, 158, 11)   # amber-500
BG_2  = (217, 119, 6)    # amber-600 (for soft radial edge)
BLADE = (15, 23, 42)     # slate-900 — the aperture blades
HOLE  = (245, 158, 11)   # center hole matches background → feels "open"


def rounded_square(size: int, radius_ratio: float = 0.22) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    r = int(size * radius_ratio)
    d.rounded_rectangle((0, 0, size - 1, size - 1), radius=r, fill=BG)
    # subtle inner vignette for depth
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    inset = int(size * 0.05)
    od.rounded_rectangle(
        (inset, inset, size - inset, size - inset),
        radius=r - inset, outline=BG_2, width=max(2, size // 80),
    )
    img.alpha_composite(overlay)
    return img


def aperture_blades(size: int, n_blades: int = 6) -> Image.Image:
    """Draw n triangular aperture blades arranged in a circle."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    cx = cy = size / 2
    outer_r = size * 0.36
    inner_r = size * 0.085

    # Each blade is a triangle whose base touches the outer ring and tip points
    # toward but stops short of center, leaving the circular hole.
    for i in range(n_blades):
        a = (2 * math.pi * i) / n_blades - math.pi / 2
        a_next = a + (2 * math.pi) / n_blades

        # Two outer points on the ring, swept by half a sector
        half = (a_next - a) / 2
        p_outer_1 = (cx + outer_r * math.cos(a + half * 0.1),
                     cy + outer_r * math.sin(a + half * 0.1))
        p_outer_2 = (cx + outer_r * math.cos(a_next - half * 0.1),
                     cy + outer_r * math.sin(a_next - half * 0.1))
        # Tip offset from center so the blades swirl rather than meet
        tip_angle = a + half + math.radians(18)
        p_tip = (cx + inner_r * math.cos(tip_angle),
                 cy + inner_r * math.sin(tip_angle))

        d.polygon([p_outer_1, p_outer_2, p_tip], fill=BLADE)

    # Center hole (transparent through to background color)
    d.ellipse(
        (cx - inner_r, cy - inner_r, cx + inner_r, cy + inner_r),
        fill=HOLE,
    )
    return img


def make_logo(size: int = SIZE) -> Image.Image:
    base = rounded_square(size)
    blades = aperture_blades(size)
    base.alpha_composite(blades)
    return base


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    out = root / "logo.png"
    img = make_logo(SIZE)
    img.save(out, "PNG")
    # Also write a small @1x copy used inline in the UI
    small = img.resize((128, 128), Image.Resampling.LANCZOS)
    small.save(root / "logo_128.png", "PNG")
    print(f"wrote {out} and logo_128.png")


if __name__ == "__main__":
    main()
