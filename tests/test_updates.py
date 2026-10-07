"""Telling you a newer release is out, without ever getting in the way."""

import json
import time

import pytest

from luniistory import updates


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(updates.config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(updates.config, "APP_DIR", tmp_path)
    monkeypatch.setattr(updates.config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(updates.config, "TMP_DIR", tmp_path / "tmp")
    monkeypatch.setattr(updates.config, "SETTINGS_FILE", tmp_path / "settings.json")
    return tmp_path


def test_versions_compare_by_number_not_by_text():
    # "0.10" sorts below "0.9" as text, and above it as a version.
    assert updates.is_newer("0.10.0", "0.9.0") is True
    assert updates.is_newer("0.9.0", "0.10.0") is False
    assert updates.is_newer("1.0.0", "0.99.99") is True


def test_the_same_version_is_not_newer():
    assert updates.is_newer("0.1.1", "0.1.1") is False


def test_a_tag_with_a_v_prefix_still_compares(monkeypatch):
    assert updates.version_tuple("v0.2.0") == (0, 2, 0)


def test_nothing_to_say_when_up_to_date(monkeypatch):
    monkeypatch.setattr(updates, "latest_version", lambda **kwargs: "0.1.0")
    monkeypatch.setattr(updates, "__version__", "0.1.0")
    assert updates.available_update() is None


def test_a_newer_release_is_reported(monkeypatch):
    monkeypatch.setattr(updates, "latest_version", lambda **kwargs: "9.9.9")
    assert updates.available_update() == "9.9.9"


def test_the_check_can_be_turned_off(monkeypatch):
    monkeypatch.setattr(updates, "latest_version", lambda **kwargs: "9.9.9")
    updates.set_enabled(False)
    assert updates.available_update() is None
    updates.set_enabled(True)
    assert updates.available_update() == "9.9.9"


def test_a_fresh_cache_answers_without_asking(isolated_home, monkeypatch):
    updates.config.ensure_dirs()
    updates._cache_path().write_text(
        json.dumps({"version": "2.0.0", "fetched_at": time.time()}), "utf-8"
    )

    def refuse(*args, **kwargs):
        raise AssertionError("the network should not be touched")

    monkeypatch.setattr(updates.requests, "Session", refuse)
    assert updates.latest_version() == "2.0.0"


def test_a_stale_cache_is_ignored(isolated_home, monkeypatch):
    updates.config.ensure_dirs()
    updates._cache_path().write_text(
        json.dumps({"version": "2.0.0", "fetched_at": time.time() - updates.CACHE_SECONDS - 1}),
        "utf-8",
    )
    monkeypatch.setattr(updates, "_cached", lambda: None)
    monkeypatch.setattr(updates.requests, "Session", lambda: _session("v3.0.0"))
    assert updates.latest_version() == "3.0.0"


def test_being_offline_is_not_an_error(isolated_home, monkeypatch):
    def explode():
        raise OSError("no network")

    monkeypatch.setattr(updates.requests, "Session", explode)
    # A launch must never be held up by this.
    assert updates.latest_version(use_cache=False) is None


def _session(tag):
    class Response:
        def raise_for_status(self):
            pass

        def json(self):
            return {"tag_name": tag}

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    return Session()
