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

    assert len(story["stageNodes"]) == 4  # cover + s0, s1, s2
    # a0, a1, a2 from the pack, plus the home target the converter adds for s2,
    # whose home button is lit with nothing behind it.
    assert {action["id"] for action in story["actionNodes"]} == {
        "a0", "a1", "a2", telmi.COVER_ACTION_ID,
    }

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
    # The unknown action goes, and since the button stays lit it falls back to
    # the cover rather than pointing at something that is not there.
    assert "a99" not in {action["id"] for action in story["actionNodes"]}
    assert by_name["s1"]["okTransition"]["actionNode"] == telmi.COVER_ACTION_ID


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


def test_stereo_audio_is_folded_to_mono(telmi_pack, tmp_path):
    """Catalogue packs are not all mono, and the device only plays mono."""
    import lameenc
    from luniistory.convert import audio

    encoder = lameenc.Encoder()
    encoder.set_bit_rate(128)
    encoder.set_in_sample_rate(44100)
    encoder.set_channels(2)
    encoder.set_quality(5)
    encoder.silence()
    stereo = bytes(encoder.encode(b"\x00\x00" * 44100 * 2) + encoder.flush())
    (telmi_pack / "audios" / "0.mp3").write_bytes(stereo)
    assert not audio.is_lunii_ready(stereo)

    archive = telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip")
    with zipfile.ZipFile(archive) as handle:
        tracks = [name for name in handle.namelist() if name.endswith(".mp3")]
        assert tracks
        for name in tracks:
            assert audio.is_lunii_ready(handle.read(name), name)


def test_an_enabled_button_always_leads_somewhere(telmi_pack, tmp_path):
    """Telmi OS answers dead button presses itself; a Lunii follows the
    transition it was promised and stops with an SD card error."""
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s2"]["control"] = {"wheel": False, "ok": True, "home": True,
                                        "pause": False, "autoplay": False}
    nodes["stages"]["s2"]["ok"] = None      # OK lit, with nowhere to go
    nodes["stages"]["s2"]["home"] = None    # same for home
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    by_name = {node["name"]: node for node in story["stageNodes"]}
    s2 = by_name["s2"]

    # Both buttons lead to the cover, which is the way out of a pack on the
    # device: Telmi writes "ok: null" on the stages that end a story.
    exit_action = next(a for a in story["actionNodes"] if a["id"] == telmi.COVER_ACTION_ID)
    assert exit_action["options"] == [story["stageNodes"][0]["uuid"]]
    for field in ("ok", "home"):
        assert s2["controlSettings"][field] is True
        assert s2[field + "Transition"] == {"actionNode": telmi.COVER_ACTION_ID, "optionIndex": 0}


def test_only_one_exit_is_added(telmi_pack, tmp_path):
    """A pack that already leads back to the cover keeps its own route."""
    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    cover = story["stageNodes"][0]["uuid"]

    leading_back = [action for action in story["actionNodes"] if cover in action["options"]]
    assert len(leading_back) == 1


def test_a_story_ending_leaves_the_pack(telmi_pack, tmp_path):
    """Telmi marks an ending with "ok: null" while leaving the button lit.

    Turning the button off there would strand a child on the last stage of the
    story with nothing to press.
    """
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s2"]["ok"] = None
    nodes["stages"]["s2"]["control"] = {"wheel": False, "ok": True, "home": True,
                                        "pause": False, "autoplay": True}
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    ending = next(node for node in story["stageNodes"] if node["name"] == "s2")
    assert ending["controlSettings"]["ok"] is True
    assert ending["okTransition"]["actionNode"] == telmi.COVER_ACTION_ID


def test_the_indexitem_spelling_is_recognised(telmi_pack, tmp_path):
    """A couple of packs spell the option indexItem rather than index, and it
    means something different: a lookup by counter, not a fixed choice."""
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s0"]["ok"] = {"action": "a1", "indexItem": 1}
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    by_name = {node["name"]: node for node in story["stageNodes"]}
    assert by_name["s0"]["okTransition"]["actionNode"] == "a1"
    assert by_name["s0"]["okTransition"]["optionIndex"] == telmi.RANDOM_OPTION


def test_a_random_option_is_kept(telmi_pack, tmp_path):
    """STUdio uses -1 to mean "pick one at random"; it must survive."""
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s0"]["ok"] = {"action": "a1", "index": -1}
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    by_name = {node["name"]: node for node in story["stageNodes"]}
    assert by_name["s0"]["okTransition"]["optionIndex"] == -1


def _with_ok(telmi_pack, transition, control=None):
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s0"]["ok"] = transition
    nodes["stages"]["s0"]["control"] = control or {
        "wheel": False, "ok": True, "home": False, "pause": False, "autoplay": False,
    }
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")
    return nodes


def _wheel_of(story, name):
    return next(n for n in story["stageNodes"] if n["name"] == name)["controlSettings"]["wheel"]


def test_the_options_get_the_wheel(telmi_pack, tmp_path):
    """The wheel belongs to the options, not to the stage that asks.

    The child lands on one option, turns to hear the others, presses OK on the
    one they want. Putting it on the asking stage instead leaves it dead.
    """
    _with_ok(telmi_pack, {"action": "a1", "index": 0})      # a1 offers s1 and s2
    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))

    assert _wheel_of(story, "s1") is True
    assert _wheel_of(story, "s2") is True
    assert _wheel_of(story, "s0") is False                  # the one that asked


