"""Builds a playable pack around a single audio file.

A podcast episode is just an MP3. The Lunii needs a pack: a cover node whose
image it shows and whose audio it speaks when the wheel lands on the story, then
the episode itself. This assembles both into a STUdio archive the regular import
path can swallow.
"""

import json
import zipfile
from pathlib import Path
from uuid import UUID, uuid5

from luniistory.convert import speech
from luniistory.convert.telmi import COVER_CONTROLS, TelmiFormatError, _asset_name
from luniistory.i18n import _

NAMESPACE = UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8")

# The episode plays on its own, can be paused, and the home button goes back to
# the menu — the same controls Telmi gives a straight-through audio stage.
EPISODE_CONTROLS = {"wheel": False, "ok": False, "home": True, "pause": True, "autoplay": True}


def _is_mp3(data):
    return data[:2] == b"\xff\xfb" or data[:3] == b"ID3"


def spoken_or_silent(title):
    """The cover audio: a voice when one can be used, silence otherwise.

    Every host voice renders to WAV, and only FFMPEG turns that into the MP3 the
    Lunii accepts. Without it a spoken title would make the whole pack
    unimportable, so the cover goes silent instead of the transfer failing.
    """
    from luniistory.lunii_api import which_ffmpeg

    if which_ffmpeg():
        spoken = speech.speak(title)
        if spoken:
            return spoken
    return speech.silence()


def story_uuid(seed):
    """Stable identifier, so re-transferring an episode replaces rather than duplicates."""
    return uuid5(NAMESPACE, f"luniistory:audio:{seed}")


def build(title, audio, cover, output_zip, description="", spoken_title=None, uuid=None):
    """Writes the STUdio archive for one audio file.

    ``audio`` and ``cover`` are paths. ``spoken_title`` is the audio announcing
    the story; when it is ``None`` a voice is attempted, and failing that the
    cover stays silent rather than blocking the transfer.
    """
    audio = Path(audio)
    if not audio.is_file():
        raise TelmiFormatError(_("Audio file missing: {path}", path=audio))

    uuid = uuid or story_uuid(title)
    episode_uuid = str(uuid5(uuid, "episode"))

    if spoken_title is None:
        spoken_title = spoken_or_silent(title)
    title_extension = ".mp3" if _is_mp3(spoken_title) else ".wav"

    taken = set()
    cover_name = _asset_name("cover", ".png", taken) if cover else None
    title_name = _asset_name("title", title_extension, taken)
    episode_name = _asset_name("episode", audio.suffix.lower() or ".mp3", taken)

    story = {
        "format": "v1",
        "version": 1,
        "title": title,
        "description": description,
        "nightModeAvailable": False,
        "stageNodes": [
            {
                "uuid": str(uuid),
                "type": "cover",
                "name": title,
                "position": {"x": 0, "y": 0},
                "image": cover_name,
                "audio": title_name,
                "okTransition": {"actionNode": "a0", "optionIndex": 0},
                "homeTransition": None,
                "controlSettings": dict(COVER_CONTROLS),
                "squareOne": True,
            },
            {
                "uuid": episode_uuid,
                "type": "stage",
                "name": "episode",
                "position": {"x": 0, "y": 0},
                "image": cover_name,
                "audio": episode_name,
                "okTransition": None,
                "homeTransition": None,
                "controlSettings": dict(EPISODE_CONTROLS),
            },
        ],
        "actionNodes": [
            {"id": "a0", "name": "a0", "position": {"x": 0, "y": 0}, "options": [episode_uuid]},
        ],
    }

    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("story.json", json.dumps(story, ensure_ascii=False))
        archive.writestr(f"assets/{title_name}", spoken_title)
        archive.write(audio, f"assets/{episode_name}")
        if cover:
            archive.write(cover, f"assets/{cover_name}")
            archive.write(cover, "thumbnail.png")

    return output_zip
