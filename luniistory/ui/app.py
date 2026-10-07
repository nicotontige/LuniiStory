"""Graphical interface entry point."""

import sys
from pathlib import Path

from PySide6.QtCore import QLocale, QTranslator
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from luniistory import config, i18n, logs
from luniistory.lunii_api import ENGINE_LOCALES_DIR
from luniistory.ui.main_window import MainWindow

STYLE_FILE = Path(__file__).parent / "style.qss"
ICON_FILE = Path(__file__).parent / "icons" / "icon.png"

# Lunii.QT writes its log messages in English and ships its own catalogs; we
# load the matching one so engine messages follow the chosen language.
ENGINE_LOCALES = {"fr": "fr_FR"}


def _install_engine_translator(app):
    name = ENGINE_LOCALES.get(i18n.current_language())
    if not name:
        return None
    translator = QTranslator(app)
    if translator.load(str(ENGINE_LOCALES_DIR / f"{name}.qm")):
        app.installTranslator(translator)
        return translator
    return None


def run():
    config.ensure_dirs()
    logs.setup()
    i18n.set_language(i18n.detect_language())
    logs.log_environment({"language": i18n.current_language(), "interface": "window"})

    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("luniiStory")
    if ICON_FILE.exists():
        app.setWindowIcon(QIcon(str(ICON_FILE)))
    if STYLE_FILE.exists():
        app.setStyleSheet(STYLE_FILE.read_text("utf-8"))

    code = 0
    while True:
        QLocale.setDefault(QLocale(i18n.current_language()))
        translator = _install_engine_translator(app)

        window = MainWindow()
        window.show()
        code = app.exec()

        if translator is not None:
            app.removeTranslator(translator)
        # Switching language closes the window and rebuilds it translated.
        if not window.restart_requested:
            return code


if __name__ == "__main__":
    sys.exit(run())
