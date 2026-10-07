"""Wrapping a single audio file into something the Lunii can play."""

import json
import zipfile

import pytest

from luniistory.convert import audio_pack, speech
from luniistory.convert.telmi import TelmiFormatError
from luniistory.lunii_api import lunii_stories
from tests.conftest import MP3_SILENCE, PNG_1PX

NI_HEADER_SIZE = 512
NODE_SIZE = 44


@pytest.fixture
def episode(tmp_path):
    path = tmp_path / "episode.mp3"
    path.write_bytes(MP3_SILENCE * 5)
    return path


@pytest.fixture
def cover(tmp_path):
    path = tmp_path / "cover.png"
    path.write_bytes(PNG_1PX)
    return path


def _story(archive_path):
    with zipfile.ZipFile(archive_path) as archive:
        return json.loads(archive.read("story.json")), archive.namelist()


def test_pack_has_a_cover_and_the_episode(episode, cover, tmp_path):
    story, names = _story(audio_pack.build("Doudou", episode, cover, tmp_path / "out.zip"))

    assert len(story["stageNodes"]) == 2
    first, second = story["stageNodes"]
    assert first["squareOne"] is True
    assert first["image"] == second["image"]          # the artwork serves both
    assert first["audio"] != second["audio"]          # the title is not the episode
    assert first["okTransition"] == {"actionNode": "a0", "optionIndex": 0}
    assert story["actionNodes"][0]["options"] == [second["uuid"]]
    assert "thumbnail.png" in names


def test_episode_controls_let_it_play_and_pause(episode, cover, tmp_path):
    story, _names = _story(audio_pack.build("Doudou", episode, cover, tmp_path / "out.zip"))
    controls = story["stageNodes"][1]["controlSettings"]

    assert controls["autoplay"] is True
    assert controls["pause"] is True
    assert controls["home"] is True
    assert controls["wheel"] is False


def test_lunii_qt_accepts_the_pack(episode, cover, tmp_path):
    story_json, _names = _story(audio_pack.build("Doudou", episode, cover, tmp_path / "out.zip"))
    story = lunii_stories.StudioStory(story_json)

    assert story.compatible
    assert len(story.ri) == 1       # one image, shared
    assert len(story.si) == 2       # spoken title + episode
    assert story.li == [1]          # OK on the cover leads to the episode
    assert len(story.get_ni_data()) == NI_HEADER_SIZE + 2 * NODE_SIZE


def test_a_silent_title_needs_no_transcoding(episode, cover, tmp_path):
    """Without FFMPEG the cover goes silent, which keeps the pack importable."""
    archive = audio_pack.build(
        "Doudou", episode, cover, tmp_path / "out.zip", spoken_title=speech.silence()
    )
    _story_json, names = _story(archive)
    assert any(name.endswith(".mp3") for name in names)

    from pkg.api.convert_audio import transcoding_required

    assert transcoding_required("title.mp3", speech.silence()) is False


def test_uuid_is_stable_for_the_same_episode(episode, cover, tmp_path):
    first, _ = _story(audio_pack.build("Doudou", episode, cover, tmp_path / "a.zip",
                                       uuid=audio_pack.story_uuid("abc")))
    second, _ = _story(audio_pack.build("Doudou", episode, cover, tmp_path / "b.zip",
                                        uuid=audio_pack.story_uuid("abc")))
    # Re-transferring an episode must land on the same story, not a duplicate.
    assert first["stageNodes"][0]["uuid"] == second["stageNodes"][0]["uuid"]
    assert audio_pack.story_uuid("abc") != audio_pack.story_uuid("def")


def test_a_pack_without_artwork_still_builds(episode, tmp_path):
    story, names = _story(audio_pack.build("Doudou", episode, None, tmp_path / "out.zip"))
    assert story["stageNodes"][0]["image"] is None
    assert "thumbnail.png" not in names


def test_missing_audio_is_reported(cover, tmp_path):
    with pytest.raises(TelmiFormatError):
        audio_pack.build("Doudou", tmp_path / "gone.mp3", cover, tmp_path / "out.zip")


def test_silence_is_a_real_mono_mp3():
    from io import BytesIO

    from mutagen.mp3 import MP3

    info = MP3(BytesIO(speech.silence(2.0))).info
    assert info.sample_rate == 44100
    assert info.mode == 3            # MONO
    assert 1.8 < info.length < 2.2
