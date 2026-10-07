"""Browsable directory of podcast feeds, each addable as a store."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from luniistory.i18n import _, _n
from luniistory.ui.story_card import shorten
from luniistory.ui.workers import FeedDirectoryWorker, FeedThumbnailWorker

THUMB_SIZE = QSize(64, 64)
ROW_HEIGHT = 96
DESCRIPTION_LIMIT = 150


class FeedRow(QFrame):
    """One directory entry: cover, title, publisher, and an add button."""

    add_requested = Signal(object)

    def __init__(self, feed, already_added, parent=None):
        super().__init__(parent)
        self.feed = feed
        self.setObjectName("feedRow")

        self.thumbnail = QLabel("…")
        self.thumbnail.setFixedSize(THUMB_SIZE)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setObjectName("thumbnail")

        title = QLabel(feed.title)
        title.setObjectName("cardTitle")
        title.setWordWrap(True)

        subtitle = QLabel(" · ".join(filter(None, [
            feed.publisher,
            _("contains advertising") if feed.has_ads else "",
        ])))
        subtitle.setObjectName("feedAds" if feed.has_ads else "cardSubtitle")
        subtitle.setWordWrap(True)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        if feed.description:
            description = QLabel(shorten(feed.description, DESCRIPTION_LIMIT))
            description.setObjectName("cardDescription")
            description.setWordWrap(True)
            texts.addWidget(description)
        texts.addStretch(1)

        buttons = QVBoxLayout()
        buttons.setSpacing(4)
        self.add_button = QPushButton(_("Already added") if already_added else _("Add"))
        self.add_button.setEnabled(not already_added)
        self.add_button.clicked.connect(lambda: self.add_requested.emit(feed))
        buttons.addWidget(self.add_button)
        if feed.website:
            website = QPushButton(_("Website"))
            website.clicked.connect(lambda: QDesktopServices.openUrl(feed.website))
            buttons.addWidget(website)
        buttons.addStretch(1)

        self.setFixedHeight(ROW_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)
        layout.addWidget(self.thumbnail, 0, Qt.AlignTop)
        layout.addLayout(texts, 1)
        layout.addLayout(buttons, 0)

    def set_thumbnail(self, path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        self.thumbnail.setPixmap(pixmap.scaled(THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.thumbnail.setText("")

    def mark_added(self):
        self.add_button.setText(_("Already added"))
        self.add_button.setEnabled(False)


class FeedDirectoryDialog(QDialog):
    """Lists the published feeds so a store can be added without an address."""

    def __init__(self, known_urls, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Browse story feeds"))
        self.setModal(True)
        self.resize(760, 600)

        self._known = {url.strip() for url in known_urls}
        self._rows = {}
        self.added = []

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Search the feeds…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)

        self.status = QLabel(_("Loading the feed directory…"))
        self.status.setObjectName("cardSubtitle")

        self.listing = QListWidget()
        self.listing.setSelectionMode(QListWidget.NoSelection)
        self.listing.setSpacing(4)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(_("Close"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(self.search)
        layout.addWidget(self.status)
        layout.addWidget(self.listing, 1)
        layout.addWidget(buttons)

        self._worker = FeedDirectoryWorker(self)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()

        self._thumbnails = None

    def _on_loaded(self, directory):
        self._directory = directory
        for feed in directory.feeds:
            row = FeedRow(feed, feed.url in self._known)
            row.add_requested.connect(self._on_add)
            item = QListWidgetItem(self.listing)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            self.listing.addItem(item)
            self.listing.setItemWidget(item, row)
            self._rows[feed.key] = (row, item)

        self._apply_filter()
        # Populating leaves the view at the bottom; the list reads from the top.
        self.listing.scrollToTop()
        self._thumbnails = FeedThumbnailWorker(directory.feeds, self)
        self._thumbnails.ready.connect(self._on_thumbnail)
        self._thumbnails.start()

    def _on_failed(self, error):
        self.status.setText(_("Could not load the feed directory: {error}", error=error))

    def _on_thumbnail(self, key, path):
        entry = self._rows.get(key)
        if entry:
            entry[0].set_thumbnail(path)

    def _on_add(self, feed):
        self.added.append((feed.title, feed.url))
        self._known.add(feed.url)
        entry = self._rows.get(feed.key)
        if entry:
            entry[0].mark_added()

    def _apply_filter(self):
        needle = self.search.text().strip()
        matching = {feed.key for feed in self._directory.search(needle)}
        for key, (_row, item) in self._rows.items():
            item.setHidden(key not in matching)
        self.status.setText(_n(len(matching), "{count} feed", "{count} feeds"))

    def _stop_workers(self):
        for worker in (self._worker, self._thumbnails):
            if worker is None:
                continue
            if hasattr(worker, "stop"):
                worker.stop()
            worker.wait(2000)

    # done() covers accept, reject and a programmatic close alike; closeEvent
    # alone leaves the threads running when the dialog is dismissed otherwise.
    def done(self, result):
        self._stop_workers()
        super().done(result)

    def closeEvent(self, event):
        self._stop_workers()
        super().closeEvent(event)

    @classmethod
    def ask(cls, known_urls, parent=None):
        """Returns the ``(name, url)`` pairs the user added."""
        dialog = cls(known_urls, parent)
        dialog.exec()
        return dialog.added
