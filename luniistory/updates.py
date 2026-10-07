"""Telling you when a newer release is out.

It asks GitHub for the latest release and compares it with the running version.
Nothing is downloaded or installed: the binaries are unsigned, and an
application that replaces itself from the network is a far bigger promise than
this one makes. It points at the release page and leaves the choice there.
"""

import json
import re
import time

import requests

from luniistory import __version__, config
from luniistory.stores import TIMEOUT, USER_AGENT

REPOSITORY = "nicotontige/LuniiStory"
LATEST_URL = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
RELEASES_PAGE = f"https://github.com/{REPOSITORY}/releases/latest"
NEW_ISSUE_PAGE = f"https://github.com/{REPOSITORY}/issues/new"

CACHE_NAME = "latest-release.json"
CACHE_SECONDS = 24 * 3600
SETTING = "check_updates"


def version_tuple(version):
    """``"0.10.2"`` → ``(0, 10, 2)``, so 0.10 sorts above 0.9."""
    return tuple(int(part) for part in re.findall(r"\d+", str(version))) or (0,)


def is_newer(candidate, current=None):
    """Whether ``candidate`` is a newer version than the one running.

    The running version is read at call time rather than bound as a default,
    which keeps the comparison honest under test.
    """
    return version_tuple(candidate) > version_tuple(current or __version__)


def enabled():
    """Checking is opt-out: it is one request to GitHub on launch."""
    return config.load_settings().get(SETTING, True)


def set_enabled(value):
    config.save_setting(SETTING, bool(value))


def _cache_path():
    config.ensure_dirs()
    return config.CACHE_DIR / CACHE_NAME


def _cached():
    path = _cache_path()
    try:
        payload = json.loads(path.read_text("utf-8"))
    except (OSError, ValueError):
        return None
    if time.time() - payload.get("fetched_at", 0) > CACHE_SECONDS:
        return None
    return payload.get("version")


def latest_version(session=None, use_cache=True):
    """Version of the newest published release, or ``None``.

    Answers from a day-old cache when it can, so launching the application
    repeatedly does not mean asking GitHub every time.
    """
    if use_cache:
        cached = _cached()
        if cached:
            return cached

    try:
        session = session or requests.Session()
        response = session.get(
            LATEST_URL,
            headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        tag = (response.json().get("tag_name") or "").lstrip("vV")
    except Exception:
        # Offline, rate limited, no release yet: never a reason to interrupt.
        return None

    if not tag:
        return None

    try:
        _cache_path().write_text(
            json.dumps({"version": tag, "fetched_at": time.time()}), "utf-8"
        )
    except OSError:
        pass
    return tag


def available_update(session=None):
    """The newer version on offer, or ``None`` when there is nothing to say."""
    if not enabled():
        return None
    latest = latest_version(session=session)
    return latest if latest and is_newer(latest) else None
