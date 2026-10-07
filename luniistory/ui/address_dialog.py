"""Asking for a library by its address, when it is not in the published list."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
)

from luniistory.i18n import _

ACCEPTED_SCHEMES = ("http://", "https://")


class AddressDialog(QDialog):
    """Asks for a library's name and address in one go.

    The accept button stays disabled until both fields hold something usable,
    which spares the user a round trip through an error message.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(_("Add by address"))
        self.setModal(True)
        self.setMinimumWidth(460)

        self.name_field = QLineEdit()
        self.name_field.setPlaceholderText(_("My story library"))

        self.url_field = QLineEdit()
        self.url_field.setPlaceholderText("https://example.org/catalog.json")

        hint = QLabel(_(
            "A library is any address serving a story catalog in JSON, or a "
            "podcast RSS feed. Its stories then show up in their own tab."
        ))
        hint.setObjectName("dialogHint")
        hint.setWordWrap(True)

        self.error = QLabel()
        self.error.setObjectName("dialogError")
        self.error.setWordWrap(True)
        self.error.setVisible(False)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        form.addRow(_("Name"), self.name_field)
        form.addRow(_("Catalog address"), self.url_field)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Ok).setText(_("Add"))
        self.buttons.button(QDialogButtonBox.Cancel).setText(_("Cancel"))
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)
        layout.addWidget(hint)
        layout.addLayout(form)
        layout.addWidget(self.error)
        layout.addWidget(self.buttons)

        self.name_field.textChanged.connect(self._validate)
        self.url_field.textChanged.connect(self._validate)
        self._validate()

    @property
    def library_name(self):
        return self.name_field.text().strip()

    @property
    def library_url(self):
        return self.url_field.text().strip()

    def _validate(self):
        url = self.library_url
        problem = ""
        if url and not url.lower().startswith(ACCEPTED_SCHEMES):
            problem = _("The address must start with http:// or https://")

        self.error.setText(problem)
        self.error.setVisible(bool(problem))
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(
            bool(self.library_name) and bool(url) and not problem
        )

    @classmethod
    def ask(cls, parent=None):
        """Returns ``(name, url)``, or ``None`` if the user backed out."""
        dialog = cls(parent)
        if dialog.exec() != QDialog.Accepted:
            return None
        return dialog.store_name, dialog.store_url
