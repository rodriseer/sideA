# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec — generic photo metadata GUI (branding in branding.py)
# Build: pyinstaller SideA.spec

block_cipher = None

import os
_background = None
for name in ('background.jpeg', 'background.jpg', 'background.png', 'background.webp', 'background.bmp'):
    if os.path.exists(name):
        _background = name
        break
    pub = os.path.join('public', name)
    if os.path.exists(pub):
        _background = pub
        break
_datas = [(_background, '.')] if _background else []

a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=[],
    datas=_datas,
    hiddenimports=[
        'app',
        'branding',
        'brand',
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
