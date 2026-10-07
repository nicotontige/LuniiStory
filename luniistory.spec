# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller recipe — one executable for the current platform."""

import sys

block_cipher = None

analysis = Analysis(
    ["luniistory/__main__.py"],
    pathex=["vendor/Lunii.QT"],   # the "pkg" package from Lunii.QT
    binaries=[],
    datas=[
        ("luniistory/ui/style.qss", "luniistory/ui"),
        ("luniistory/ui/icons", "luniistory/ui/icons"),
        ("luniistory/locales", "luniistory/locales"),
        ("vendor/Lunii.QT/locales", "locales"),
    ],
    hiddenimports=[
        "pkg.api.device_lunii",
        "pkg.api.device_flam",
        "pkg.api.devices",
        "pkg.api.stories",
        "lameenc",
        "miniaudio",
    ],
    hookspath=[],
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "PySide6.QtWebEngineCore"],
    cipher=block_cipher,
    noarchive=False,
)

archive = PYZ(analysis.pure, analysis.zipped_data, cipher=block_cipher)

executable = EXE(
    archive,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="luniistory",
    icon="luniistory/ui/icons/icon.ico",
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
)

collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.zipfiles,
    analysis.datas,
    strip=False,
    upx=False,
    name="luniistory",
)

if sys.platform == "darwin":
    app = BUNDLE(
        collection,
        name="luniiStory.app",
        icon="luniistory/ui/icons/icon.icns",
        bundle_identifier="fr.luniistory.app",
        info_plist={
            "NSHighResolutionCapable": True,
            # macOS denies access to removable volumes without this, and the
            # Lunii mounts as a USB disk.
            "NSRemovableVolumesUsageDescription":
                "luniiStory reads and writes the stories on the Lunii connected over USB.",
        },
    )
