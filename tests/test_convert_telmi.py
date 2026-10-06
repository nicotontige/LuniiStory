import json
import zipfile

import pytest

from luniistory.convert import telmi
from tests.conftest import STORY_UUID


def _story_json(archive_path):
    with zipfile.ZipFile(archive_path) as archive:
        return json.loads(archive.read("story.json")), archive.namelist()


def test_cover_node_rebuilt_from_metadata(telmi_pack, tmp_path):
    story, _ = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    cover = story["stageNodes"][0]

    # Le noeud de couverture porte l'UUID du pack : c'est lui que Lunii.QT
    # retient comme identifiant de l'histoire.
    assert cover["uuid"] == STORY_UUID
    assert cover["squareOne"] is True
    assert cover["okTransition"] == {"actionNode": "a0", "optionIndex": 0}
    assert cover["homeTransition"] is None
    assert cover["controlSettings"] == telmi.COVER_CONTROLS
    assert story["title"] == "Pack de test"


def test_stages_and_actions_are_preserved(telmi_pack, tmp_path):
    story, _ = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))

    assert len(story["stageNodes"]) == 4  # couverture + s0, s1, s2
    assert {action["id"] for action in story["actionNodes"]} == {"a0", "a1", "a2"}

    by_name = {node["name"]: node for node in story["stageNodes"]}
    assert by_name["s0"]["okTransition"] == {"actionNode": "a1", "optionIndex": 0}
    assert by_name["s0"]["homeTransition"] is None
    assert by_name["s1"]["controlSettings"]["wheel"] is True
    assert by_name["s2"]["okTransition"] is None

    options = {action["id"]: action["options"] for action in story["actionNodes"]}
    assert options["a1"] == [by_name["s1"]["uuid"], by_name["s2"]["uuid"]]


def test_assets_are_renamed(telmi_pack, tmp_path):
    story, names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))

    assets = [name for name in names if name.startswith("assets/")]
    assert len(assets) == 7  # title.png + title.mp3 + 2 images + 3 audios
    assert "thumbnail.png" in names

    for node in story["stageNodes"]:
        for media in (node["image"], node["audio"]):
            if media is None:
                continue
            # 8 hex characters, as in the original STUdio packs.
            stem = media.rsplit(".", 1)[0]
            assert len(stem) == 8 and all(char in "0123456789ABCDEF" for char in stem)
            assert f"assets/{media}" in names


def test_conversion_is_deterministic(telmi_pack, tmp_path):
    first, _ = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "a.zip"))
    second, _ = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "b.zip"))
    assert first == second


def test_zip_entry_point_finds_the_pack_root(telmi_zip, tmp_path):
    story, _ = _story_json(
        telmi.zip_to_studio_zip(telmi_zip, tmp_path / "out.zip", tmp_path / "work")
    )
    assert story["stageNodes"][0]["uuid"] == STORY_UUID
    assert not (tmp_path / "work").exists()  # the working folder is cleaned up


def test_dangling_transition_is_dropped(telmi_pack, tmp_path):
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s1"]["ok"] = {"action": "a99", "index": 0}
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _ = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    by_name = {node["name"]: node for node in story["stageNodes"]}
    assert by_name["s1"]["okTransition"] is None


def test_missing_title_audio_is_reported(telmi_pack, tmp_path):
    (telmi_pack / "title.mp3").unlink()
    with pytest.raises(telmi.TelmiFormatError):
        telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip")


def test_not_a_telmi_pack(tmp_path):
    (tmp_path / "vide").mkdir()
    with pytest.raises(telmi.TelmiFormatError):
        telmi.find_pack_root(tmp_path / "vide")


def test_shared_media_is_stored_once(telmi_pack, tmp_path):
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s2"]["audio"] = nodes["stages"]["s1"]["audio"]
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    by_name = {node["name"]: node for node in story["stageNodes"]}

    assert by_name["s1"]["audio"] == by_name["s2"]["audio"]
    assert len([name for name in names if name.startswith("assets/")]) == 6
