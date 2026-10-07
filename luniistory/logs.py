"""Where the application writes down what it did.

A parent who hits a failed transfer has nothing useful to send unless it was
written to a file at the time. Everything lands in one, including the engine's
own diagnostics and the stack traces the window never shows.
"""

import logging
import logging.handlers
import platform
import sys

from luniistory import __version__, config

LOG_DIR_NAME = "logs"
LOG_FILE_NAME = "luniistory.log"
MAX_BYTES = 2 * 1024 * 1024
BACKUPS = 3

FILE_FORMAT = "%(asctime)s %(levelname)-7s %(name)-22s %(message)s"
CONSOLE_FORMAT = "%(message)s"

_configured = False


def log_dir():
    return config.APP_DIR / LOG_DIR_NAME


def log_file():
    return log_dir() / LOG_FILE_NAME


def setup(verbose=False, console=True):
    """Sends everything to a rotating file, and the gist to the console.

    The file keeps DEBUG because that is the level that explains a failure
    after the fact; the console stays readable.
    """
    global _configured
    if _configured:
        return log_file()

    config.ensure_dirs()
    log_dir().mkdir(parents=True, exist_ok=True)

    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    handler = logging.handlers.RotatingFileHandler(
        log_file(), maxBytes=MAX_BYTES, backupCount=BACKUPS, encoding="utf-8"
    )
    handler.setLevel(logging.DEBUG)
    handler.setFormatter(logging.Formatter(FILE_FORMAT))
    root.addHandler(handler)

    if console:
        stream = logging.StreamHandler(sys.stderr)
        stream.setLevel(logging.DEBUG if verbose else logging.WARNING)
        stream.setFormatter(logging.Formatter(CONSOLE_FORMAT))
        root.addHandler(stream)

    # Chatty third parties, muted in the file as well: a transfer makes dozens
    # of requests and their headers drown everything worth reading.
    for noisy in ("urllib3", "requests", "PIL"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _configured = True
    return log_file()


def log_environment(extra=None):
    """The context every report needs, written once at startup."""
    logger = logging.getLogger("luniistory")
    logger.info("=" * 60)
    logger.info("luniiStory %s starting", __version__)
    logger.info(
        "%s %s (%s), Python %s",
        platform.system(), platform.release(), platform.machine(),
        platform.python_version(),
    )
    logger.info("frozen: %s | home: %s", bool(getattr(sys, "frozen", False)), config.APP_DIR)

    try:
        from luniistory.lunii_api import which_ffmpeg

        logger.info("ffmpeg: %s", which_ffmpeg() or "not installed (not needed)")
    except Exception:
        logger.warning("Lunii.QT engine unavailable", exc_info=True)

    for key, value in (extra or {}).items():
        logger.info("%s: %s", key, value)


def describe_device(device):
    """Writes down what was found on the bus, which a device report needs."""
    logger = logging.getLogger("luniistory.device")
    logger.info(
        "device at %s: version %s, firmware %s.%s.%s, serial %s, %d story(ies)",
        device.mount_point, device.device_version,
        device.fw_vers_major, device.fw_vers_minor, device.fw_vers_subminor,
        device.snu_str, len(device.stories),
    )
    logger.debug(
        "keys — device: %s, story: %s",
        "present" if device.device_key else "absent",
        "present" if device.story_key else "absent",
    )


def recent(lines=200):
    """The tail of the log, for showing without opening a file manager."""
    try:
        return log_file().read_text("utf-8", errors="replace").splitlines()[-lines:]
    except OSError:
        return []
