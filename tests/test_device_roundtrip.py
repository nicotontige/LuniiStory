"""Full chain: store archive → conversion → written to the device."""

from luniistory import transfer
from tests.conftest import STORY_UUID

SHORT_UUID = STORY_UUID.replace("-", "")[24:].upper()


def test_install_writes_a_playable_story(telmi_zip, fake_lunii):
    device = transfer.open_device(str(fake_lunii))
    assert device.device_version == 2
    assert len(device.stories) == 0

    transfer.install_archive(device, telmi_zip)

    story_dir = fake_lunii / ".content" / SHORT_UUID
    assert story_dir.is_dir()
    # The five index files the firmware expects.
    assert {path.name for path in story_dir.iterdir() if path.is_file()} == {"bt", "li", "ni", "ri", "si"}
    assert len(list((story_dir / "rf" / "000").iterdir())) == 3
    assert len(list((story_dir / "sf" / "000").iterdir())) == 4

    # The UUID is written to the pack index the Lunii reads at startup.
    assert bytes.fromhex(STORY_UUID.replace("-", "")) in (fake_lunii / ".pi").read_bytes()


def test_installed_story_is_listed_then_removed(telmi_zip, fake_lunii):
    device = transfer.open_device(str(fake_lunii))
    transfer.install_archive(device, telmi_zip)

    reopened = transfer.open_device(str(fake_lunii))
    listed = transfer.installed_stories(reopened)
    assert [story["short_uuid"] for story in listed] == [SHORT_UUID]

    transfer.remove_story(reopened, SHORT_UUID)
    assert not (fake_lunii / ".content" / SHORT_UUID).exists()
    assert transfer.installed_stories(transfer.open_device(str(fake_lunii))) == []


def test_images_are_converted_to_lunii_bitmaps(telmi_zip, fake_lunii):
    device = transfer.open_device(str(fake_lunii))
    transfer.install_archive(device, telmi_zip)

    image = next((fake_lunii / ".content" / SHORT_UUID / "rf" / "000").iterdir())

    # On a v2 the first 512 bytes are ciphered with the generic key.
    from pkg.api.constants import lunii_generic_key

    plain = device.decipher(image.read_bytes(), lunii_generic_key)
    assert plain[:2] == b"BM"
    width = int.from_bytes(plain[18:22], "little")
    height = int.from_bytes(plain[22:26], "little")
    compression = int.from_bytes(plain[30:34], "little")
    assert (width, height) == (320, 240)
    assert compression == 2  # BI_RLE4


def test_a_studio_archive_is_passed_through_unconverted(telmi_zip, fake_lunii, tmp_path):
    from luniistory.convert import telmi

    studio_zip = telmi.zip_to_studio_zip(telmi_zip, tmp_path / "studio.zip", tmp_path / "work")
    prepared, temporary = transfer.prepare_archive(studio_zip)

    assert prepared == studio_zip
    assert temporary is False


def test_progress_reports_both_phases(telmi_zip, fake_lunii):
    """Conversion and transfer go through the same three-argument callback."""
    from luniistory.i18n import _

    events = []
    device = transfer.open_device(str(fake_lunii))
    transfer.install_archive(device, telmi_zip, on_progress=lambda *args: events.append(args))

    assert all(len(event) == 3 for event in events)
    assert {event[0] for event in events} == {_("Converting"), _("Transferring")}
    assert all(isinstance(event[1], int) and isinstance(event[2], int) for event in events)
