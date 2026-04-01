## Side_A – Lightroom-safe Metadata Tagging Assistant (Google Cloud Vision)

Side_A is a Python project that analyzes photos using the **Google Cloud Vision API** and generates **metadata + keyword suggestions** for Lightroom-compatible workflows.

It will:

- **Analyze each image** with the Vision API.
- **Classify** each image into simple categories:
  - **Outdoor**
  - **Indoor**
  - **Photobooth**
  - **Portrait**
  - **Group**
  - **Other**
- **Write outputs only** (`metadata.csv`, `suggested_keywords.csv`, and an optional future `optional_xmp/` export folder).

### Lightroom compatibility (important)

Lightroom catalogs depend on **stable file paths** for RAW/photo files. If files are moved, renamed, or reorganized on disk, Lightroom can lose references.

**This tool does not move or rename your original files.** It only reads images where they already are and generates metadata/keyword suggestions for Lightroom workflows.

---

## Project structure

- **`app.py`**: Main pipeline (scan folder → Vision → classify → write CSV outputs).
- **`gui.py`**: Desktop GUI (folder selection, progress, lightweight review/edit of suggested keywords).
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
- Ability to set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable on your system.

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

2. **Easiest (automatic):** Place the key file at `keys/vision-key.json` inside the project folder (or next to the `.exe` when packaged). The app will use it automatically if `GOOGLE_APPLICATION_CREDENTIALS` is not set.

3. **Alternative:** Set the `GOOGLE_APPLICATION_CREDENTIALS` environment variable to the full path of your JSON key file.

On **Windows (PowerShell, current session)**:

```powershell
$env:GOOGLE_APPLICATION_CREDENTIALS="C:\path\to\vision-key.json"
```

On **macOS / Linux**:

```bash
export GOOGLE_APPLICATION_CREDENTIALS="/path/to/vision-key.json"
```

### Where the app looks for credentials

1. **`GOOGLE_APPLICATION_CREDENTIALS`** (if already set)  
   - Uses the path from the environment variable.

2. **`keys/vision-key.json`** (automatic fallback)  
   - Relative to the project folder when running as a script, or next to the `.exe` when packaged.  
   - No environment variable needed.

3. **User credentials from `gcloud auth application-default login`**  
   - Stored in `%APPDATA%\gcloud\application_default_credentials.json` (Windows) or `$HOME/.config/gcloud/` (Linux/macOS).

4. **Attached service account** (when running on Google Cloud).

If none are found, the app shows a clear error with the expected path.

---

## 3. Choose a folder of photos (no file moving)

The app scans a folder you select and **never alters the originals**.

Supported extensions (case-insensitive):

- Images: `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif`, `.tiff`, `.gif`
- RAW (best-effort scanning): `.dng`, `.cr2`, `.cr3`, `.nef`, `.arw`, `.raf`, `.rw2`, `.orf`, `.srw`

---

## 4. Run the program

From the project root (with the virtual environment activated and `GOOGLE_APPLICATION_CREDENTIALS` set):

```bash
python app.py
```

The program will:

- Read supported files from `input_images/` (recursive).
- Analyze each image with Vision (labels, faces, OCR text).
- Classify into Outdoor/Indoor/Photobooth/Portrait/Group/Other.
- Generate outputs in `side_a_outputs/`:
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

1. Click **Browse** and choose the folder with your photos/RAW files.
2. Click **Start Processing**.
3. When done, open the results folder and optionally **Review & Edit Suggested Keywords**.

Outputs are written to `SideA_Metadata/` inside the selected folder.

Credentials are auto-detected from `keys/vision-key.json` if present (see section 2).

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
   pyinstaller --onefile --windowed --name SideA_PhotoOrganizer --hidden-import=app --hidden-import=classifier --hidden-import=metadata --hidden-import=organizer --hidden-import=vision_client --hidden-import=customtkinter --hidden-import=google.cloud.vision --hidden-import=google.cloud.vision_v1 --hidden-import=google.auth gui.py
   ```

3. The `.exe` will be in the `dist/` folder: `dist\SideA_PhotoOrganizer.exe`.

**Important for end users:** The `.exe` still needs `GOOGLE_APPLICATION_CREDENTIALS` set to the path of the service account JSON key. They can set it in System Properties → Environment Variables, or run from a batch file:

```batch
set GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\your\vision-key.json
SideA_PhotoOrganizer.exe
```

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

Written to the output folder (GUI: `SideA_Metadata/`, CLI: `side_a_outputs/`). One row per processed image.

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

