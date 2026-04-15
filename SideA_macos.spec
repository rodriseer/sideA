# -*- mode: python ; coding: utf-8 -*-
# macOS: builds dist/PhotoMetadataAssistant.app (windowed, onedir inside bundle).
# Run on Apple Silicon or Intel Mac with Python + deps installed.
#
#   cd /path/to/Side_A
#   python3 -m venv .venv && source .venv/bin/activate
#   pip install -r requirements.txt
#   pyinstaller --clean --noconfirm SideA_macos.spec
#
# Icon (optional): place AppIcon.icns in assets/ (create assets/ if needed).

import os

block_cipher = None

_spec_dir = os.path.dirname(os.path.abspath(SPEC))

# Brand resources. Background image removed in the redesign — only the logo
# is shipped now (both master and @128 for HiDPI).
_datas = []
for _name in ("logo.png", "logo_128.png"):
    _p = os.path.join(_spec_dir, _name)
    if os.path.isfile(_p):
        _datas.append((_p, "."))

# CustomTkinter / Pillow bundled assets (themes, fonts)
try:
    from PyInstaller.utils.hooks import collect_data_files

    _datas += collect_data_files("customtkinter")
    _datas += collect_data_files("PIL")
except Exception:
    pass

# Optional app icon (macOS .icns)
_icon = os.path.join(_spec_dir, "assets", "AppIcon.icns")
ICON = _icon if os.path.isfile(_icon) else None

a = Analysis(
    [os.path.join(_spec_dir, "gui.py")],
    pathex=[_spec_dir],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        "app",
        "branding",
        "brand",
        "bundle_paths",
        "theme",
        "user_settings",
        "classifier",
        "metadata",
        "organizer",
        "vision_client",
        "customtkinter",
        "PIL",
        "PIL.Image",
        "PIL.ImageTk",
        "google.cloud.vision",
        "google.cloud.vision_v1",
        "google.cloud.vision_v1.types",
        "google.auth",
        "google.auth.transport.requests",
        "google.oauth2",
        "grpc",
        "numpy",
        "rawpy",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="PhotoMetadataAssistant",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=True,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PhotoMetadataAssistant",
)

app = BUNDLE(
    coll,
    name="PhotoMetadataAssistant.app",
    icon=ICON,
    bundle_identifier="com.photometadata.assistant",
    version="1.0.0",
    info_plist={
        "NSHighResolutionCapable": True,
        "CFBundleName": "Photo Metadata Assistant",
        "CFBundleDisplayName": "Photo Metadata Assistant",
        "NSHumanReadableCopyright": "Copyright © Photo Metadata Assistant",
    },
)
