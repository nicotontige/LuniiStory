"""Folds audio into the one format the Lunii plays.

The device only accepts mono 44.1 kHz MP3. Podcast episodes ship joint stereo
and the host voices render WAV, so both need converting. FFMPEG would do it, but
pulling in an 80 MB binary to downmix a track is out of proportion: decoding
through miniaudio and re-encoding through LAME costs half a megabyte and ships
as ordinary wheels on every platform we release for.
"""

import lameenc
import miniaudio

from luniistory.i18n import _

SAMPLE_RATE = 44100
BIT_RATE = 128
QUALITY = 2  # LAME scale, 0 best and 9 fastest; 2 is the usual high setting


class AudioError(Exception):
    """The bytes could not be read as audio."""


def is_lunii_ready(data, filename="audio.mp3"):
    """True when the device would take the bytes as they are."""
    # Through lunii_api, which is what puts the engine on the import path; a
    # bare "from pkg..." only works once something else has imported it.
    from luniistory.lunii_api import transcoding_required

    try:
        return not transcoding_required(filename, data)
    except Exception:
        return False


def to_lunii_mp3(data, filename="audio.mp3"):
    """Returns mono 44.1 kHz MP3 bytes, re-encoding only when it is needed.

    Audio that already fits is passed straight through: re-encoding a file that
    is fine would only lose quality.
    """
    if is_lunii_ready(data, filename):
        return data

    try:
        decoded = miniaudio.decode(
            data,
            output_format=miniaudio.SampleFormat.SIGNED16,
            nchannels=1,
            sample_rate=SAMPLE_RATE,
        )
    except Exception as error:
        # miniaudio says "failed to decode data", which tells nobody anything.
        raise AudioError(_(
            "{name} could not be read as audio ({size} KB). It is probably an "
            "incomplete download; removing it and transferring again should fix it.",
            name=filename, size=len(data) // 1024,
        )) from error

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(BIT_RATE)
    encoder.set_in_sample_rate(SAMPLE_RATE)
    encoder.set_channels(1)
    encoder.set_quality(QUALITY)
    encoder.silence()
    return bytes(encoder.encode(decoded.samples.tobytes()) + encoder.flush())
