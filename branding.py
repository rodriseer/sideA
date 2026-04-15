"""
User-facing brand strings and product copy — single customization surface.

Defaults describe a generic photography metadata tool (no client-specific naming).
For a white-label or custom build, edit this file only: APP_NAME, OUTPUTS_SUBFOLDER,
APP_CONFIG_SLUG, and any copy below.
"""

# =============================================================================
# Identity — change these for your distribution
# =============================================================================

APP_NAME = "Photo Metadata Assistant"
WINDOW_TITLE = APP_NAME
OUTPUTS_SUBFOLDER = "PhotoMetadata_Output"
APP_CONFIG_SLUG = "PhotoMetadataAssistant"

# =============================================================================
# Product copy
# =============================================================================

APP_SUBTITLE = "Lightroom-safe metadata + keyword suggestions"
APP_SAFETY_NOTE = (
    "This tool does not move, rename, or alter your original image files. "
    "Optional XMP sidecars may be created for Lightroom-compatible metadata."
)
APP_SAFETY_BADGE = "Lightroom-safe · originals never moved"

APP_DESCRIPTION = (
    "Generate keywords and XMP sidecars for Lightroom - your originals stay in place; "
    "new files are reports, optional sidecars, and other outputs listed when a run finishes."
)
APP_TRUST_NOTE = (
    "Uses Google Cloud Vision for image analysis. Your Google service account credentials "
    "file stays on this computer; it is only used to sign in to Google's servers."
)

# Pipeline / completion (CLI + GUI status)
MSG_PIPELINE_ANALYZING = (
    "Analyzing folder. Your original image files are not moved, renamed, or altered. "
    "Optional XMP sidecars may be created for Lightroom-compatible metadata."
)
MSG_PIPELINE_COMPLETE_ORIGINALS = (
    "Your original image files were not moved, renamed, or altered."
)
MSG_PIPELINE_COMPLETE_OUTPUTS = (
    "Outputs were written (CSV, logs, and any XMP sidecars beside originals - see paths above). "
    "Temporary preview JPEGs used for analysis are removed after each image unless you enabled keeping them."
)

RUN_SUMMARY_HEADER = "Photo metadata - run summary"

SUMMARY_OUTPUTS_NOTE = (
    "Original photos and RAW files are unchanged. The output paths above may be new or updated "
    "(including XMP sidecars next to originals, CSV reports, logs, and temporary previews folder)."
)

# --- New three-card main screen ----------------------------------------------
CARD_CREDENTIALS_TITLE = "1. Connect Google Vision"
CARD_CREDENTIALS_BODY = (
    "One-time setup. Open the Setup Guide, follow the short steps, and pick the "
    "service-account JSON you download from Google Cloud. Your file stays on this "
    "computer."
)
CARD_CREDENTIALS_BODY_CONNECTED = (
    "You're connected. You can re-open the Setup Guide anytime from Settings to "
    "change the credentials file."
)

CARD_FOLDER_TITLE = "2. Choose your photos"
CARD_FOLDER_BODY = (
    "Pick the folder containing your photos or RAW files. The app scans it in place - "
    "no files are moved or renamed."
)

CARD_RUN_TITLE = "3. Analyze"
CARD_RUN_BODY = (
    "Google Vision reads each image and proposes keywords and a category. Outputs "
    "(CSV reports, optional XMP sidecars) are written to a new PhotoMetadata_Output "
    "folder next to your photos."
)

# Button / status microcopy
BTN_WORKING = "Working..."
MSG_STARTING = "Starting..."
MSG_COMPLETE = "Complete"
MSG_ERROR = "Stopped with an error"

# --- Common UI strings --------------------------------------------------------
PLACEHOLDER_PHOTOS_FOLDER = "Select the folder that contains your photos or RAW files..."

BTN_BROWSE_FOLDER = "Browse..."
BTN_START_ANALYSIS = "Start analysis"
BTN_OPEN_RESULTS = "Open results folder"
BTN_REVIEW_KEYWORDS = "Review & edit keywords"
BTN_REVIEW_SAVE = "Save CSV + sync XMP"

REVIEW_INTRO_XMP = (
    "Edit keywords, then save. Matching XMP sidecars next to your originals may be updated; "
    "rows without a sidecar are skipped. Your original image files are not moved, renamed, or altered."
)
REVIEW_SAVE_SUCCESS = (
    "Save complete.\n\n"
    "- CSV updated: {csv_basename}\n"
    "- XMP sidecars updated: {xmp_updated}\n"
    "- Skipped for XMP sync: {xmp_skipped}\n"
    "(No .xmp beside that file, blank path, or file could not be written - originals are never changed.)"
)
BTN_SETUP_VISION = "Google Vision Setup..."
BTN_SETUP_GUIDE = "Open Setup Guide"
MENU_SETTINGS = "Settings"
MENU_SETTINGS_CREDENTIALS = "Setup Guide..."
BTN_SELECT_CREDENTIALS_JSON = "Select Credentials File (.json)"
BTN_CREDENTIALS_TEST = "Test connection"
BTN_TEST_CONNECTION = "Test Connection"
BTN_CREDENTIALS_SAVE = "Save"

