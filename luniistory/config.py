"""On-disk locations and persisted preferences."""

import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("LUNIISTORY_HOME") or (Path.home() / ".luniistory"))
CACHE_DIR = APP_DIR / "cache"          # thumbnails and downloaded catalogs
LIBRARY_DIR = APP_DIR / "library"      # downloaded Telmi packs, ready to transfer
TMP_DIR = APP_DIR / "tmp"              # conversions in flight
STORES_FILE = APP_DIR / "stores.json"
SETTINGS_FILE = APP_DIR / "settings.json"

# The two stores Telmi Sync ships with, kept as they are.
DEFAULT_STORES = [
    {
        "name": "Telmi Interactive",
        "url": "https://gist.githubusercontent.com/DantSu/49ed776755f3a01c995e78e3fd1cb79f/raw/telmi-interactive.json",
        "deletable": False,
    },
    {
        "name": "Litteratureaudio.com",
        "url": "https://gist.githubusercontent.com/DantSu/c6a58c2d0f3b4dc01ed6cdeed6b93ebb/raw/litteratureaudio.json",
        "deletable": False,
    },
]


def ensure_dirs():
    for directory in (APP_DIR, CACHE_DIR, LIBRARY_DIR, TMP_DIR):
        directory.mkdir(parents=True, exist_ok=True)


def load_stores():
    """Configured stores, the default ones always among them."""
    ensure_dirs()

    user_stores = []
    if STORES_FILE.exists():
        try:
            user_stores = json.loads(STORES_FILE.read_text("utf-8")).get("stores", [])
        except (ValueError, OSError):
            user_stores = []

    known_urls = {store["url"] for store in DEFAULT_STORES}
    merged = DEFAULT_STORES + [
        {**store, "deletable": True} for store in user_stores if store.get("url") not in known_urls
    ]
    save_stores(merged)
    return merged


def save_stores(stores):
    ensure_dirs()
    STORES_FILE.write_text(json.dumps({"stores": stores}, ensure_ascii=False, indent=2), "utf-8")


def add_store(name, url):
    stores = load_stores()
    if any(store["url"] == url for store in stores):
        return stores
    stores.append({"name": name, "url": url, "deletable": True})
    save_stores(stores)
    return stores


def remove_store(url):
    stores = [store for store in load_stores() if store["url"] != url or not store.get("deletable", True)]
    save_stores(stores)
    return stores


def load_settings():
    """User preferences: language, and whatever gets added later."""
    ensure_dirs()
    if not SETTINGS_FILE.exists():
        return {}
    try:
        return json.loads(SETTINGS_FILE.read_text("utf-8"))
    except (ValueError, OSError):
        return {}


def save_setting(key, value):
    settings = load_settings()
    settings[key] = value
    SETTINGS_FILE.write_text(json.dumps(settings, ensure_ascii=False, indent=2), "utf-8")
    return settings
