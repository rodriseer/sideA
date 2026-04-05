## Photo Metadata Assistant — Lightroom-safe metadata tool (Google Cloud Vision)

The **product name**, **output folder name**, **per-user config slug**, and all user-facing strings are defined in **`branding.py`** (defaults are generic so the app reads as a standalone photography utility). The project uses the **Google Cloud Vision API** and generates **metadata, keyword suggestions, and XMP sidecars** for Lightroom-compatible workflows.

It will:

- **Analyze each image** with the Vision API.
- **Classify** each image into simple categories:
  - **Outdoor**
  - **Indoor**
  - **Photobooth**
  - **Portrait**
  - **Group**
  - **Other**
- **Write outputs only** (`metadata.csv`, `suggested_keywords.csv`, XMP sidecars next to originals, logs under the output folder).

### Lightroom compatibility (important)

Lightroom catalogs depend on **stable file paths** for RAW/photo files. If files are moved, renamed, or reorganized on disk, Lightroom can lose references.

**This tool does not move, rename, or alter your original image files.** It reads images in place and generates metadata, keyword suggestions, and optional XMP sidecars for Lightroom-compatible workflows.

---

## Project structure

- **`branding.py`**: **Central branding** — `APP_NAME`, `WINDOW_TITLE`, `OUTPUTS_SUBFOLDER`, `APP_CONFIG_SLUG` (user settings folder), pipeline/UI copy, and About text.
- **`brand.py`**: Thin compatibility shim (re-exports `branding` + legacy names like `OUTPUT_FOLDER_NAME`).
- **`user_settings.py`**: Loads/saves **`config.json`** in the OS user data folder (path to the Google **service account JSON**). PyInstaller-safe; migrates legacy `settings.json` if present.
- **`app.py`**: Main pipeline (scan folder → Vision → classify → write CSV outputs).
- **`gui.py`**: Desktop GUI (Setup Guide onboarding, folder selection, progress, review/edit keywords + XMP sync).
- **`vision_client.py`**: Wraps Google Cloud Vision API calls.
- **`classifier.py`**: Rule-based logic for Outdoor, Indoor, Photobooth, Portrait, Group, Other.
- **`organizer.py`**: Output manager (Lightroom-safe: creates output folders only, no file operations on originals).
- **`metadata.py`**: CSV writers for `metadata.csv` and `suggested_keywords.csv`.
- **`requirements.txt`**: Python dependencies.
- **`README.md`**: This documentation.
- **`input_images/`**: Optional default input folder for CLI mode (you can also pick any folder in the GUI).
- **`background.png`** (optional): Background image for the GUI. Falls back to dark theme if missing.

---

## Prerequisites

- **Python**: 3.9 or newer is recommended.
- **Google Cloud account** with:
  - A project created.
  - **Vision API enabled**.
  - A **service account key** (JSON file) with permission to use the Vision API.
- **Recommended:** use the GUI **Setup Guide** (step-by-step) to create credentials in Google Cloud, choose the service account JSON, and tap **Test Connection**; the path is stored in `config.json` and applied automatically (no environment variables required for typical users).

---

## 1. Install dependencies

From the project root (`Side_A` folder):

```bash
python -m venv .venv
```

On **Windows (PowerShell)**:

```bash
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

On **macOS / Linux**:

```bash
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 2. Configure Google Cloud Vision credentials

1. In the Google Cloud Console:
   - Create or select a project.
   - Enable **Vision API**.
   - Create a **service account** and download its **JSON key file**.

2. **GUI (recommended):** Run `python gui.py` → **Setup Guide** → follow the steps → **Select Credentials File (.json)** → **Test Connection** (this saves the path). The path is stored under your user profile (see the hint in the guide).

3. **CLI / scripts:** On each run the app calls `apply_saved_credentials_to_environment()` so the same **`config.json`** path is used. If nothing is saved yet, a valid **`GOOGLE_APPLICATION_CREDENTIALS`** environment variable or optional **`keys/vision-key.json`** next to the project or `.exe` still works for developers.

### Where the app looks for credentials (order of use)

1. **Path saved in `config.json`** (from Setup Guide / **Test Connection**) — if the file still exists, it is applied as `GOOGLE_APPLICATION_CREDENTIALS` for that run.

2. **`GOOGLE_APPLICATION_CREDENTIALS`** (if already set and the file exists) — useful for CI or advanced setups.

3. **`keys/vision-key.json`** — optional fallback beside the repo or packaged `.exe`.

4. Other **Application Default Credentials** (e.g. `gcloud auth application-default login`) if no service-account file is found.

If none are valid, the GUI asks you to connect your Google Vision credentials file; the CLI prints a short error.

---

## 3. Choose a folder of photos (no file moving)

The app scans a folder you select and **never alters the originals**.

Supported extensions (case-insensitive):

