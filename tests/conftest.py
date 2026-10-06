import json
import zipfile

import pytest

STORY_UUID = "d781e1bd-2946-4b2e-b450-d993d8bd184f"

# A minimal but complete pack: an intro that chains on its own, then a choice
# between two endings. Enough to exercise transitions, multiple options and media.
NODES = {
    "startAction": {"action": "a0", "index": 0},
    "stages": {
        "s0": {
            "image": None,
            "audio": "0.mp3",
            "ok": {"action": "a1", "index": 0},
            "home": None,
            "control": {"wheel": False, "ok": False, "home": False, "pause": False, "autoplay": True},
        },
        "s1": {
            "image": "0.png",
            "audio": "1.mp3",
            "ok": {"action": "a2", "index": 0},
            "home": {"action": "a0", "index": 0},
            "control": {"wheel": True, "ok": True, "home": True, "pause": False, "autoplay": False},
        },
        "s2": {
            "image": "1.png",
            "audio": "2.mp3",
            "ok": None,
            "home": None,
            "control": {"wheel": False, "ok": False, "home": True, "pause": True, "autoplay": True},
        },
    },
    "actions": {
        "a0": [{"stage": "s0"}],
        "a1": [{"stage": "s1"}, {"stage": "s2"}],
        "a2": [{"stage": "s2"}],
    },
}

METADATA = {
    "title": "Pack de test",
    "uuid": STORY_UUID,
    "image": "cover.png",
    "version": 0,
    "category": "Test",
    "description": "A pack built for the tests.",
    "age": 5,
}

PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6300010000050001" "0d0a2db40000000049454e44ae426082"
)
# Ten silent MPEG-1 Layer III frames: 44.1 kHz mono 128 kbps, exactly what the
# Lunii accepts without going through FFMPEG.
MP3_FRAME = b"\xff\xfb\x90\xc0" + b"\x00" * 413
MP3_SILENCE = MP3_FRAME * 10


@pytest.fixture
def telmi_pack(tmp_path):
    """Telmi pack unpacked on disk."""
    root = tmp_path / "pack"
    (root / "images").mkdir(parents=True)
    (root / "audios").mkdir(parents=True)

    (root / "metadata.json").write_text(json.dumps(METADATA), "utf-8")
    (root / "nodes.json").write_text(json.dumps(NODES), "utf-8")
    (root / "title.png").write_bytes(PNG_1PX)
    (root / "cover.png").write_bytes(PNG_1PX)
    (root / "title.mp3").write_bytes(MP3_SILENCE)
    for index in range(2):
        (root / "images" / f"{index}.png").write_bytes(PNG_1PX)
    for index in range(3):
        (root / "audios" / f"{index}.mp3").write_bytes(MP3_SILENCE)
    return root


@pytest.fixture
def telmi_zip(telmi_pack, tmp_path):
    """The same pack, as a store archive."""
    archive_path = tmp_path / "pack.zip"
    with zipfile.ZipFile(archive_path, "w") as archive:
        for path in sorted(telmi_pack.rglob("*")):
            if path.is_file():
                archive.write(path, f"Pack de test_05_{STORY_UUID}/{path.relative_to(telmi_pack)}")
    return archive_path


@pytest.fixture
def fake_lunii(tmp_path):
    """Layout of a blank Lunii v2, enough for the import engine.

    The ``.md`` file carries the metadata version, the firmware, the serial
    number, the VID/PID pair identifying the hardware, and the ciphered device
    key from offset 0x100 on.
    """
    mount_point = tmp_path / "LUNII"
    (mount_point / ".content").mkdir(parents=True)

    metadata = bytearray(512)
    metadata[0:2] = (2).to_bytes(2, "little")
    metadata[6:8] = (2).to_bytes(2, "little")
    metadata[8:10] = (22).to_bytes(2, "little")
    metadata[10:18] = bytes.fromhex("0011223344556677")
    metadata[18:20] = (0x0483).to_bytes(2, "little")   # FAH_V2_V3_USB_VID_PID
    metadata[20:22] = (0xA341).to_bytes(2, "little")
    metadata[0x100:0x200] = bytes(range(256))
    (mount_point / ".md").write_bytes(bytes(metadata))
    return mount_point
