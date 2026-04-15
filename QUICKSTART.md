# Photo Metadata Assistant — Quick Start

Welcome! This short guide walks you through analyzing your first folder of photos. No coding, no command line — just three short steps the first time, then one step for every shoot after that.

---

## Before you begin

You will need:

1. A Windows PC (or Mac) to run the app.
2. A folder of photos or RAW files you want to analyze.
3. A free Google account (Gmail works).
4. About 10 minutes for the one-time Google setup.

> Your original photo and RAW files are never moved, renamed, or changed. The app only reads them and writes new files (CSV reports and optional XMP sidecars) to a separate output folder.

---

## Step 1 — Install and open the app

1. Double-click **PhotoMetadataAssistant.exe**.
2. On first launch Windows may show a blue "Windows protected your PC" screen. Click **More info → Run anyway**.
3. A welcome window will appear asking you to connect Google Vision.

That's it — there is nothing to install beyond the single .exe.

---

## Step 2 — Connect Google Vision (one-time)

Google Vision is the service that actually looks at your images and suggests keywords. It's free for the first 1,000 images per month.

The app has a built-in **Setup Guide** that walks you through it. Here is the big picture so you know what to expect:

1. **Open the Setup Guide** — click the big amber button in the welcome window, or go to **Settings → Setup Guide…**
2. **Open Google Cloud** — the guide has a link that takes you to the right page.
3. **Create a project** — any name is fine ("Photo Keywords", "Studio", whatever). Click Create.
4. **Turn on the Vision API** — in the search bar inside Google Cloud, type "Vision API" and click **Enable**.
5. **Create a service account** — go to *Credentials → Create credentials → Service account*. Any name is fine.
6. **Download the key file** — on the service account page, click *Keys → Add Key → Create new key → JSON*. Your browser downloads a small `.json` file. Save it somewhere you'll remember (Documents is fine).
7. **Come back to the app** — click **Select Credentials File (.json)** and pick the file you just downloaded.
8. **Click Test Connection** — if it says "Connection works. You're all set." you are done with setup forever on this computer.

### Keep the .json file safe

That little JSON file is like a password for your Google account's Vision usage. Don't email it, don't post it online, don't upload it to shared drives. Keep it on your computer.

---

## Step 3 — Analyze a folder

This is the part you'll do every time.

1. In the main window, click **Browse…** next to the folder field.
2. Pick the folder that contains your photos or RAW files. Sub-folders are included automatically.
3. Click **Start analysis**.

You'll see each image appear as it is being analyzed, along with:

- a thumbnail of the current image
- the detected category (Outdoor, Indoor, Portrait, Group, Photobooth, Other)
- a progress bar showing "image 47 of 312"

When it finishes you'll get:

- **Open results folder** — opens the new `PhotoMetadata_Output` folder created next to your photos. Inside you'll find `metadata.csv` and `suggested_keywords.csv`.
- **Review & edit keywords** — opens a small editor where you can tweak the keywords for each image before saving them into Lightroom-compatible XMP sidecars.

Your original photos stay exactly where they were, untouched.

---

## Step 4 — Use the keywords in Lightroom

1. Import your RAW or JPEG folder into Lightroom Classic the way you normally would.
2. In Lightroom, select the photos you want to pick up the new keywords.
3. Go to **Metadata → Read Metadata from File**.
4. Open the **Keyword Tags** panel — the suggested keywords should now be attached to each image.

If Lightroom does not see the keywords, make sure:

- You ran **Review & edit keywords → Save CSV + sync XMP** in the app, and
- The `.xmp` sidecar file is sitting next to the RAW file (same name, different extension).

---

## Troubleshooting

**"Not connected" stays red after choosing the JSON file.**
Check the file you picked is the same one Google downloaded (it ends in `.json` and contains lines like `"type": "service_account"`). If in doubt, create a new key in Google Cloud and try again.

**The Start button is greyed out.**
You need to finish the Setup Guide once. Open Settings → Setup Guide… and complete the Test Connection step.

**The progress bar freezes.**
Check your internet connection — Google Vision needs to be reachable. Very large RAW files can take several seconds each, which is normal.

**I want to use a different Google account.**
Open **Settings → Setup Guide…**, pick a new JSON file, and hit Test Connection. The app always uses the most recently saved credentials.

**I see "quota exceeded" in the activity log.**
Google's free Vision tier is 1,000 images per calendar month. Either wait until next month or enable billing on your Google Cloud project.

---

## What the app creates

After a run, inside `PhotoMetadata_Output/` next to your photos you'll find:

- **`metadata.csv`** — one row per image with filename, category, top labels, face count, confidence, and a timestamp.
- **`suggested_keywords.csv`** — one row per image with a keyword list ready for Lightroom.
- **`optional_xmp/`** — placeholder folder for future exports.
- **Log files** — so you (or support) can see what happened if anything looks wrong.

And beside each RAW file (when you click **Save CSV + sync XMP** in the review window):

- **`YOUR_FILE.xmp`** — a small text file Lightroom reads for keywords and category, without ever touching the RAW itself.

---

Questions or trouble? Tap **Help → About** in the app for version info, and keep your service-account JSON file handy — it's the only thing this tool needs to keep working across photo sessions.