- Images: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif`, `.tiff`, `.gif`
- RAW (best-effort scanning): `.dng`, `.cr2`, `.cr3`, `.nef`, `.arw`, `.raf`, `.rw2`, `.orf`, `.srw`

---

## 4. Run the program

From the project root (with the virtual environment activated and Vision credentials configured as in section 2):

```bash
python app.py
```

The program will:

- Read supported files from `input_images/` (recursive).
- Analyze each image with Vision (labels, faces, OCR text).
- Classify into Outdoor/Indoor/Photobooth/Portrait/Group/Other.
- Generate outputs in `PhotoMetadata_Output/` (change `OUTPUTS_SUBFOLDER` in `branding.py`):
  - `metadata.csv`
  - `suggested_keywords.csv`
  - `optional_xmp/` (placeholder folder for future XMP sidecar export)

---

## Lightroom Classic XMP sidecar test (RAW-first)

JPEG/TIFF validation is not reliable for Lightroom Classic because Lightroom often writes metadata directly into those formats. For **proprietary RAW files**, Lightroom Classic commonly uses **XMP sidecars**.

### Generate XMP sidecars next to RAW files

From the project root:

```bash
python app.py --mode test-xmp-raw --input "C:\path\to\your\raw_folder"
```

This will, for each RAW file (`.cr2`, `.cr3`, `.nef`, `.arw`, `.orf`, `.rw2`, `.raf`, `.dng`):

- Create `IMG_1234.xmp` next to `IMG_1234.CR2` (same basename, same folder)
- Print:
  - RAW filename
  - generated XMP path
  - keywords written
- Validate:
  - `IMG_1234.xmp` exists
  - `dc:subject` contains the generated keywords

### Lightroom Classic verification steps

1. Import the RAW files into Lightroom Classic.
2. Generate XMP sidecars with the command above.
3. In Lightroom Classic, select the RAW photo.
4. Use **Metadata > Read Metadata from File**.
5. Check **Keyword Tags** (and hierarchical keywords if enabled).

---

## 5. Desktop GUI (recommended for photographers)

A simple Windows desktop app lets you choose a folder and generate Lightroom-safe metadata outputs.

### Run the GUI

```bash
python gui.py
```

1. Complete **Setup Guide** once (service account JSON), if prompted.
2. Click **Browse** and choose the folder with your photos/RAW files.
3. Click **Start analysis**.
4. When done, open the results folder and optionally **Review & edit keywords**.

Outputs are written to `PhotoMetadata_Output/` inside the selected folder (set `OUTPUTS_SUBFOLDER` in `branding.py`).

---

## 6. Build a single .exe (PyInstaller)

To create a standalone Windows executable so others can run the app without installing Python:

1. Install dependencies (including PyInstaller):

   ```bash
   pip install -r requirements.txt
   ```

2. Build the executable:

   ```bash
   pyinstaller SideA.spec
   ```

   Or use the one-line command:

   ```bash
   pyinstaller --onefile --windowed --name PhotoMetadataAssistant --hidden-import=app --hidden-import=classifier --hidden-import=metadata --hidden-import=organizer --hidden-import=vision_client --hidden-import=customtkinter --hidden-import=google.cloud.vision --hidden-import=google.cloud.vision_v1 --hidden-import=google.auth gui.py
   ```

3. The `.exe` will be in the `dist/` folder: `dist\PhotoMetadataAssistant.exe`.

**Important for end users:** After launching the `.exe`, open **Setup Guide** from the main window or **Settings → Setup Guide…**, follow the steps, choose the JSON file, and tap **Test Connection** to save. No environment variables are required. Developers may still use `GOOGLE_APPLICATION_CREDENTIALS` or `keys/vision-key.json` if they prefer.

---

## 7. Classification rules (high-level)

The classifier maps Vision labels to Lightroom-friendly categories:

- **Photobooth** – explicit “photo booth” OCR/labels
- **Group** – 3+ faces or group/crowd indicators
- **Portrait** – 1–2 faces and portrait indicators
- **Outdoor** – outdoor/nature indicators
- **Indoor** – indoor/interior indicators
- **Other** – fallback when no clear match

Edit `classifier.py` to adjust the rules.

---

## 8. Output CSV formats

### `metadata.csv`

Written to the output folder (default: `PhotoMetadata_Output/` next to your photos, or the CLI `--output` path). One row per processed image.

Columns:

- **`filename`**: Base filename of the image.
- **`original_path`**: Absolute path to the image on disk (never changed).
- **`category`**: One of Outdoor, Indoor, Photobooth, Portrait, Group, Other.
- **`top_labels`**: Comma-separated list of the top labels from Vision.
- **`face_count`**: Number of faces detected in the image.
- **`confidence_summary`**: Semi-colon separated `label(score)` pairs (score in \[0,1\]).
- **`date_processed`**: UTC timestamp in ISO 8601 format.

---

### `suggested_keywords.csv`

Also written to the output folder. One row per processed image.

Columns:

- **`filename`**
- **`original_path`**
- **`suggested_keywords`**: Comma-separated Lightroom-style keywords.
- **`primary_category`**
- **`notes`**

---

## 9. Customization ideas

- Adjust or expand label keywords for each category in `classifier.py`.
- Tweak suggested keyword composition (see `app.py`).
- Implement optional XMP sidecar export to `optional_xmp/`.

