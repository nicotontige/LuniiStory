"""What the local library accepts as a finished download."""

import pytest

from luniistory import library


class _Story:
    def __init__(self, is_audio=False):
        self.key = "abc123"
        self.title = "Arthur le hérisson"
        self.download = "https://example.org/arthur.mp3"
        self.story_uuid = ""
        self.version = 0
        self.store_name = "Nonno"
        self.age = 0
        self.is_audio = is_audio


def _session(chunks, announced):
    class Response:
        headers = {"Content-Length": str(announced)} if announced else {}

        def raise_for_status(self):
            pass

        def iter_content(self, chunk_size):
            return iter(chunks)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    return Session()


@pytest.fixture(autouse=True)
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setattr(library.config, "APP_DIR", tmp_path)
    monkeypatch.setattr(library.config, "CACHE_DIR", tmp_path / "cache")
    monkeypatch.setattr(library.config, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(library.config, "TMP_DIR", tmp_path / "tmp")
    return tmp_path


def test_a_short_download_is_refused(monkeypatch):
    """Nothing downstream can tell a truncated file from a broken one."""
    story = _Story(is_audio=True)
    monkeypatch.setattr(library.requests, "Session", lambda: _session([b"x" * 100], 500))

    with pytest.raises(ValueError, match="100 of 500"):
        library.download(story)

    # Nothing is kept, so the next attempt fetches it again.
    assert not library.pack_path(story).exists()
    assert story.key not in library.load_index()


def test_a_complete_audio_download_is_kept(monkeypatch):
    story = _Story(is_audio=True)
    monkeypatch.setattr(library.requests, "Session", lambda: _session([b"x" * 500], 500))

    path = library.download(story)
    assert path.exists()
    assert path.suffix == ".mp3"       # an episode is not an archive
    assert library.is_downloaded(story)


def test_a_server_that_announces_nothing_is_accepted(monkeypatch):
    story = _Story(is_audio=True)
    monkeypatch.setattr(library.requests, "Session", lambda: _session([b"x" * 500], None))
    assert library.download(story).exists()


def test_forgetting_clears_the_way_for_a_retry(monkeypatch):
    story = _Story(is_audio=True)
    monkeypatch.setattr(library.requests, "Session", lambda: _session([b"x" * 500], 500))
    library.download(story)

    library.forget(story)
    assert not library.pack_path(story).exists()
    assert not library.is_downloaded(story)
