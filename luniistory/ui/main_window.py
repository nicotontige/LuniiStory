"""Main window: store catalogs on one side, the Lunii on the other."""

import logging
import unicodedata
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from luniistory import config, i18n, library, transfer
from luniistory.i18n import _, _n
from luniistory.ui.store_dialog import StoreDialog
from luniistory.ui.story_card import StoryCard
from luniistory.ui.workers import (
    ArchiveWorker,
    CatalogWorker,
    DeviceWorker,
    InstallWorker,
    RemoveWorker,
    ThumbnailWorker,
)


def _age_filters():
    return [
        (_("All ages"), None),
        (_("Ages {age} and up", age=3), 3),
        (_("Ages {age} and up", age=5), 5),
        (_("Ages {age} and up", age=7), 7),
    ]


# Room the drop-down needs beyond the text itself: the check mark against the
# current entry, the arrow on the closed box, and the padding from the
# stylesheet on both. Qt sizes the popup from the box, so it has to be here.
COMBO_CHROME = 64


def _fit_to_contents(combo):
    """Widens a combo so no entry is cut off, in any language."""
    metrics = combo.fontMetrics()
    widest = max(
        (metrics.horizontalAdvance(combo.itemText(index)) for index in range(combo.count())),
        default=0,
    )
    combo.setMinimumWidth(widest + COMBO_CHROME)
    combo.view().setMinimumWidth(widest + COMBO_CHROME)


