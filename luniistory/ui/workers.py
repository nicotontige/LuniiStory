"""Long-running work, kept off the interface thread."""

import logging
import traceback

import requests
from PySide6.QtCore import QThread, Signal

from luniistory import directory, stores, transfer, usb
from luniistory.i18n import _


class CatalogWorker(QThread):
    """Downloads the catalogs of every configured store."""

    loaded = Signal(list)
    store_failed = Signal(str, str)

    def run(self):
        session = requests.Session()
        catalog = stores.fetch_all(
            session=session,
            on_error=lambda store, error: self.store_failed.emit(store["name"], str(error)),
        )
        self.loaded.emit(catalog)


class ThumbnailWorker(QThread):
    """Fills the thumbnail cache, one story at a time."""

    ready = Signal(str, str)

    def __init__(self, catalog, parent=None):
        super().__init__(parent)
        self._catalog = list(catalog)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        session = requests.Session()
        for story in self._catalog:
            if self._stop:
                return
            path = stores.cached_thumbnail(story, session=session)
            if path:
                self.ready.emit(story.key, str(path))


class DeviceWorker(QThread):
    """Looks for connected Lunii devices and reads their contents.

    ``attached`` says whether Lunii hardware is on the USB bus, which tells a
    device that is off apart from one that is not plugged in at all.
    """

    found = Signal(list, bool)

    def run(self):
        devices = []
        for mount_point in transfer.find_lunii():
            try:
                device = transfer.open_device(mount_point)
                devices.append({
                    "mount_point": mount_point,
                    "label": transfer.describe(device),
                    "uuids": {story["uuid"].upper() for story in transfer.installed_stories(device)},
                    "stories": transfer.installed_stories(device),
                })
            except Exception as error:
                devices.append({
                    "mount_point": mount_point,
                    "label": _("unreadable — {error}", error=error),
                    "uuids": set(),
                    "stories": [],
                })
        self.found.emit(devices, bool(devices) or usb.is_lunii_attached())


class InstallWorker(QThread):
    """Downloads, converts and transfers a selection of stories."""

    log = Signal(int, str)
    progress = Signal(str, int, int)
    story_started = Signal(str, str)
    story_done = Signal(str, bool, str)

    def __init__(self, mount_point, catalog, parent=None):
        super().__init__(parent)
        self._mount_point = mount_point
        self._catalog = list(catalog)
        self._abort = False
        self._device = None

    def abort(self):
        self._abort = True
        if self._device is not None:
            self._device.abort_process = True

    def run(self):
        try:
            # The device is opened here: it is only ever touched from this thread.
            self._device = transfer.open_device(self._mount_point)
        except Exception as error:
            self.log.emit(logging.ERROR, str(error))
            return

        session = requests.Session()
        for story in self._catalog:
            if self._abort:
                self.log.emit(logging.WARNING, _("Transfer interrupted."))
                break
            self.story_started.emit(story.key, story.title)
            try:
                transfer.install_story(
                    self._device, story,
                    on_log=self.log.emit,
                    on_progress=self.progress.emit,
                    session=session,
                )
                self.story_done.emit(story.key, True, _("“{title}” transferred", title=story.title))
            except Exception as error:
                self.log.emit(logging.DEBUG, traceback.format_exc())
                self.story_done.emit(story.key, False, str(error))

        transfer.cleanup_tmp()
        self._device = None


class ArchiveWorker(InstallWorker):
    """Same thing, for archives already on disk."""

    def run(self):
        try:
            self._device = transfer.open_device(self._mount_point)
        except Exception as error:
            self.log.emit(logging.ERROR, str(error))
            return

        for path in self._catalog:
            if self._abort:
                break
            self.story_started.emit(str(path), str(path))
            try:
                transfer.install_archive(
                    self._device, path,
                    on_log=self.log.emit,
                    on_progress=self.progress.emit,
                )
                self.story_done.emit(str(path), True, _("{path} transferred", path=path))
            except Exception as error:
                self.log.emit(logging.DEBUG, traceback.format_exc())
                self.story_done.emit(str(path), False, str(error))

        transfer.cleanup_tmp()
        self._device = None


class RemoveWorker(QThread):
    """Removes stories from the device."""

    log = Signal(int, str)
    done = Signal()

    def __init__(self, mount_point, short_uuids, parent=None):
        super().__init__(parent)
        self._mount_point = mount_point
        self._short_uuids = list(short_uuids)

    def run(self):
        try:
            device = transfer.open_device(self._mount_point)
        except Exception as error:
            self.log.emit(logging.ERROR, str(error))
            return
        device.signal_logger.connect(self.log.emit)
        for short_uuid in self._short_uuids:
            device.remove_story(short_uuid)
        self.done.emit()


class FeedDirectoryWorker(QThread):
    """Downloads the published list of podcast feeds."""

    loaded = Signal(object)
    failed = Signal(str)

    def run(self):
        try:
            self.loaded.emit(directory.fetch())
        except Exception as error:
            self.failed.emit(str(error))


class FeedThumbnailWorker(QThread):
    """Caches the directory's cover images, one feed at a time."""

    ready = Signal(str, str)

    def __init__(self, feeds, parent=None):
        super().__init__(parent)
        self._feeds = list(feeds)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        session = requests.Session()
        for feed in self._feeds:
            if self._stop:
                return
            path = stores.cached_thumbnail(feed, session=session)
            if path:
                self.ready.emit(feed.key, str(path))
