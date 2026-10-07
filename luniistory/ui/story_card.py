"""Catalog row: thumbnail, title, badges and state."""

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QCheckBox, QFrame, QHBoxLayout, QLabel, QVBoxLayout

from luniistory.i18n import _

THUMB_SIZE = QSize(128, 96)
ROW_HEIGHT = 146
# Catalogue blurbs run long; a trimmed line keeps every row the same height, so
# the list stays scannable and never needs to scroll sideways.
DESCRIPTION_LIMIT = 110


def shorten(text, limit=DESCRIPTION_LIMIT):
    """One line, trimmed on a word boundary."""
    text = " ".join(str(text).split())
    if len(text) <= limit:
        return text
    return text[:limit].rsplit(" ", 1)[0] + "…"


def state_label(state):
    return {
        "audio-only": _("episode"),
        "installed": _("on the Lunii"),
        "downloaded": _("downloaded"),
        "pending": _("queued…"),
        "working": _("working…"),
        "done": _("transferred ✓"),
        "failed": _("failed ✗"),
    }.get(state, "")


class StoryCard(QFrame):
    toggled = Signal(str, bool)

    def __init__(self, story, parent=None):
        super().__init__(parent)
        self.story = story
        self.setObjectName("storyCard")

        self.checkbox = QCheckBox()
        self.checkbox.toggled.connect(lambda checked: self.toggled.emit(story.key, checked))
        if story.is_audio:
            self.checkbox.setToolTip(_(
                "A podcast episode carries no cover or spoken title, so one is "
                "built around it before the transfer."
            ))

        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(THUMB_SIZE)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setObjectName("thumbnail")
        self.thumbnail.setText("…")

        title = QLabel(f"{story.title}")
        title.setObjectName("cardTitle")
        title.setWordWrap(True)

        badges = []
        if story.is_new:
            badges.append(_("★ new"))
        elif story.is_updated:
            badges.append(_("↻ updated"))
        if story.is_awarded:
            badges.append(_("🏆 perfect"))

        subtitle = QLabel(" · ".join(filter(None, [
            _("ages {age} and up", age=story.age) if story.age else "",
            story.category,
            story.store_name,
            *badges,
        ])))
        subtitle.setObjectName("cardSubtitle")
        subtitle.setWordWrap(True)

        self.state = QLabel()
        self.state.setObjectName("cardState")
        self.state.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.state.setMinimumWidth(110)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        texts.addWidget(title)
        texts.addWidget(subtitle)
        if story.description:
            description = QLabel(shorten(story.description))
            description.setObjectName("cardDescription")
            description.setWordWrap(True)
            texts.addWidget(description)
        texts.addStretch(1)

        self.setFixedHeight(ROW_HEIGHT)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(12)
        layout.addWidget(self.checkbox, 0, Qt.AlignTop)
        layout.addWidget(self.thumbnail, 0, Qt.AlignTop)
        layout.addLayout(texts, 1)
        layout.addWidget(self.state, 0)

    def set_thumbnail(self, path):
        pixmap = QPixmap(str(path))
        if pixmap.isNull():
            return
        self.thumbnail.setPixmap(
            pixmap.scaled(THUMB_SIZE, Qt.KeepAspectRatio, Qt.SmoothTransformation)
        )
        self.thumbnail.setText("")

    def set_state(self, state):
        if self.story.is_audio:
            state = "audio-only"
        self.state.setText(state_label(state))
        self.setProperty("state", state)
        # Changing a property does not restyle the widget on its own.
        self.style().unpolish(self)
        self.style().polish(self)
        if state == "installed":
            self.checkbox.setChecked(False)

    def set_checked(self, checked):
        self.checkbox.setChecked(checked)