def test_an_option_waits_for_the_child(telmi_pack, tmp_path):
    """Turning takes time, which autoplay does not leave."""
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s1"]["control"]["autoplay"] = True     # s1 is an option of a1
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    controls = next(n for n in story["stageNodes"] if n["name"] == "s1")["controlSettings"]
    assert controls["wheel"] is True
    assert controls["autoplay"] is False


def test_the_only_way_on_is_not_a_choice(telmi_pack, tmp_path):
    """a0 leads to s0 alone, so s0 has nothing to turn between."""
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    for name in ("a1", "a2"):
        nodes["actions"][name] = [{"stage": "s2"}]          # no action offers a choice
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    # s1 declares a wheel of its own in the fixture; nothing else gains one.
    assert _wheel_of(story, "s0") is False
    assert _wheel_of(story, "s2") is False


def test_an_option_of_a_random_pick_still_gets_the_wheel(telmi_pack, tmp_path):
    """Random chooses where you land; the wheel is how you leave that spot.

    The quiz packs do exactly this: a random option to open on, browsable from
    there.
    """
    _with_ok(telmi_pack, {"action": "a1", "index": -1})
    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    assert _wheel_of(story, "s1") is True


def test_the_inventory_marker_never_reaches_the_archive(telmi_pack, tmp_path):
    _with_ok(telmi_pack, {"action": "a1", "indexItem": 1})
    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    for node in story["stageNodes"]:
        for field in ("okTransition", "homeTransition"):
            assert telmi.INVENTORY_MARKER not in (node[field] or {})


def test_the_cover_keeps_the_wheel(telmi_pack, tmp_path):
    """The cover node governs the wheel in the device's story menu.

    Read off a genuine story on a Lunii: its cover has the wheel on. A pack
    that returns there with it off leaves the menu unable to browse, and only
    a power cycle brings it back.
    """
    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    assert story["stageNodes"][0]["controlSettings"]["wheel"] is True


def test_an_inventory_lookup_becomes_a_random_pick(telmi_pack, tmp_path):
    """Telmi serves the option a counter points at; a Lunii keeps no counters,
    so it would serve the first one forever — the same quiz question every
    time."""
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s0"]["ok"] = {"action": "a1", "indexItem": 0}   # a1 offers two
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    assert next(n for n in story["stageNodes"] if n["name"] == "s0")["okTransition"] == {
        "actionNode": "a1", "optionIndex": telmi.RANDOM_OPTION,
    }


def test_a_single_option_lookup_is_left_alone(telmi_pack, tmp_path):
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s0"]["ok"] = {"action": "a2", "indexItem": 0}   # a2 offers one
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    assert next(n for n in story["stageNodes"] if n["name"] == "s0")["okTransition"]["optionIndex"] == 0


def test_home_always_has_a_way_to_the_menu(telmi_pack, tmp_path):
    """Some packs route home into a prompt that loops back to the first stage:
    Telmi OS takes you out, so the graph never needs to. A Lunii does not."""
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    for name, stage in nodes["stages"].items():
        stage["ok"] = {"action": "a0", "index": 0}      # nothing dangles
        stage["home"] = {"action": "a0", "index": 0}    # home never exits
        stage["control"] = {"wheel": False, "ok": True, "home": True,
                            "pause": False, "autoplay": False}
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    cover = story["stageNodes"][0]["uuid"]
    assert any(cover in action["options"] for action in story["actionNodes"])
    for node in story["stageNodes"][1:]:
        assert node["homeTransition"]["actionNode"] == telmi.COVER_ACTION_ID


def test_an_ending_leaves_on_its_own(telmi_pack, tmp_path):
    """A stage that ends the pack is a closing line, not a question.

    Waiting for OK there means pressing it twice to leave: once to confirm,
    once to dismiss the confirmation.
    """
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    # s0 is reached from a0, which offers it alone, so it is not browsable.
    nodes["stages"]["s0"]["ok"] = None
    nodes["stages"]["s0"]["control"] = {"wheel": False, "ok": True, "home": True,
                                        "pause": False, "autoplay": False}
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    ending = next(node for node in story["stageNodes"] if node["name"] == "s0")
    assert ending["okTransition"]["actionNode"] == telmi.COVER_ACTION_ID
    assert ending["controlSettings"]["autoplay"] is True


def test_a_browsable_ending_stays_browsable(telmi_pack, tmp_path):
    """A stage can be both an ending and one of several options.

    It must stay turnable: the child browses to it and presses OK, which leaves
    the story. Letting it autoplay would carry them out before they chose it.
    """
    nodes = json.loads((telmi_pack / "nodes.json").read_text("utf-8"))
    nodes["stages"]["s2"]["ok"] = None                      # s2 is an option of a1
    nodes["stages"]["s2"]["control"] = {"wheel": False, "ok": True, "home": True,
                                        "pause": False, "autoplay": False}
    (telmi_pack / "nodes.json").write_text(json.dumps(nodes), "utf-8")

    story, _names = _story_json(telmi.to_studio_zip(telmi_pack, tmp_path / "out.zip"))
    node = next(n for n in story["stageNodes"] if n["name"] == "s2")
    assert node["controlSettings"]["wheel"] is True
    assert node["controlSettings"]["autoplay"] is False
    assert node["okTransition"]["actionNode"] == telmi.COVER_ACTION_ID
