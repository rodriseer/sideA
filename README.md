## Side_A – Automatic Photo Organization with Google Cloud Vision

Side_A is a Python project that automatically analyzes and organizes photos using the **Google Cloud Vision API**.

It will:

- **Analyze each image** with the Vision API.
- **Classify** each image into photographer-friendly categories:
  - **Events** – celebrations, parties, weddings
  - **Portraits** – single or couple photos
  - **Crowd** – group photos, audiences
  - **Stage** – performances, presentations
  - **Indoor** – interior shots
  - **Night** – nighttime, evening
  - **Formal** – business, corporate
  - **Misc** – everything else
- **Copy** each image into an `Organized` subfolder with category subfolders.

---

## Project structure

- **`app.py`**: Main program that runs the full pipeline (command-line).
- **`gui.py`**: Desktop GUI for photographers (folder selection, progress, one-click processing).
- **`vision_client.py`**: Wraps Google Cloud Vision API calls.
- **`classifier.py`**: Rule-based logic for Events, Portraits, Crowd, Stage, Indoor, Night, Formal, Misc.
- **`organizer.py`**: Copies images into category folders.
- **`metadata.py`**: Optional metadata CSV (enable with `SIDE_A_DEBUG=1` for debugging).
- **`requirements.txt`**: Python dependencies.
- **`README.md`**: This documentation.
- **`input_images/`**: Default input folder for CLI mode.
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

## 3. Add images to `input_images/`

1. Ensure the folder `input_images/` exists in the project root.
   - If it doesn’t, the app will create it when you run it the first time.
2. Copy any photos you want to organize into `input_images/`.
   - Supported extensions (case-insensitive):
     - `.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tif`, `.tiff`, `.gif`

---

## 4. Run the program

From the project root (with the virtual environment activated and `GOOGLE_APPLICATION_CREDENTIALS` set):

```bash
python app.py
```

The program will:

- Read all supported image files from `input_images/`.
- For each image:
  - Call Google Cloud Vision to get:
    - Labels and confidence scores.
    - Face detection results.
    - Text (OCR) if present.
  - Classify the image into Events, Portraits, Crowd, Stage, Indoor, Night, Formal, or Misc.
  - Copy the image into `organized_output/<Category>/`.

---

## 5. Desktop GUI (recommended for photographers)

A simple Windows desktop app lets you choose folders and run processing without using the command line.

### Run the GUI

```bash
python gui.py
```

1. Click **Browse...** next to "Select Photos Folder" and choose the folder with your photos.
2. Click **Start Processing**.
3. Watch the progress bar and status messages.
4. When done, view the summary (total processed, folders created, images per category).
5. Click **Open Organized Folder** to open the results (photos are in `Organized/` inside your selected folder).

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

The classifier maps Vision labels to photographer-friendly categories:

- **Crowd** – 3+ faces, or labels like crowd, group, people, audience
- **Portraits** – 1–2 faces with person/face labels
- **Stage** – stage, performance, theater, presentation
- **Events** – event, celebration, party, wedding, concert
- **Night** – night, nightlife, dark, evening
- **Formal** – suit, formal, business, corporate
- **Indoor** – indoor, room, furniture, ceiling, floor, wall
- **Misc** – fallback when no clear match

Edit `classifier.py` to adjust the rules.

---

## 8. `metadata.csv` format

The file `organized_output/metadata.csv` is created (with a header) if it does not exist and one row is appended per processed image.

Columns:

- **`filename`**: Base filename of the image.
- **`original_path`**: Absolute path to the image in `input_images/`.
- **`new_path`**: Absolute path to the copied image inside `organized_output/<Category>/`.
- **`category`**: One of Events, Portraits, Crowd, Stage, Indoor, Night, Formal, Misc.
- **`top_labels`**: Comma-separated list of the top labels from Vision.
- **`face_count`**: Number of faces detected in the image.
- **`confidence_summary`**: Semi-colon separated `label(score)` pairs (score in \[0,1\]).
- **`date_processed`**: UTC timestamp in ISO 8601 format.

---

## 9. Customization ideas

- Adjust or expand label keywords for each category in `classifier.py`.
- Change the number of top labels used in the summary.
- Add more Vision features (e.g., safe-search, landmarks) if needed.
- Integrate with a GUI or web frontend.

