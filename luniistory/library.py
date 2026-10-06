"""Local library: packs downloaded from the stores."""

import json
import zipfile

import requests

from luniistory import config
from luniistory.i18n import _
from luniistory.stores import TIMEOUT, USER_AGENT

INDEX_FILE_NAME = "index.json"


def _index_path():
    return config.LIBRARY_DIR / INDEX_FILE_NAME


def load_index():
    config.ensure_dirs()
    if not _index_path().exists():
        return {}
    try:
        return json.loads(_index_path().read_text("utf-8"))
    except (ValueError, OSError):
        return {}


def _save_index(index):
    _index_path().write_text(json.dumps(index, ensure_ascii=False, indent=2), "utf-8")


def pack_path(story):
    return config.LIBRARY_DIR / f"{story.key}.zip"


def is_downloaded(story):
    """True when a cached pack is at least as recent as the catalog entry."""
    entry = load_index().get(story.key)
    if not entry or not pack_path(story).exists():
        return False
    return entry.get("version", 0) >= story.version


def download(story, on_progress=None, session=None):
    """Fetches a story's pack and stores it in the library.

    ``on_progress`` receives ``(bytes_received, bytes_expected)``.
    """
    config.ensure_dirs()
    target = pack_path(story)
    if is_downloaded(story):
        return target

    partial = target.with_suffix(".part")
    session = session or requests.Session()
    with session.get(
        story.download, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT, stream=True
    ) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length") or 0)
        received = 0
        with open(partial, "wb") as handle:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                handle.write(chunk)
                received += len(chunk)
                if on_progress:
                    on_progress(received, total)

    if not zipfile.is_zipfile(partial):
        partial.unlink(missing_ok=True)
        raise ValueError(_("The download of “{title}” is not a zip archive", title=story.title))

    partial.replace(target)

    index = load_index()
    index[story.key] = {
        "title": story.title,
        "uuid": story.story_uuid,
        "pack_uuid": pack_metadata(target).get("uuid", ""),
        "version": story.version,
        "store": story.store_name,
        "age": story.age,
        "file": target.name,
    }
    _save_index(index)
    return target


def pack_metadata(archive_path):
    """Reads a Telmi pack's ``metadata.json`` without unpacking it."""
    try:
        with zipfile.ZipFile(archive_path) as archive:
            name = next((n for n in archive.namelist() if n.endswith("metadata.json")), None)
            if name is None:
                return {}
            return json.loads(archive.read(name))
    except (OSError, ValueError, zipfile.BadZipFile):
        return {}


def known_uuid(story):
    """UUID that will identify the story on the Lunii.

    The pack's own as soon as it has been downloaded, the catalog's otherwise —
    the latter not always being accurate.
    """
    cached = load_index().get(story.key, {}).get("pack_uuid")
    return (cached or story.story_uuid or "").upper()


def forget(story):
    """Drops the pack from the local cache."""
    pack_path(story).unlink(missing_ok=True)
    index = load_index()
    if index.pop(story.key, None) is not None:
        _save_index(index)


def downloaded_size():
    return sum(path.stat().st_size for path in config.LIBRARY_DIR.glob("*.zip"))


def clear():
    for path in config.LIBRARY_DIR.glob("*.zip"):
        path.unlink(missing_ok=True)
    _save_index({})