MSG_VISION_CREDENTIALS_REQUIRED = "Please connect your Google Vision credentials file"

CREDENTIALS_MISSING_GUI = (
    f"{MSG_VISION_CREDENTIALS_REQUIRED}\n\n"
    "Open Setup Guide and follow the steps, or use \"Select Credentials File (.json)\" if you already have the file."
)

CREDENTIALS_CLI_HINT = (
    "In the desktop app, open Settings -> Setup Guide and choose your service account .json file."
)

LABEL_STATUS = "Activity log"
LABEL_VISION_SETUP = "Google Vision Setup"

CREDENTIALS_STATUS_CONFIGURED = "Connected"
CREDENTIALS_STATUS_NOT_CONFIGURED = "Not connected"

FIRST_RUN_TITLE = "Welcome - quick setup"
FIRST_RUN_BODY = (
    "Before you can analyze photos, we'll help you connect Google Vision once.\n\n"
    "It's a short walkthrough - no tech background needed.\n\n"
    "Tap Setup Guide below, or open Settings -> Setup Guide anytime."
)
FIRST_RUN_BTN_SETUP = "Open Setup Guide"
FIRST_RUN_BTN_LATER = "Not now"

# --- Setup Guide (onboarding) -------------------------------------------------
SETUP_GUIDE_TITLE = "Connect Google Vision"
SETUP_GUIDE_SUBTITLE = "A few simple steps - only needed once."
SETUP_GUIDE_CLOUD_URL = "https://console.cloud.google.com/"
SETUP_GUIDE_LINK_TEXT = "Open Google Cloud"
SETUP_GUIDE_STEP_1 = "Go to Google Cloud in your browser (use the link below)."
SETUP_GUIDE_STEP_2 = "Sign in with your Google account. Create a new project - any name is fine."
SETUP_GUIDE_STEP_3 = "Turn on the Vision feature for that project."
SETUP_GUIDE_STEP_4 = "Create new credentials and pick \"Service account.\""
SETUP_GUIDE_STEP_5 = "Create a key, choose JSON, and download the file to your computer."
SETUP_GUIDE_STEP_6 = "Tap the big button below and choose that file in this app."
SETUP_GUIDE_PRIVACY_WARNING = (
    "Keep this file private. It gives access to your Google account usage."
)
SETUP_GUIDE_PATH_HINT = "No file chosen yet"
SETUP_GUIDE_TEST_TO_FINISH = "Tap \"Test Connection\" to save and finish."

# --- Google Vision Setup dialog ----------------------------------------------
CREDENTIALS_DIALOG_TITLE = "Google Vision Setup"
CREDENTIALS_FILE_LABEL = "Service account credentials (.json)"
CREDENTIALS_FILE_DIALOG_TITLE = "Select your Google Cloud service account JSON file"
CREDENTIALS_HELP_NOTE = (
    "Google Cloud gives you a JSON file for a \"service account.\" That is what this app "
    "uses - not a browser API key. The file stays on your computer."
)
CREDENTIALS_INTRO = (
    "Quick steps:\n\n"
    "1. In Google Cloud Console, open your project, enable the Vision API, and create a service account.\n"
    "2. Create a key for that account and download the JSON file.\n"
    "3. Click \"Select Credentials File (.json)\" below and pick that file.\n"
    "4. Click Test connection, then Save.\n\n"
    "Your file path is stored only on this computer (see the note at the bottom)."
)

CREDENTIALS_SUCCESS = "Connection works. You're all set."
CREDENTIALS_FAILURE = "That didn't work. Check the file and that Vision API is enabled for your Google project."
CREDENTIALS_SAVE_SUCCESS = "Your credentials file is saved. This app will use it automatically next time."
CREDENTIALS_ERROR_NO_FILE = "Please choose your Google service account JSON file first."
CREDENTIALS_CONFIG_HINT = "Where your settings are saved on this computer:"
CREDENTIALS_TESTING = "Checking connection..."

MENU_HELP_ABOUT = "About"
ABOUT_BLURB = (
    "A lightweight tool for photographers: keywords and XMP sidecars for Lightroom, "
    "without moving or breaking file references to your originals."
)
