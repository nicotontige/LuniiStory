"""Browsable directory of podcast feeds, each addable as a store.

Shown as a wall of covers: artwork is how these are recognised, and a list of
titles made every feed look alike. Picking one fills the panel underneath.
"""

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
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
    QScrollArea,
    QVBoxLayout,
)

from luniistory.i18n import _, _n
from luniistory.ui.story_card import shorten
from luniistory.ui.workers import FeedDirectoryWorker, FeedThumbnailWorker

COVER_SIZE = QSize(120, 120)
CELL_SIZE = QSize(144, 176)
DETAIL_COVER = QSize(96, 96)


def _placeholder():
    pixmap = QPixmap(COVER_SIZE)
    pixmap.fill(QColor("#ebe5dc"))
    return QIcon(pixmap)


class FeedDirectoryDialog(QDialog):
    def __init__(self, known_urls, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Browse story feeds"))
        self.setModal(True)
        self.resize(860, 700)

        self._known = {url.strip() for url in known_urls}
        self._directory = None
        self._items = {}
        self._covers = {}
        self.added = []

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Search the feeds…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filter)

        self.status = QLabel(_("Loading the feed directory…"))
        self.status.setObjectName("panelSubtitle")

        self.grid = QListWidget()
        self.grid.setViewMode(QListWidget.IconMode)
        self.grid.setIconSize(COVER_SIZE)
        self.grid.setGridSize(CELL_SIZE)
        self.grid.setResizeMode(QListWidget.Adjust)
        self.grid.setMovement(QListWidget.Static)   # covers are not draggable
        self.grid.setSelectionMode(QListWidget.SingleSelection)
        self.grid.setWordWrap(True)
        self.grid.setSpacing(6)
        self.grid.setObjectName("feedGrid")
        self.grid.currentItemChanged.connect(self._on_selected)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(_("Close"))
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 12)
        layout.setSpacing(10)
        layout.addWidget(self.search)
        layout.addWidget(self.status)
        layout.addWidget(self.grid, 1)
        layout.addWidget(self._build_details())
        layout.addWidget(buttons)

        self._worker = FeedDirectoryWorker(self)
        self._worker.loaded.connect(self._on_loaded)
        self._worker.failed.connect(self._on_failed)
        self._worker.start()
        self._thumbnails = None

    # -- details ---------------------------------------------------------

    def _build_details(self):
        panel = QFrame()
        panel.setObjectName("feedDetails")
        panel.setFixedHeight(170)

        self.detail_cover = QLabel()
        self.detail_cover.setFixedSize(DETAIL_COVER)
        self.detail_cover.setObjectName("thumbnail")
        self.detail_cover.setAlignment(Qt.AlignCenter)

        self.detail_title = QLabel()
        self.detail_title.setObjectName("cardTitle")
        self.detail_title.setWordWrap(True)

        self.detail_subtitle = QLabel()
        self.detail_subtitle.setWordWrap(True)

        # Some blurbs run to several paragraphs, including the credits and the
        # hosting notice, so the whole thing is kept and scrolls instead.
        self.detail_description = QLabel()
        self.detail_description.setObjectName("cardDescription")
        self.detail_description.setWordWrap(True)
        self.detail_description.setAlignment(Qt.AlignTop)
        self.detail_description.setTextInteractionFlags(Qt.TextSelectableByMouse)

        scroller = QScrollArea()
        scroller.setObjectName("detailScroll")
        scroller.setWidget(self.detail_description)
        scroller.setWidgetResizable(True)
        scroller.setFrameShape(QFrame.NoFrame)
        scroller.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        texts = QVBoxLayout()
        texts.setSpacing(3)
        texts.addWidget(self.detail_title)
        texts.addWidget(self.detail_subtitle)
        texts.addWidget(scroller, 1)

        self.add_button = QPushButton(_("Add"))
        self.add_button.setObjectName("primary")
        self.add_button.clicked.connect(self._on_add)

        self.website_button = QPushButton(_("Website"))
        self.website_button.clicked.connect(self._on_website)

        # The button swaps between two labels of very different lengths, and in
        # two languages; size it for the longest so none of them is clipped.
        metrics = self.add_button.fontMetrics()
        widest = max(metrics.horizontalAdvance(label)
                     for label in (_("Add"), _("Already added"), _("Website")))
        for button in (self.add_button, self.website_button):
            button.setMinimumWidth(widest + 44)

        actions = QVBoxLayout()
        actions.setSpacing(6)
        actions.addWidget(self.add_button)
        actions.addWidget(self.website_button)
        actions.addStretch(1)

        layout = QHBoxLayout(panel)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(12)
        layout.addWidget(self.detail_cover, 0, Qt.AlignTop)
        layout.addLayout(texts, 1)
        layout.addLayout(actions, 0)

        self._show_feed(None)
        return panel

    def _show_feed(self, feed):
        self._selected = feed
        if feed is None:
            self.detail_cover.setPixmap(QPixmap())
            self.detail_cover.setText("")
            self.detail_title.setText(_("Pick a feed to see what it holds."))
            self.detail_subtitle.setText("")
            self.detail_description.setText("")
            self.add_button.setEnabled(False)
            self.website_button.setEnabled(False)
            return

        cover = self._covers.get(feed.key)
        if cover:
            self.detail_cover.setPixmap(
                QPixmap(cover).scaled(DETAIL_COVER, Qt.KeepAspectRatio, Qt.SmoothTransformation)
            )
        else:
            self.detail_cover.setPixmap(QPixmap())

        self.detail_title.setText(feed.title)
        self.detail_subtitle.setText(" · ".join(filter(None, [
            feed.publisher,
            _("contains advertising") if feed.has_ads else "",
        ])))
        self.detail_subtitle.setObjectName("feedAds" if feed.has_ads else "cardSubtitle")
        self.detail_subtitle.style().unpolish(self.detail_subtitle)
        self.detail_subtitle.style().polish(self.detail_subtitle)
        self.detail_description.setText(" ".join(feed.description.split()))

        added = feed.url in self._known
        self.add_button.setText(_("Already added") if added else _("Add"))
        self.add_button.setEnabled(not added)
        self.website_button.setEnabled(bool(feed.website))

    # -- directory -------------------------------------------------------

    def _on_loaded(self, directory):
        self._directory = directory
        placeholder = _placeholder()
        for feed in directory.feeds:
            item = QListWidgetItem(shorten(feed.title, 40), self.grid)
            item.setIcon(placeholder)
            item.setSizeHint(CELL_SIZE)
            item.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
            item.setToolTip(feed.title)
            item.setData(Qt.UserRole, feed.key)
            self._items[feed.key] = (item, feed)

        self._apply_filter()
        self.grid.scrollToTop()
        self._thumbnails = FeedThumbnailWorker(directory.feeds, self)
        self._thumbnails.ready.connect(self._on_thumbnail)
        self._thumbnails.start()

    def _on_failed(self, error):
        self.status.setText(_("Could not load the feed directory: {error}", error=error))

    def _on_thumbnail(self, key, path):
        self._covers[key] = path
        entry = self._items.get(key)
        if entry:
            entry[0].setIcon(QIcon(path))
        if self._selected is not None and self._selected.key == key:
            self._show_feed(self._selected)

    def _on_selected(self, current, _previous):
        if current is None:
            self._show_feed(None)
            return
        entry = self._items.get(current.data(Qt.UserRole))
        self._show_feed(entry[1] if entry else None)

    # -- actions ---------------------------------------------------------

    def _on_add(self):
        feed = self._selected
        if feed is None or feed.url in self._known:
            return
        self.added.append((feed.title, feed.url))
        self._known.add(feed.url)
        self._show_feed(feed)

    def _on_website(self):
        if self._selected is not None and self._selected.website:
            QDesktopServices.openUrl(self._selected.website)

    def _apply_filter(self):
        if self._directory is None:
            return
        matching = {feed.key for feed in self._directory.search(self.search.text().strip())}
        for key, (item, _feed) in self._items.items():
            item.setHidden(key not in matching)
        self.status.setText(_n(len(matching), "{count} feed", "{count} feeds"))

    # -- plumbing --------------------------------------------------------

    def _stop_workers(self):
        for worker in (self._worker, self._thumbnails):
            if worker is None:
                continue
            if hasattr(worker, "stop"):
                worker.stop()
            worker.wait(2000)

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
