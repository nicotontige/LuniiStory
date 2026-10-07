"""Transfer to the Lunii: detection, conversion, then import.

The import itself is delegated to Lunii.QT. The one link added here is the
Telmi → STUdio conversion, which makes store packs readable by that engine.
"""

import logging
import shutil
import tempfile
import zipfile
from pathlib import Path

from luniistory import config, library, logs, stores
from luniistory.convert import audio_pack, telmi
from luniistory.i18n import _, _n
from luniistory.lunii_api import (
    LUNII_V1,
    LUNII_V2,
    LUNII_V3,
    LuniiDevice,
    find_devices,
    lunii_stories,
    which_ffmpeg,
)

LOGGER = logging.getLogger("luniistory.transfer")

VERSION_NAMES = {LUNII_V1: "Lunii v1", LUNII_V2: "Lunii v2", LUNII_V3: "Lunii v3"}


class TransferError(Exception):
    pass


def find_lunii():
    """Mount points of the connected devices."""
    return [str(path) for path in find_devices()]


_names_loaded = False


def load_story_names():
    """Loads the catalogues the engine names stories from.

    Lunii.QT keeps an official database and one of third-party stories, and
    without them every story on the device reads "Unknown story". It loads them
    at startup; nothing did here, so the left panel named nothing.
    """
    global _names_loaded

    if _names_loaded:
        return True
    try:
        _names_loaded = bool(lunii_stories.story_load_db())
    except Exception:
        # Offline on a first run, say: names stay unknown, nothing else breaks.
        _names_loaded = False
    return _names_loaded


def open_device(mount_point):
    load_story_names()
    device = LuniiDevice(str(mount_point))
    if not device.device_version:
        LOGGER.warning("%s is not a recognised Lunii", mount_point)
        raise TransferError(_("{path} is not a recognised Lunii", path=mount_point))
    logs.describe_device(device)
    return device


def describe(device):
    version = VERSION_NAMES.get(device.device_version, _("version {number}", number=device.device_version))
    firmware = f"{device.fw_vers_major}.{device.fw_vers_minor}.{device.fw_vers_subminor}"
    stories = _n(len(device.stories), "{count} story", "{count} stories")
    return _(
        "{version} — firmware {firmware} — {stories}",
        version=version, firmware=firmware, stories=stories,
    )


def is_telmi_archive(archive_path):
    """A Telmi pack is recognised by its metadata.json / nodes.json pair."""
    if not zipfile.is_zipfile(archive_path):
        return False
    with zipfile.ZipFile(archive_path) as archive:
        names = archive.namelist()
    has_metadata = any(name.endswith("metadata.json") for name in names)
    has_nodes = any(name.endswith("nodes.json") for name in names)
    return has_metadata and has_nodes


def prepare_archive(archive_path, on_progress=None):
    """Makes the archive importable by Lunii.QT.

    A Telmi pack is converted to STUdio under the temporary folder; any other
    format (STUdio, .pk, 7z) is passed through untouched. The second tuple
    element says whether the returned path is temporary.

    ``on_progress`` receives ``(current_file, total)``.
    """
    archive_path = Path(archive_path)
    if not is_telmi_archive(archive_path):
        return archive_path, False

    config.ensure_dirs()
    # A folder per call, not per pack: two conversions of the same story would
    # otherwise unpack into the same place and delete each other's files.
    scratch = Path(tempfile.mkdtemp(prefix="convert-", dir=config.TMP_DIR))
    studio_zip = scratch / f"{archive_path.stem}.studio.zip"
    telmi.zip_to_studio_zip(archive_path, studio_zip, scratch / "unpacked", progress=on_progress)
    return studio_zip, True


def install_archive(device, archive_path, on_log=None, on_progress=None):
    """Converts if needed, then imports an archive already on disk.

    ``on_progress`` receives ``(step, current, total)``, the step naming the
    phase under way: conversion, then transfer.
    """
    def conversion_progress(current, total):
        if on_progress:
            on_progress(_("Converting"), current, total)

    prepared, temporary = prepare_archive(archive_path, on_progress=conversion_progress)
    try:
        return _import(device, prepared, on_log=on_log, on_progress=on_progress)
    finally:
        if temporary:
            shutil.rmtree(prepared.parent, ignore_errors=True)


def install_story(device, story, on_log=None, on_progress=None, session=None):
    """Downloads the story from its store, then installs it on the device.

    ``on_progress`` receives ``(step, current, total)``.
    """
    if on_log:
        on_log(logging.INFO, _("Downloading “{title}”…", title=story.title))

    def download_progress(received, total):
        if on_progress:
            on_progress(_("Downloading"), received, total)

    downloaded = library.download(story, on_progress=download_progress, session=session)

    if getattr(story, "is_audio", False):
        # A bare episode is not a pack; wrap it in one before importing.
        if on_log:
            on_log(logging.INFO, _("Building a pack around the episode…"))
        try:
            archive = _pack_episode(story, downloaded, session=session)
        except Exception:
            # A file that will not convert is no use cached: dropping it means
            # the next attempt fetches it again rather than failing identically.
            library.forget(story)
            raise
        try:
            return install_archive(device, archive, on_log=on_log, on_progress=on_progress)
        finally:
            shutil.rmtree(archive.parent, ignore_errors=True)

    return install_archive(device, downloaded, on_log=on_log, on_progress=on_progress)


def _pack_episode(story, audio_path, session=None):
    """Assembles cover art and episode audio into an importable archive."""
    config.ensure_dirs()
    cover = stores.cached_thumbnail(story, session=session)
    scratch = Path(tempfile.mkdtemp(prefix="episode-", dir=config.TMP_DIR))
    return audio_pack.build(
        title=story.title,
        audio_file=audio_path,
        cover=cover,
        output_zip=scratch / f"{story.key}.studio.zip",
        description=story.description,
        uuid=audio_pack.story_uuid(story.key),
    )


def _import(device, archive_path, on_log=None, on_progress=None):
    connections = []
    if on_log:
        device.signal_logger.connect(on_log)
        connections.append((device.signal_logger, on_log))
    if on_progress:
        def report(name, current, total):
            on_progress(_("Transferring"), current, total)

        device.signal_story_progress.connect(report)
        connections.append((device.signal_story_progress, report))

    try:
        result = device.import_story(str(archive_path))
    finally:
        for signal, handler in connections:
            signal.disconnect(handler)

    if not result:
        raise TransferError(_("The Lunii refused to import {name}", name=Path(archive_path).name))
    return result


def remove_story(device, short_uuid):
    return device.remove_story(short_uuid)


def installed_stories(device):
    """Stories present on the device, in menu order."""
    return [
        {
            "uuid": str(story.uuid),
            "short_uuid": story.uuid.hex[24:].upper(),
            "name": story.name,
            "night_mode": bool(getattr(story, "nm", False)),
        }
        for story in device.stories
    ]


def ffmpeg_available():
    """FFMPEG is only needed for packs whose audio is not Lunii-ready MP3."""
    return bool(which_ffmpeg())


def cleanup_tmp():
    shutil.rmtree(config.TMP_DIR, ignore_errors=True)
    config.ensure_dirs()