def _normalize(text):
    decomposed = unicodedata.normalize("NFD", str(text).lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("luniiStory")
        self.resize(1040, 720)
        self.setAcceptDrops(True)

        self._catalog = []
        self._cards = {}
        self._selection = set()
        self._devices = []
        self._workers = []
        self._transfer_worker = None
        self._current_title = ""
        self._age_filters = _age_filters()

        # Set when the language changes: app.py then rebuilds the window.
        self.restart_requested = False

        self._build_ui()
        self.refresh_devices()
        self.refresh_catalog()

    # -- construction ----------------------------------------------------

    def _build_ui(self):
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        layout.addWidget(self._build_filters())
        layout.addWidget(self._build_tabs(), 1)
        layout.addWidget(self._build_footer())
        self.setCentralWidget(root)

    def _build_header(self):
        header = QFrame()
        header.setObjectName("header")
        layout = QHBoxLayout(header)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        title_box = QVBoxLayout()
        title_box.setSpacing(0)
        title = QLabel("luniiStory")
        title.setObjectName("appTitle")
        self.device_status = QLabel(_("Looking for a Lunii…"))
        self.device_status.setObjectName("deviceStatus")
        title_box.addWidget(title)
        title_box.addWidget(self.device_status)

        self.language_combo = QComboBox()
        for code in i18n.available_languages():
            self.language_combo.addItem(i18n.language_name(code), code)
        self.language_combo.setCurrentIndex(i18n.available_languages().index(i18n.current_language()))
        self.language_combo.currentIndexChanged.connect(self._on_language_changed)
        _fit_to_contents(self.language_combo)

        self.device_combo = QComboBox()
        self.device_combo.setMinimumWidth(240)
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)

        refresh = QPushButton(_("Find the Lunii"))
        refresh.clicked.connect(self.refresh_devices)

        layout.addLayout(title_box)
        layout.addStretch(1)
        layout.addWidget(self.language_combo)
        layout.addWidget(self.device_combo)
        layout.addWidget(refresh)
        return header

    def _build_filters(self):
        bar = QFrame()
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(18, 12, 18, 6)
        layout.setSpacing(10)

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Search for a story…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filters)

        self.age_combo = QComboBox()
        for label, _age in self._age_filters:
            self.age_combo.addItem(label)
        self.age_combo.currentIndexChanged.connect(self._apply_filters)

        reload_button = QPushButton(_("Refresh stores"))
        reload_button.clicked.connect(self.refresh_catalog)

        add_store = QPushButton(_("Add a store"))
        add_store.clicked.connect(self._add_store)

        import_button = QPushButton(_("Import a file…"))
        import_button.clicked.connect(self._choose_archives)

        layout.addWidget(self.search, 1)
        layout.addWidget(self.age_combo)
        layout.addWidget(reload_button)
        layout.addWidget(add_store)
        layout.addWidget(import_button)
        return bar

    def _build_tabs(self):
        self.tabs = QTabWidget()
        self.device_list = QListWidget()
        self.device_list.setSelectionMode(QListWidget.ExtendedSelection)

        device_tab = QWidget()
        device_layout = QVBoxLayout(device_tab)
        device_layout.setContentsMargins(18, 10, 18, 10)
        device_layout.addWidget(self.device_list, 1)

        self.remove_button = QPushButton(_("Remove from the Lunii"))
        self.remove_button.clicked.connect(self._remove_selected)
        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(self.remove_button)
        device_layout.addLayout(buttons)

        self.tabs.addTab(device_tab, _("On the Lunii"))
        return self.tabs

    def _build_footer(self):
        footer = QFrame()
        footer.setObjectName("footer")
        layout = QVBoxLayout(footer)
        layout.setContentsMargins(18, 10, 18, 12)
        layout.setSpacing(8)

        top = QHBoxLayout()
        self.progress_label = QLabel(_("Ready"))
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setMaximumWidth(260)
        self.progress.setVisible(False)

        self.log_button = QPushButton(_("Log"))
        self.log_button.setCheckable(True)
        self.log_button.toggled.connect(lambda shown: self.log_view.setVisible(shown))

        self.transfer_button = QPushButton(_("Transfer selection"))
        self.transfer_button.setObjectName("primary")
        self.transfer_button.setEnabled(False)
        self.transfer_button.clicked.connect(self._transfer_selection)

        top.addWidget(self.progress_label, 1)
        top.addWidget(self.progress)
        top.addWidget(self.log_button)
        top.addWidget(self.transfer_button)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(160)
        self.log_view.setVisible(False)

        layout.addLayout(top)
        layout.addWidget(self.log_view)
        return footer

    # -- language --------------------------------------------------------

    def _on_language_changed(self, index):
        code = self.language_combo.itemData(index)
        if code == i18n.current_language():
            return
        config.save_setting("language", code)
        i18n.set_language(code)
        self.restart_requested = True
        self.close()

    # -- devices ---------------------------------------------------------

    def refresh_devices(self):
        self.device_status.setText(_("Looking for a Lunii…"))
        worker = DeviceWorker(self)
        worker.found.connect(self._on_devices_found)
        self._start(worker)

    def _on_devices_found(self, devices):
        self._devices = devices
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(Path(device["mount_point"]).name or device["mount_point"])
        self.device_combo.blockSignals(False)

        if not devices:
            self.device_status.setText(_("No Lunii connected"))
            self.device_combo.addItem("—")
        else:
            self.device_status.setText(devices[0]["label"])

        self._refresh_device_tab()
        self._refresh_states()
        self._update_transfer_button()

    @property
    def current_device(self):
        index = self.device_combo.currentIndex()
        if 0 <= index < len(self._devices):
            return self._devices[index]
        return None

    def _on_device_changed(self):
        device = self.current_device
        self.device_status.setText(device["label"] if device else _("No Lunii connected"))
        self._refresh_device_tab()
        self._refresh_states()
        self._update_transfer_button()

    def _refresh_device_tab(self):
        self.device_list.clear()
        device = self.current_device
        if not device:
            self.device_list.addItem(_("Plug a Lunii in to see what it holds."))
            self.remove_button.setEnabled(False)
            self.tabs.setTabText(0, _("On the Lunii"))
            return
        for story in device["stories"]:
            item = QListWidgetItem(f"{story['name']}" + ("  🌙" if story["night_mode"] else ""))
            item.setData(Qt.UserRole, story["short_uuid"])
            self.device_list.addItem(item)
        self.remove_button.setEnabled(bool(device["stories"]))
        self.tabs.setTabText(0, f"{_('On the Lunii')} ({len(device['stories'])})")

    # -- catalog ---------------------------------------------------------

    def refresh_catalog(self):
        self.progress_label.setText(_("Loading stores…"))
        worker = CatalogWorker(self)
        worker.loaded.connect(self._on_catalog_loaded)
        worker.store_failed.connect(
            lambda name, error: self._append_log(
                logging.WARNING, _("Store “{name}”: {error}", name=name, error=error)
            )
        )
        self._start(worker)

    def _on_catalog_loaded(self, catalog):
        self._catalog = catalog
        self._cards = {}
        self._selection.clear()

        # Keep only the device tab, then rebuild one tab per store.
        while self.tabs.count() > 1:
            self.tabs.removeTab(1)

        for store_name in dict.fromkeys(story.store_name for story in catalog):
            stories = [story for story in catalog if story.store_name == store_name]
            self.tabs.addTab(self._build_store_tab(stories), f"{store_name} ({len(stories)})")

        self.progress_label.setText(_(
            "{stories} across {stores}",
            stories=_n(len(catalog), "{count} story", "{count} stories"),
            stores=_n(self.tabs.count() - 1, "{count} store", "{count} stores"),
        ))
        if self.tabs.count() > 1 and self.tabs.currentIndex() == 0:
            self.tabs.setCurrentIndex(1)

        self._refresh_states()
        self._apply_filters()

        thumbnails = ThumbnailWorker(catalog, self)
        thumbnails.ready.connect(self._on_thumbnail)
        self._start(thumbnails)

    def _build_store_tab(self, stories):
        listing = QListWidget()
        listing.setSelectionMode(QListWidget.NoSelection)
        listing.setSpacing(4)
        for story in stories:
            card = StoryCard(story)
            card.toggled.connect(self._on_card_toggled)
            item = QListWidgetItem(listing)
            item.setSizeHint(card.sizeHint())
            listing.addItem(item)
            listing.setItemWidget(item, card)
            self._cards[story.key] = (card, listing, item)
        return listing

    def _on_thumbnail(self, key, path):
        entry = self._cards.get(key)
        if entry:
            entry[0].set_thumbnail(path)

    def _refresh_states(self):
        """Resets each card's state against the current device."""
        device = self.current_device
        installed = device["uuids"] if device else set()
        for key, (card, _listing, _item) in self._cards.items():
            if card.property("state") in ("working", "pending", "done", "failed"):
                continue
            uuid = library.known_uuid(card.story)
            if uuid and uuid.upper() in installed:
                card.set_state("installed")
            elif library.is_downloaded(card.story):
                card.set_state("downloaded")
            else:
                card.set_state("")

    def _apply_filters(self):
        needle = _normalize(self.search.text().strip())
        max_age = self._age_filters[self.age_combo.currentIndex()][1]
        for card, _listing, item in self._cards.values():
            story = card.story
            matches = not needle or needle in _normalize(f"{story.title} {story.description} {story.category}")
            if max_age is not None and story.age and story.age > max_age:
                matches = False
            item.setHidden(not matches)

    # -- selection and transfer -------------------------------------------

    def _on_card_toggled(self, key, checked):
        if checked:
            self._selection.add(key)
        else:
            self._selection.discard(key)
        self._update_transfer_button()

    def _update_transfer_button(self):
        busy = self._transfer_worker is not None and self._transfer_worker.isRunning()
        count = len(self._selection)
        self.transfer_button.setText(
            _("Transfer selection ({count})", count=count) if count else _("Transfer selection")
        )
        self.transfer_button.setEnabled(bool(count) and self.current_device is not None and not busy)

    def _transfer_selection(self):
        device = self.current_device
        if not device or not self._selection:
            return
        selected = [card.story for key, (card, _listing, _item) in self._cards.items() if key in self._selection]
        for story in selected:
            self._cards[story.key][0].set_state("pending")

        self._run_transfer(InstallWorker(device["mount_point"], selected, self))

    def _run_transfer(self, worker):
        self._transfer_worker = worker
        worker.log.connect(self._append_log)
        worker.progress.connect(self._on_progress)
        worker.story_started.connect(self._on_story_started)
        worker.story_done.connect(self._on_story_done)
        worker.finished.connect(self._on_transfer_finished)
        self.progress.setVisible(True)
        self._update_transfer_button()
        self._start(worker)

    def _on_progress(self, label, current, total):
        self.progress.setMaximum(total or 0)
        self.progress.setValue(current)
        self.progress_label.setText(
            f"{self._current_title} — {label.lower()}" if self._current_title else label
        )

    def _on_story_started(self, key, title):
        self._current_title = title
        entry = self._cards.get(key)
        if entry:
            entry[0].set_state("working")

    def _on_story_done(self, key, success, message):
        entry = self._cards.get(key)
        if entry:
            entry[0].set_state("done" if success else "failed")
            if success:
                entry[0].set_checked(False)
        self._append_log(logging.INFO if success else logging.ERROR, message)

    def _on_transfer_finished(self):
        self._transfer_worker = None
        self._current_title = ""
        self.progress.setVisible(False)
        self.progress_label.setText(_("Transfer finished"))
        self.refresh_devices()
        self._update_transfer_button()

    # -- other actions ----------------------------------------------------

    def _add_store(self):
        answer = StoreDialog.ask(self)
        if answer is None:
            return
        config.add_store(*answer)
        self.refresh_catalog()

    def _choose_archives(self):
        paths, _filter = QFileDialog.getOpenFileNames(
            self, _("Choose stories"),
            filter=_("Stories (*.zip *.7z *.pk);;All files (*)"),
        )
        if paths:
            self._transfer_archives(paths)

    def _transfer_archives(self, paths):
        device = self.current_device
        if not device:
            QMessageBox.warning(self, "luniiStory", _("Plug a Lunii in before importing stories."))
            return
        self._run_transfer(ArchiveWorker(device["mount_point"], paths, self))

    def _remove_selected(self):
        device = self.current_device
        if not device:
            return
        short_uuids = [item.data(Qt.UserRole) for item in self.device_list.selectedItems()]
        short_uuids = [value for value in short_uuids if value]
        if not short_uuids:
            return
        confirmation = QMessageBox.question(
            self, "luniiStory",
            _n(len(short_uuids),
               "Remove {count} story from the Lunii?",
               "Remove {count} stories from the Lunii?"),
        )
        if confirmation != QMessageBox.Yes:
            return
        worker = RemoveWorker(device["mount_point"], short_uuids, self)
        worker.log.connect(self._append_log)
        worker.done.connect(self.refresh_devices)
        self._start(worker)

    def _append_log(self, level, message):
        if level <= logging.DEBUG:
            return
        self.log_view.appendPlainText(str(message))
        if level >= logging.ERROR:
            self.log_button.setChecked(True)

    # -- plumbing ---------------------------------------------------------

    def _start(self, worker):
        """Holds a reference to the thread for as long as it runs."""
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        worker.start()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self._transfer_archives(paths)

    def closeEvent(self, event):
        for worker in list(self._workers):
            if hasattr(worker, "abort"):
                worker.abort()
            if hasattr(worker, "stop"):
                worker.stop()
            worker.wait(3000)
        transfer.cleanup_tmp()
        super().closeEvent(event)
