"""The contract that matters: what the converter produces must be read back by
the Lunii.QT import engine, since that engine is what writes to the device."""

import json
import zipfile

from luniistory.convert import telmi
from luniistory.lunii_api import lunii_stories
from tests.conftest import STORY_UUID

NI_HEADER_SIZE = 512
NODE_SIZE = 44


def _studio_story(telmi_pack, tmp_path):
    archive_path = telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip")
    with zipfile.ZipFile(archive_path) as archive:
        return lunii_stories.StudioStory(json.loads(archive.read("story.json")))


def test_story_is_readable_by_lunii_qt(telmi_pack, tmp_path):
    story = _studio_story(telmi_pack, tmp_path)

    assert story.compatible
    assert str(story.uuid) == STORY_UUID
    assert story.short_uuid == STORY_UUID.replace("-", "")[24:].upper()
    assert story.title == "Pack de test"


def test_index_files_are_consistent(telmi_pack, tmp_path):
    story = _studio_story(telmi_pack, tmp_path)

    # 3 images (title + 2) and 4 sounds (title + 3), each listed once.
    assert len(story.ri) == 3
    assert len(story.si) == 4
    assert story.get_ri_data().count(b"000\\") == 3
    assert story.get_si_data().count(b"000\\") == 4

    node_data = story.get_ni_data()
    assert len(node_data) == NI_HEADER_SIZE + 4 * NODE_SIZE

    # li flattens every action's options: a0(1) + a1(2) + a2(1).
    assert len(story.li) == 4
    assert len(story.get_li_data()) == 16


def test_start_node_points_at_the_first_option(telmi_pack, tmp_path):
    story = _studio_story(telmi_pack, tmp_path)
    node = story.get_ni_data()[NI_HEADER_SIZE:NI_HEADER_SIZE + NODE_SIZE]

    image_index = int.from_bytes(node[0:4], "little", signed=True)
    sound_index = int.from_bytes(node[4:8], "little", signed=True)
    ok_list, ok_count, ok_option = (
        int.from_bytes(node[offset:offset + 4], "little", signed=True) for offset in (8, 12, 16)
    )

    assert (image_index, sound_index) == (0, 0)  # title.png / title.mp3 come first
    assert (ok_list, ok_count, ok_option) == (0, 1, 0)  # a0, a single option
    assert node[20:32] == b"\xFF" * 12  # no home transition

    # And the option a0 points at is indeed the first stage node, s0.
    assert story.li[0] == 1
