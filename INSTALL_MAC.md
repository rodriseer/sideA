# Installing on macOS

There are two ways to run Photo Metadata Assistant on a Mac.

---

## Option A — Download the app (easiest)

1. Go to **https://github.com/rodriseer/sideA/releases**
2. Under the latest release, download **PhotoMetadataAssistant-macOS.zip**
3. Double-click the zip to unpack it — you'll get **PhotoMetadataAssistant.app**
4. Drag it to your **Applications** folder
5. **First launch only:** right-click the app → **Open** → click **Open** in the dialog  
   (macOS blocks apps not from the App Store by default — this one-time step bypasses that)

That's it. Open the app and follow the Setup Guide to connect Google Vision.

---

## Option B — Run with Python (if Option A isn't available yet)

If there is no release posted yet, you can run the app directly with Python in about two minutes.

### 1. Install Python

Download from **https://www.python.org/downloads/mac-osx/** and run the installer.  
Choose the latest **3.12** or **3.11** version.

### 2. Download the project

- Go to **https://github.com/rodriseer/sideA**
- Click the green **Code** button → **Download ZIP**
- Unzip it — you'll get a folder called **Side_A** (or similar)

### 3. Open Terminal

Press **Command + Space**, type **Terminal**, press Enter.

### 4. Go to the project folder

Drag the **Side_A** folder onto the Terminal window after typing `cd ` (with a space):

```
cd 
```

Then press Enter. (Or type the path manually, e.g. `cd ~/Downloads/Side_A`)

### 5. Install dependencies

```
pip3 install -r requirements.txt
```

Wait for it to finish — it downloads a few libraries. You only need to do this once.

### 6. Launch the app

```
python3 gui.py
```

The app opens. Follow the Setup Guide to connect Google Vision, then you're ready to analyze photos.

---

## Every time after that

Just open Terminal, go to the folder, and run:

```
python3 gui.py
```

---

## Troubleshooting

**"python3 not found"** — Make sure you installed Python from python.org (not the Apple built-in). Close and reopen Terminal after installing.

**"pip3 not found"** — Try `python3 -m pip install -r requirements.txt` instead.

**App opens but shows "Not connected"** — That's normal on first launch. Open the Setup Guide and complete the Google Vision steps (see QUICKSTART.md).

**macOS blocks the .app** — Right-click → Open, then click Open in the dialog. You only need to do this once.
