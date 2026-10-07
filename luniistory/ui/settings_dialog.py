"""Everything that was scattered, in one place.

The language lived in the header, emptying the downloads was command line only,
and turning the update check off meant editing a JSON file by hand.
"""

import subprocess
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
)

from luniistory import config, i18n, library, transfer, updates
from luniistory.i18n import _, _n


def reveal(path):
    """Opens the folder in the system's file manager."""
    opener = {"darwin": ["open"], "win32": ["explorer"]}.get(sys.platform, ["xdg-open"])
    try:
        subprocess.Popen(opener + [str(path)])
    except OSError:
        pass


class SettingsDialog(QDialog):
    """Returns whether the language changed, since that rebuilds the window."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Settings"))
        self.setModal(True)
        self.setMinimumWidth(520)

        self._language_before = i18n.current_language()

        self.language = QComboBox()
        for code in i18n.available_languages():
            self.language.addItem(i18n.language_name(code), code)
        self.language.setCurrentIndex(i18n.available_languages().index(self._language_before))

        self.check_updates = QCheckBox(_("Look for a new version on launch"))
        self.check_updates.setChecked(updates.enabled())
        self.check_updates.setToolTip(_("Asks GitHub once a day, and never installs anything"))

        self.downloads = QLabel()
        empty_button = QPushButton(_("Empty"))
        empty_button.clicked.connect(self._empty_downloads)
        downloads_row = QHBoxLayout()
        downloads_row.setSpacing(8)
        downloads_row.addWidget(self.downloads, 1)
        downloads_row.addWidget(empty_button)

        folder_button = QPushButton(_("Open the folder"))
        folder_button.clicked.connect(lambda: reveal(config.APP_DIR))
        folder_row = QHBoxLayout()
        folder_row.setSpacing(8)
        folder_row.addWidget(QLabel(str(config.APP_DIR)), 1)
        folder_row.addWidget(folder_button)

        self.audio = QLabel(
            _("Bundled, no FFMPEG needed") if not transfer.ffmpeg_available()
            else _("FFMPEG found, it will be used for the rarer formats")
        )
        self.audio.setObjectName("cardSubtitle")

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.setSpacing(12)
        form.addRow(_("Language"), self.language)
        form.addRow(_("Updates"), self.check_updates)
        form.addRow(_("Downloaded packs"), downloads_row)
        form.addRow(_("Audio conversion"), self.audio)
        form.addRow(_("Files"), folder_row)

        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.button(QDialogButtonBox.Close).setText(_("Close"))
        buttons.rejected.connect(self.accept)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(14)
        layout.addLayout(form)
        layout.addWidget(buttons)

        self._refresh_downloads()

    def _refresh_downloads(self):
        count = len(library.load_index())
        self.downloads.setText(_(
            "{packs}, {size:.0f} MB",
            packs=_n(count, "{count} pack", "{count} packs"),
            size=library.downloaded_size() / 1e6,
        ))

    def _empty_downloads(self):
        library.clear()
        self._refresh_downloads()

    @property
    def language_changed(self):
        return self.language.currentData() != self._language_before

    def accept(self):
        """Settings are written on the way out, not on every keystroke."""
        updates.set_enabled(self.check_updates.isChecked())
        code = self.language.currentData()
        if code != self._language_before:
            config.save_setting("language", code)
            i18n.set_language(code)
        super().accept()

    @classmethod
    def ask(cls, parent=None):
        dialog = cls(parent)
        dialog.exec()
        return dialog.language_changed
