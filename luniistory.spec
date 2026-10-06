# -*- mode: python ; coding: utf-8 -*-
"""Recette PyInstaller — un exécutable pour la plateforme courante."""

import sys

block_cipher = None

analysis = Analysis(
    ["luniistory/__main__.py"],
    pathex=["vendor/Lunii.QT"],   # le paquet « pkg » de Lunii.QT
    binaries=[],
    datas=[
        ("luniistory/ui/style.qss", "luniistory/ui"),
        ("luniistory/locales", "luniistory/locales"),
        ("vendor/Lunii.QT/locales", "locales"),
    ],
    hiddenimports=[
        "pkg.api.device_lunii",
        "pkg.api.device_flam",
        "pkg.api.devices",
        "pkg.api.stories",
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
        bundle_identifier="fr.luniistory.app",
        info_plist={
            "NSHighResolutionCapable": True,
            # macOS refuse l'accès aux volumes amovibles sans cette déclaration,
            # et la Lunii est montée comme un disque USB.
            "NSRemovableVolumesUsageDescription":
                "luniiStory lit et écrit les histoires sur la Lunii branchée en USB.",
        },
    )
