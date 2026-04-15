# -*- mode: python ; coding: utf-8 -*-
# Windows-focused one-file build (produces PhotoMetadataAssistant.exe).
# For macOS .app bundle, use SideA_macos.spec on a Mac.
# Build: pyinstaller SideA.spec

block_cipher = None

import os

# Resources to ship inside the bundle. The background image has been removed
# from the brand; only the logo is shipped now. Both sizes are included so the
# UI can pick a crisp source for HiDPI.
_datas = []
for _name in ("logo.png", "logo_128.png"):
    if os.path.exists(_name):
        _datas.append((_name, "."))

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'app',
        'branding',
        'brand',
        'bundle_paths',
        'theme',
        'user_settings',
        'classifier',
        'metadata',
        'organizer',
        'vision_client',
        'customtkinter',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
        'google.cloud.vision',
        'google.cloud.vision_v1',
        'google.cloud.vision_v1.types',
        'google.auth',
        'google.auth.transport.requests',
        'google.oauth2',
        'grpc',
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
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='PhotoMetadataAssistant',
    icon='logo.png' if os.path.exists('logo.png') else None,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window (GUI app)
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
