"""Main window: the libraries on one side, the Lunii on the other."""

import logging
import unicodedata
from pathlib import Path

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QDesktopServices
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
    QSplitter,
    QTabBar,
    QTabWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from luniistory import __version__, config, eject, library, transfer, updates
from luniistory.i18n import _, _n

LOGGER = logging.getLogger("luniistory.ui")
from luniistory.ui.library_dialog import LibraryDialog
from luniistory.ui.settings_dialog import SettingsDialog
from luniistory.ui.story_card import ROW_HEIGHT, StoryCard
from luniistory.ui.workers import (
    ArchiveWorker,
    CatalogWorker,
    DeviceWorker,
    InstallWorker,
    RemoveWorker,
    ThumbnailWorker,
    UpdateWorker,
)


# Catalogues declare a minimum age from 2 to 10; three steps left most of that
# unreachable. The label names the child's age, not the story's, because the
# filter keeps stories suitable at that age rather than stories aimed above it.
AGE_CHOICES = (3, 4, 5, 6, 7, 8, 10)


def _age_filters():
    return [(_("Any age"), None)] + [
        (_("For a child of {age}", age=age), age) for age in AGE_CHOICES
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
        self._empty_states = []
        self._selection = set()
        self._devices = []
        self._workers = []
        self._transfer_worker = None
        # Whatever is currently touching the device, so nothing else starts.
        self._busy = None
        self._current_title = ""
        self._age_filters = _age_filters()

        # Set when the language changes: app.py then rebuilds the window.
        self.restart_requested = False

        self._build_ui()
        self.refresh_devices()
        self.refresh_catalog()
        self._check_for_update()

    # -- construction ----------------------------------------------------

    def _build_ui(self):
        # Left: what the Lunii holds. Right: what can go on it. The transfer
        # runs right to left, so the device stays in view while browsing.
        panels = QSplitter(Qt.Horizontal)
        panels.setObjectName("panels")
        panels.setChildrenCollapsible(False)
        panels.addWidget(self._build_device_panel())
        panels.addWidget(self._build_catalog_panel())
        panels.setStretchFactor(0, 4)
        panels.setStretchFactor(1, 6)
        panels.setSizes([420, 620])

        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_header())
        layout.addWidget(panels, 1)
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
        tagline = QLabel(_("Stories for the Lunii · version {version}", version=__version__))
        tagline.setObjectName("deviceStatus")
        title_box.addWidget(title)
        title_box.addWidget(tagline)

        # Hidden until there is something to say; nagging on every launch about
        # a release you have already seen is worse than not telling you.
        self.update_button = QPushButton()
        self.update_button.setObjectName("update")
        self.update_button.setVisible(False)
        self.update_button.clicked.connect(
            lambda: QDesktopServices.openUrl(updates.RELEASES_PAGE)
        )

        settings_button = QPushButton(_("Settings"))
        settings_button.clicked.connect(self._open_settings)

        layout.addLayout(title_box)
        layout.addStretch(1)
        layout.addWidget(self.update_button)
        layout.addWidget(settings_button)
        return header

    def _build_device_panel(self):
        panel = QFrame()
        panel.setObjectName("devicePanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(16, 14, 12, 14)
        layout.setSpacing(10)

        self.device_title = QLabel(_("On the Lunii"))
        self.device_title.setObjectName("panelTitle")

        self.device_combo = QComboBox()
        self.device_combo.currentIndexChanged.connect(self._on_device_changed)

        find_button = QPushButton(_("Search"))
        find_button.clicked.connect(self.refresh_devices)

        picker = QHBoxLayout()
        picker.setSpacing(8)
        picker.addWidget(self.device_combo, 1)
        picker.addWidget(find_button)

        self.device_status = QLabel(_("Looking for a Lunii…"))
        self.device_status.setObjectName("panelSubtitle")
        self.device_status.setWordWrap(True)

        self.device_list = QListWidget()
        # Tick boxes rather than click-selection, to match the catalogue side
        # and to survive the list being rebuilt after every transfer.
        self.device_list.setSelectionMode(QListWidget.NoSelection)
        self.device_list.itemChanged.connect(self._update_remove_button)

        self.remove_button = QPushButton(_("Remove from the Lunii"))
        self.remove_button.setObjectName("destructive")
        self.remove_button.setEnabled(False)
        self.remove_button.clicked.connect(self._remove_selected)

        self.eject_button = QPushButton(_("Eject"))
        self.eject_button.setEnabled(False)
        self.eject_button.clicked.connect(self._eject_device)

        buttons = QHBoxLayout()
        buttons.setSpacing(8)
        buttons.addWidget(self.remove_button, 1)
        buttons.addWidget(self.eject_button)

        layout.addWidget(self.device_title)
        layout.addLayout(picker)
        layout.addWidget(self.device_status)
        layout.addWidget(self.device_list, 1)
        layout.addLayout(buttons)
        return panel

    def _build_catalog_panel(self):
        panel = QFrame()
        panel.setObjectName("catalogPanel")
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(12, 14, 16, 14)
        layout.setSpacing(10)

        self.catalog_title = QLabel(_("Available to transfer"))
        self.catalog_title.setObjectName("panelTitle")

        self.search = QLineEdit()
        self.search.setPlaceholderText(_("Search for a story…"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._apply_filters)

        self.age_combo = QComboBox()
        for label, _age in self._age_filters:
            self.age_combo.addItem(label)
        self.age_combo.currentIndexChanged.connect(self._apply_filters)
        _fit_to_contents(self.age_combo)

        filters = QHBoxLayout()
        filters.setSpacing(8)
        filters.addWidget(self.search, 1)
        filters.addWidget(self.age_combo)

        reload_button = QPushButton(_("Refresh"))
        reload_button.clicked.connect(self.refresh_catalog)

        add_library = QPushButton(_("Manage libraries"))
        add_library.clicked.connect(self._add_library)

        import_button = QPushButton(_("Import a file…"))
        import_button.clicked.connect(self._choose_archives)

        actions = QHBoxLayout()
        actions.setSpacing(8)
        actions.addWidget(reload_button)
        actions.addWidget(add_library)
        actions.addWidget(import_button)
        actions.addStretch(1)

        self.tabs = QTabWidget()

        layout.addWidget(self.catalog_title)
        layout.addLayout(filters)
        layout.addLayout(actions)
        layout.addWidget(self.tabs, 1)

        self.transfer_button = QPushButton(_("Transfer selection"))
        self.transfer_button.setObjectName("primary")
        self.transfer_button.setEnabled(False)
        self.transfer_button.clicked.connect(self._transfer_selection)
        layout.addWidget(self.transfer_button)
        return panel

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

        top.addWidget(self.progress_label, 1)
        top.addWidget(self.progress)
        top.addWidget(self.log_button)

        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setMaximumHeight(160)
        self.log_view.setVisible(False)

        layout.addLayout(top)
        layout.addWidget(self.log_view)
        return footer

    def _check_for_update(self):
        worker = UpdateWorker(self)
        worker.available.connect(self._on_update_available)
        self._start(worker)

    def _on_update_available(self, version):
        self.update_button.setText(_("Version {version} is out", version=version))
        self.update_button.setToolTip(_("Opens the release page in your browser"))
        self.update_button.setVisible(True)

    # -- language --------------------------------------------------------

    def _open_settings(self):
        if SettingsDialog.ask(self):
            # The window is rebuilt rather than retranslated in place: Qt would
            # need every string re-applied by hand, and this cannot drift.
            self.restart_requested = True
            self.close()

    # -- devices ---------------------------------------------------------

    def refresh_devices(self):
        self.device_status.setText(_("Looking for a Lunii…"))
        worker = DeviceWorker(self)
        worker.found.connect(self._on_devices_found)
        self._start(worker)

    def _on_devices_found(self, devices, attached):
        self._devices = devices
        self.device_combo.blockSignals(True)
        self.device_combo.clear()
        for device in devices:
            self.device_combo.addItem(Path(device["mount_point"]).name or device["mount_point"])
        self.device_combo.blockSignals(False)

        if not devices:
            # Plugged in but mounting nothing is the common case, and it has a
            # one-step fix the old message gave no hint of.
            self.device_status.setText(_(
                "A Lunii is connected but has not opened its storage. Switch it on."
            ) if attached else _("No Lunii connected"))
            self.device_combo.addItem("—")
        else:
            self.device_status.setText(devices[0]["label"])

        self._refresh_device_list()
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
        self._refresh_device_list()
        self._refresh_states()
        self._update_transfer_button()

    def _refresh_device_list(self):
        self.device_list.clear()
        device = self.current_device
        if not device:
            self.device_title.setText(_("On the Lunii"))
            placeholder = QListWidgetItem(_("Plug a Lunii in to see what it holds."))
            placeholder.setFlags(Qt.NoItemFlags)
            self.device_list.addItem(placeholder)
            self._update_remove_button()
            return
        for story in device["stories"]:
            item = QListWidgetItem(f"{story['name']}" + ("  🌙" if story["night_mode"] else ""))
            item.setData(Qt.UserRole, story["short_uuid"])
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            self.device_list.addItem(item)
        self.device_title.setText(_n(
            len(device["stories"]), "{count} story on the Lunii", "{count} stories on the Lunii"
        ))
        self._update_remove_button()

    def _checked_device_stories(self):
        return [
            item.data(Qt.UserRole)
            for item in (self.device_list.item(row) for row in range(self.device_list.count()))
            if item.checkState() == Qt.Checked and item.data(Qt.UserRole)
        ]

    def _on_removal_finished(self, removed, total):
        self._busy = None
        self._current_title = ""
        self.progress.setVisible(False)
        self.progress_label.setText(
            _n(removed, "{count} story removed", "{count} stories removed")
            if removed == total
            else _("{removed} of {total} removed", removed=removed, total=total)
        )
        self.refresh_devices()
        self._update_transfer_button()

    def _update_remove_button(self):
        connected = self.current_device is not None and self._busy is None
        checked = self._checked_device_stories()
        self.remove_button.setText(
            _("Remove from the Lunii ({count})", count=len(checked)) if checked
            else _("Remove from the Lunii")
        )
        self.remove_button.setEnabled(bool(checked) and connected)
        self.eject_button.setEnabled(connected)

    def _eject_device(self, confirm=False):
        """Unmounts the device so it can be unplugged without losing writes."""
        device = self.current_device
        if not device:
            return True
        try:
            eject.eject(device["mount_point"])
        except Exception as error:
            self._append_log(logging.ERROR, _("Could not eject the Lunii: {error}", error=error))
            if confirm:
                return QMessageBox.question(
                    self, "luniiStory",
                    _("The Lunii would not eject: {error}\n\nQuit anyway?", error=error),
                ) == QMessageBox.Yes
            QMessageBox.warning(self, "luniiStory", _("The Lunii would not eject: {error}", error=error))
            return False
        self._append_log(logging.INFO, _("The Lunii can be unplugged."))
        self.refresh_devices()
        return True

    # -- catalog ---------------------------------------------------------

    def refresh_catalog(self):
        self.progress_label.setText(_("Loading libraries…"))
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
        self._empty_states = []
        self._selection.clear()

        self.tabs.clear()
        removable = {store["url"]: store.get("deletable", True) for store in config.load_stores()}
        urls = {store["name"]: store["url"] for store in config.load_stores()}

        for store_name in dict.fromkeys(story.store_name for story in catalog):
            stories = [story for story in catalog if story.store_name == store_name]
            index = self.tabs.addTab(self._build_store_tab(stories), f"{store_name} ({len(stories)})")
            self.tabs.tabBar().setTabData(index, urls.get(store_name))
            if removable.get(urls.get(store_name), False):
                self._add_close_button(index)

        self.progress_label.setText(_(
            "{stories} across {stores}",
            stories=_n(len(catalog), "{count} story", "{count} stories"),
            stores=_n(self.tabs.count(), "{count} library", "{count} libraries"),
        ))

        self._refresh_states()
        self._apply_filters()

        thumbnails = ThumbnailWorker(catalog, self)
        thumbnails.ready.connect(self._on_thumbnail)
        self._start(thumbnails)

    def _build_store_tab(self, stories):
        listing = QListWidget()
        listing.setSelectionMode(QListWidget.NoSelection)
        listing.setSpacing(4)
        listing.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        for story in stories:
            card = StoryCard(story)
            card.toggled.connect(self._on_card_toggled)
            item = QListWidgetItem(listing)
            item.setSizeHint(QSize(0, ROW_HEIGHT))
            listing.addItem(item)
            listing.setItemWidget(item, card)
            self._cards[story.key] = (card, listing, item)

        # A filter that matches nothing used to leave a blank panel, with no way
        # to tell an empty store from a hidden one.
        empty = QLabel()
        empty.setObjectName("emptyState")
        empty.setAlignment(Qt.AlignCenter)
        empty.setWordWrap(True)
        empty.setVisible(False)

        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(listing, 1)
        layout.addWidget(empty, 1)
        self._empty_states.append((listing, empty))
        return tab

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
        visible = 0
        for card, _listing, item in self._cards.values():
            story = card.story
            matches = not needle or needle in _normalize(f"{story.title} {story.description} {story.category}")
            if max_age is not None and story.age and story.age > max_age:
                matches = False
            item.setHidden(not matches)
            visible += bool(matches)

        self._refresh_empty_states(needle, max_age)
        if self._catalog:
            self.progress_label.setText(
                _n(visible, "{count} story shown", "{count} stories shown")
                if visible < len(self._catalog)
                else _n(visible, "{count} story", "{count} stories")
            )

    def _refresh_empty_states(self, needle, max_age):
        """Explains an empty tab rather than leaving it blank."""
        if needle:
            message = _("No story here matches “{search}”.", search=self.search.text().strip())
        elif max_age is not None:
            message = _("No story here is meant for a child of {age}.", age=max_age)
        else:
            message = _("This library is empty.")

        for listing, label in self._empty_states:
            hidden = all(listing.item(row).isHidden() for row in range(listing.count()))
            label.setText(message)
            label.setVisible(hidden)
            listing.setVisible(not hidden)

    # -- selection and transfer -------------------------------------------

    def _on_card_toggled(self, key, checked):
        if checked:
            self._selection.add(key)
        else:
            self._selection.discard(key)
        self._update_transfer_button()

    def _update_transfer_button(self):
        busy = self._busy is not None or (
            self._transfer_worker is not None and self._transfer_worker.isRunning()
        )
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

    def _add_close_button(self, index):
        """Puts a dismiss button on a store tab, always on the right.

        Qt's own closable tabs follow the platform, and macOS puts the button
        on the left, where it reads as belonging to the tab before it.
        """
        button = QToolButton()
        button.setObjectName("tabClose")
        button.setText("×")
        button.setCursor(Qt.ArrowCursor)
        button.setToolTip(_("Remove this library"))
        button.clicked.connect(lambda: self._remove_store_at(button))
        self.tabs.tabBar().setTabButton(index, QTabBar.RightSide, button)

    def _remove_store_at(self, button):
        """Finds the tab the button belongs to; indices shift as tabs close."""
        bar = self.tabs.tabBar()
        for index in range(bar.count()):
            if bar.tabButton(index, QTabBar.RightSide) is button:
                self._remove_store(index)
                return

    def _remove_store(self, index):
        url = self.tabs.tabBar().tabData(index)
        name = self.tabs.tabText(index)
        if not url:
            return
        confirmation = QMessageBox.question(
            self, "luniiStory",
            _("Remove the library “{name}”? Its stories stay on the Lunii.", name=name),
        )
        if confirmation != QMessageBox.Yes:
            return
        config.remove_store(url)
        self.refresh_catalog()

    def _add_library(self):
        """One way in: pick from the published list, or paste an address."""
        stores = config.load_stores()
        known = {store["url"] for store in stores}
        protected = {store["url"] for store in stores if not store.get("deletable", True)}

        added, removed = LibraryDialog.ask(known, self)
        for name, url in added:
            config.add_store(name, url)
        for url in removed:
            # The libraries shipped with the application stay put.
            if url not in protected:
                config.remove_store(url)
        if added or removed:
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
        short_uuids = self._checked_device_stories()
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
        names = {
            story["short_uuid"]: story["name"] for story in device["stories"]
        }
        worker = RemoveWorker(
            device["mount_point"],
            [(uuid, names.get(uuid, uuid)) for uuid in short_uuids],
            self,
        )
        worker.log.connect(self._append_log)
        worker.progress.connect(self._on_progress)
        worker.story_started.connect(self._on_story_started)
        worker.done.connect(self._on_removal_finished)

        self._busy = worker
        self.progress.setVisible(True)
        self._update_remove_button()
        self._update_transfer_button()
        self._start(worker)

    def _append_log(self, level, message):
        # Everything is written down, including what the panel does not show:
        # the engine's debug chatter is where a device problem is explained.
        LOGGER.log(level, "%s", message)
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
        # Offer to unmount rather than let the device be yanked mid-write, which
        # is how a Lunii ends up with half-written stories.
        if self.current_device is not None and not self.restart_requested:
            answer = QMessageBox.question(
                self, "luniiStory",
                _("Eject the Lunii before quitting?"),
                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                QMessageBox.Yes,
            )
            if answer == QMessageBox.Cancel:
                event.ignore()
                return
            if answer == QMessageBox.Yes and not self._eject_device(confirm=True):
                event.ignore()
                return

        for worker in list(self._workers):
            if hasattr(worker, "abort"):
                worker.abort()
            if hasattr(worker, "stop"):
                worker.stop()
            worker.wait(3000)
        transfer.cleanup_tmp()
        super().closeEvent(event)
