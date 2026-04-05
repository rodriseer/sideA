"""
Backward compatibility for imports of `brand`.

Prefer: `import branding` for new code. Customize distribution in `branding.py`.
"""

from branding import *  # noqa: F401,F403

PRODUCT_NAME = APP_NAME
OUTPUT_FOLDER_NAME = OUTPUTS_SUBFOLDER
APP_DISPLAY_NAME = APP_NAME
UI_SUBTITLE = APP_DESCRIPTION
SAFETY_HEADLINE = APP_SAFETY_NOTE
TRUST_FOOTNOTE = APP_TRUST_NOTE
