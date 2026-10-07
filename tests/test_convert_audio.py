"""Turning any audio into the one format the Lunii plays, without FFMPEG."""

from io import BytesIO

import lameenc
import pytest
from mutagen.mp3 import MP3

from luniistory.convert import audio, speech


def _stereo_mp3(seconds=1.0, sample_rate=44100):
    """A silent stereo MP3, which is what podcasts actually ship."""
    frames = int(sample_rate * seconds)
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(sample_rate)
    encoder.set_channels(2)
    encoder.set_quality(5)
    encoder.silence()
    pcm = b"\x00\x00" * frames * 2       # 16-bit, two channels
    return bytes(encoder.encode(pcm) + encoder.flush())


def test_stereo_becomes_mono():
    converted = audio.to_lunii_mp3(_stereo_mp3())
    info = MP3(BytesIO(converted)).info

    assert info.mode == 3                # MONO
    assert info.sample_rate == 44100
    assert audio.is_lunii_ready(converted)


def test_a_lower_sample_rate_is_lifted():
    info = MP3(BytesIO(audio.to_lunii_mp3(_stereo_mp3(sample_rate=22050)))).info
    assert info.sample_rate == 44100
    assert info.mode == 3


def test_audio_that_already_fits_is_untouched():
    """Re-encoding a file the device accepts would only lose quality."""
    ready = speech.silence(1.0)
    assert audio.to_lunii_mp3(ready) is ready


def test_a_wav_becomes_mp3():
    """Host voices render WAV; the pack needs MP3."""
    import struct
    import wave

    buffer = BytesIO()
    with wave.open(buffer, "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(22050)
        handle.writeframes(struct.pack("<h", 0) * 22050 * 2)

    converted = audio.to_lunii_mp3(buffer.getvalue(), "title.wav")
    info = MP3(BytesIO(converted)).info
    assert info.mode == 3
    assert info.sample_rate == 44100


def test_unreadable_bytes_are_not_called_ready():
    assert audio.is_lunii_ready(b"not audio at all") is False


def test_unreadable_audio_says_what_to_do():
    """miniaudio answers "failed to decode data", which tells nobody anything."""
    with pytest.raises(audio.AudioError) as failure:
        audio.to_lunii_mp3(b"not audio at all" * 200, "episode.mp3")

    message = str(failure.value)
    assert "episode.mp3" in message
    assert "incomplete download" in message
