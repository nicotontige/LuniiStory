"""Spoken titles for packs built from a bare audio file.

The Lunii announces each story when the wheel lands on it, so a pack needs an
audio for its cover. A podcast episode carries none, and the alternatives are
the host's text-to-speech or a short silence.
"""

import platform
import shutil
import subprocess
import tempfile
from pathlib import Path

# One frame of silent MPEG-1 Layer III: 44.1 kHz, mono, 128 kbps — exactly what
# the Lunii accepts, so a silent title needs neither FFMPEG nor a voice.
SILENT_FRAME = b"\xff\xfb\x90\xc0" + b"\x00" * 413
FRAMES_PER_SECOND = 38


def silence(seconds=1.0):
    """A valid MP3 of the given length, built without any external tool."""
    return SILENT_FRAME * max(1, int(FRAMES_PER_SECOND * seconds))


def engine():
    """Name of the usable text-to-speech command, or ``None``."""
    system = platform.system()
    if system == "Darwin" and shutil.which("say"):
        return "say"
    if system == "Linux" and shutil.which("espeak-ng"):
        return "espeak-ng"
    if system == "Windows":
        return "sapi"
    return None


def speak(text, language="fr"):
    """Renders ``text`` to audio bytes, or returns ``None``.

    The result is WAV or AIFF depending on the host, never MP3, so the import
    pipeline transcodes it — which is why this needs FFMPEG to be of any use.
    """
    name = engine()
    if not name or not text.strip():
        return None

    with tempfile.TemporaryDirectory() as work:
        target = Path(work) / "title.wav"
        try:
            if name == "say":
                voice = "Thomas" if language == "fr" else "Alex"
                subprocess.run(
                    ["say", "-v", voice, "--data-format=LEF32@44100", "-o", str(target), text],
                    check=True, capture_output=True, timeout=60,
                )
            elif name == "espeak-ng":
                subprocess.run(
                    ["espeak-ng", "-v", language, "-w", str(target), text],
                    check=True, capture_output=True, timeout=60,
                )
            else:
                script = (
                    "Add-Type -AssemblyName System.Speech; "
                    "$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
                    f"$s.SetOutputToWaveFile('{target}'); $s.Speak('{text}'); $s.Dispose()"
                )
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", script],
                    check=True, capture_output=True, timeout=60,
                )
        except (subprocess.SubprocessError, OSError):
            return None

        return target.read_bytes() if target.exists() else None
