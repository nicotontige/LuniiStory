"""Access to the Lunii.QT core, vendored as a submodule.

Lunii.QT exposes its device package under the generic name ``pkg``. Rather than
copying that code — and having to resynchronise it on every upstream fix — we
put the submodule on ``sys.path`` and re-export what we need.
"""

import sys
from pathlib import Path

# A frozen build already carries ``pkg`` and the engine's translations inside the
# bundle, so there is no submodule to put on the path.
FROZEN = bool(getattr(sys, "frozen", False))
BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", "")) if FROZEN else Path(__file__).resolve().parent.parent

VENDOR_DIR = BUNDLE_DIR / "vendor" / "Lunii.QT"
ENGINE_LOCALES_DIR = BUNDLE_DIR / "locales" if FROZEN else VENDOR_DIR / "locales"

if not FROZEN:
    if not (VENDOR_DIR / "pkg" / "api" / "device_lunii.py").exists():
        raise ImportError(
            f"Lunii.QT not found in {VENDOR_DIR}. "
            "Run: git submodule update --init --recursive"
        )

    if str(VENDOR_DIR) not in sys.path:
        sys.path.insert(0, str(VENDOR_DIR))

from pkg.api import stories as lunii_stories  # noqa: E402
from pkg.api.constants import (  # noqa: E402
    CACHE_DIR,
    CFG_DIR,
    LUNII_V1,
    LUNII_V2,
    LUNII_V3,
    which_ffmpeg,
)
from pkg.api.convert_audio import transcoding_required  # noqa: E402
from pkg.api.device_lunii import LuniiDevice, is_lunii  # noqa: E402
from pkg.api.devices import find_devices  # noqa: E402

# The engine writes its third-party story database and cache under ~/.lunii-qt,
# and expects the host application to have created the folder.
Path(CFG_DIR).mkdir(parents=True, exist_ok=True)
Path(CACHE_DIR).mkdir(parents=True, exist_ok=True)

__all__ = [
    "ENGINE_LOCALES_DIR",
    "LuniiDevice",
    "find_devices",
    "is_lunii",
    "lunii_stories",
    "transcoding_required",
    "which_ffmpeg",
    "LUNII_V1",
    "LUNII_V2",
    "LUNII_V3",
]
