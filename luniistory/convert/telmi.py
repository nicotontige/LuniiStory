"""Conversion of a Telmi pack into a STUdio archive.

Telmi Sync builds its packs by unfolding a STUdio pack: its converter
(``ConvertFolderSTUdio.js``) strips the first stage node — the cover — into
``metadata.json`` + ``title.mp3`` + ``startAction``, then renames stages,
actions and media to ``s0``, ``a0``, ``0.mp3``…

We walk that path backwards: the cover node is rebuilt and the stages are given
back UUIDs, which yields a STUdio ``story.json`` that Lunii.QT imports as is.
"""

import hashlib
import json
import shutil
import zipfile
from pathlib import Path
from uuid import UUID, uuid5

from luniistory.convert import audio
from luniistory.i18n import _

# Control settings of a Lunii cover node, read off a genuine story on a device:
# the wheel turns between stories, OK starts the one in front of you, and
# nothing chains on its own. The wheel matters more than it looks — it is the
# cover node that governs the wheel in the story menu, so a pack that arrives
# there with it switched off leaves the device unable to browse until it is
# turned off and on again.
COVER_CONTROLS = {"wheel": True, "ok": True, "home": False, "pause": False, "autoplay": False}

IMAGE_EXTS = (".png", ".bmp", ".jpg", ".jpeg", ".gif", ".webp")
AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".flac", ".m4a", ".aac")


class TelmiFormatError(Exception):
    """The given folder is not a usable Telmi pack."""


def find_pack_root(path):
    """Pack root: the folder holding ``metadata.json`` and ``nodes.json``."""
    path = Path(path)
    if (path / "metadata.json").is_file() and (path / "nodes.json").is_file():
        return path
    for candidate in sorted(path.rglob("metadata.json")):
        if (candidate.parent / "nodes.json").is_file():
            return candidate.parent
    raise TelmiFormatError(_("No Telmi pack (metadata.json + nodes.json) in {path}", path=path))


def extract_pack(zip_path, dest_dir):
    """Unpacks a store archive and returns the Telmi pack root."""
    dest_dir = Path(dest_dir)
    dest_dir.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        for member in archive.infolist():
            # An entry name may point outside the target folder; refuse it.
            target = (dest_dir / member.filename).resolve()
            if not str(target).startswith(str(dest_dir.resolve())):
                raise TelmiFormatError(_("Suspicious path in archive: {name}", name=member.filename))
        archive.extractall(dest_dir)
    return find_pack_root(dest_dir)


def read_pack(pack_dir):
    """Loads a pack's ``metadata.json`` and ``nodes.json``."""
    pack_dir = Path(pack_dir)
    metadata = json.loads((pack_dir / "metadata.json").read_text("utf-8"))
    nodes = json.loads((pack_dir / "nodes.json").read_text("utf-8"))
    if "stages" not in nodes or "actions" not in nodes:
        raise TelmiFormatError(_("Incomplete nodes.json in {path}", path=pack_dir))
    return metadata, nodes


def _story_uuid(metadata, pack_dir):
    raw = metadata.get("uuid")
    if raw:
        try:
            return UUID(str(raw))
        except ValueError:
            pass
    # Pack without a UUID (hand-made import, RSS feed): derive a stable one from
    # the title so two transfers do not create two stories.
    seed = str(metadata.get("title") or Path(pack_dir).name)
    return uuid5(UUID("6ba7b810-9dad-11d1-80b4-00c04fd430c8"), f"luniistory:{seed}")


def _asset_name(source_name, extension, taken):
    """STUdio asset name: 8 hex characters, like the original packs use."""
    digest = hashlib.sha1(source_name.encode("utf-8")).hexdigest().upper()
    for offset in range(0, 32):
        name = digest[offset:offset + 8]
        if len(name) == 8 and name not in taken:
            taken.add(name)
            return name + extension
    raise TelmiFormatError(_("Cannot name asset {name}", name=source_name))


def _find_media(pack_dir, subdir, name, exts):
    """Locates a media file, the declared extension not always being right."""
    if not name:
        return None
    direct = pack_dir / subdir / name
    if direct.is_file():
        return direct
    stem = Path(name).stem
    for ext in exts:
        candidate = pack_dir / subdir / (stem + ext)
        if candidate.is_file():
            return candidate
    return None


def build_story_json(metadata, nodes, pack_dir):
    """Builds the STUdio ``story.json`` and the table of assets to copy.

    Returns ``(story_json, assets)`` where ``assets`` maps the file name expected
    under ``assets/`` to its source path in the Telmi pack.
    """
    pack_dir = Path(pack_dir)
    story_uuid = _story_uuid(metadata, pack_dir)
    stages = nodes["stages"]
    actions = nodes["actions"]

    # Stage identifiers are deterministic, so converting the same pack twice
    # produces exactly the same archive.
    stage_uuids = {key: str(uuid5(story_uuid, f"stage:{key}")) for key in stages}

    assets = {}
    taken_names = set()
    media_names = {}

    def register(source_path, kind):
        """Defers a media copy, deduplicated by source path."""
        if source_path is None:
            return None
        key = str(source_path)
        if key not in media_names:
            extension = ".png" if kind == "image" else source_path.suffix.lower()
            relative = str(source_path.relative_to(pack_dir))
            media_names[key] = _asset_name(relative, extension, taken_names)
            assets[media_names[key]] = source_path
        return media_names[key]

    def transition(telmi_transition):
        """Telmi ``{action, index}`` → STUdio ``{actionNode, optionIndex}``.

        A few packs spell the option ``indexItem``; -1 is kept as it is, since
        STUdio uses it to mean "pick one at random".
        """
        if not telmi_transition:
            return None
        action_id = telmi_transition.get("action")
        if action_id not in actions:
            return None
        option = telmi_transition.get("index")
        from_inventory = option is None and telmi_transition.get("indexItem") is not None
        if from_inventory and len(actions.get(action_id, ())) > 1:
            # Telmi picks the option a counter points at; a Lunii keeps no
            # counters, so this would always serve the first one — the same quiz
            # question forever. Random at least varies it, which is the nearest
            # thing to what the pack meant.
            option = RANDOM_OPTION
        elif option is None:
            option = telmi_transition.get("indexItem")
        return {
            "actionNode": action_id,
            "optionIndex": int(option if option is not None else 0),
            # Kept until the controls are settled, then dropped.
            INVENTORY_MARKER: from_inventory,
        }

    # Cover node, rebuilt from metadata.json and startAction.
    cover_image = pack_dir / "title.png"
    if not cover_image.is_file():
        cover_image = _find_media(pack_dir, ".", "title.png", IMAGE_EXTS)
    cover_audio = _find_media(pack_dir, ".", "title.mp3", AUDIO_EXTS)
    if cover_audio is None:
        raise TelmiFormatError(_("title.mp3 missing from {path}", path=pack_dir))

    stage_nodes = [{
        "uuid": str(story_uuid),
        "type": "cover",
        "name": metadata.get("title") or pack_dir.name,
        "position": {"x": 0, "y": 0},
        "image": register(cover_image, "image"),
        "audio": register(cover_audio, "audio"),
        "okTransition": transition(nodes.get("startAction")),
        "homeTransition": None,
        "controlSettings": dict(COVER_CONTROLS),
        "squareOne": True,
    }]

    for key, stage in stages.items():
        stage_nodes.append({
            "uuid": stage_uuids[key],
            "type": "stage",
            "name": key,
            "position": {"x": 0, "y": 0},
            "image": register(_find_media(pack_dir, "images", stage.get("image"), IMAGE_EXTS), "image"),
            "audio": register(_find_media(pack_dir, "audios", stage.get("audio"), AUDIO_EXTS), "audio"),
            "okTransition": transition(stage.get("ok")),
            "homeTransition": transition(stage.get("home")),
            "controlSettings": {
                "wheel": bool(stage.get("control", {}).get("wheel")),
                "ok": bool(stage.get("control", {}).get("ok")),
                "home": bool(stage.get("control", {}).get("home")),
                "pause": bool(stage.get("control", {}).get("pause")),
                "autoplay": bool(stage.get("control", {}).get("autoplay")),
            },
        })

    action_nodes = []
    for action_id, options in actions.items():
        option_uuids = []
        for option in options:
            stage_key = option.get("stage") if isinstance(option, dict) else option
            if stage_key in stage_uuids:
                option_uuids.append(stage_uuids[stage_key])
        if option_uuids:
            action_nodes.append({
                "id": action_id,
                "name": action_id,
                "position": {"x": 0, "y": 0},
                "options": option_uuids,
            })

    known_actions = {action["id"] for action in action_nodes}
    for node in stage_nodes:
        for field in ("okTransition", "homeTransition"):
            if node[field] and node[field]["actionNode"] not in known_actions:
                node[field] = None

    # Order matters: the wheel pass marks which stages are browsable options,
    # and settling an ending must leave those alone.
    _enable_choice_wheel(stage_nodes, action_nodes)
    action_nodes.extend(_settle_controls(stage_nodes, _start_uuid(stage_nodes, action_nodes)))
    _ensure_a_way_out(stage_nodes, action_nodes)
    for node in stage_nodes:
        for field in ("okTransition", "homeTransition"):
            if node[field]:
                node[field].pop(INVENTORY_MARKER, None)

    story_json = {
        "format": "v1",
        "version": int(metadata.get("version") or 1) or 1,
        "title": metadata.get("title") or pack_dir.name,
        "description": metadata.get("description") or "",
        "nightModeAvailable": False,
        "stageNodes": stage_nodes,
        "actionNodes": action_nodes,
    }
    if metadata.get("age") is not None:
        story_json["age"] = metadata["age"]
    if metadata.get("category"):
        story_json["category"] = metadata["category"]

    return story_json, assets


RESTART_ACTION_ID = "luniistory-restart"
INVENTORY_MARKER = "_fromInventory"
RANDOM_OPTION = -1   # STUdio's "pick one at random"


def _ensure_a_way_out(stage_nodes, action_nodes):
    """Leaves home without a destination where it cannot get you out.

    A pack does not walk back to its own cover to end. On the device, a lit
    home button with nothing behind it is the firmware's own exit to the story
    menu — a genuine Lunii story has four such nodes, and none of its
    transitions points at its cover. Walking to the cover instead leaves the
    device inside the pack, looking at its first page, with the menu wheel dead
    until it is switched off and on again.

    Telmi routes home into a prompt of its own, and some packs leave that
    prompt looping back to the first stage because Telmi OS takes you out
    itself. Where following home can never reach an exit, home becomes one.
    """
    options = {action["id"]: action["options"] for action in action_nodes}
    escapes = _stages_that_escape(stage_nodes, options)

    for node in stage_nodes[1:]:
        if not node["controlSettings"].get("home"):
            continue
        if node["uuid"] not in escapes:
            node["homeTransition"] = None


def _stages_that_escape(stage_nodes, options):
    """Stages from which pressing home, repeatedly, eventually leaves the pack.

    A stage escapes when its home button is lit and leads nowhere — that is the
    exit — or when every road home from it reaches such a stage.
    """
    escapes = {
        node["uuid"] for node in stage_nodes[1:]
        if node["controlSettings"].get("home") and not node["homeTransition"]
    }

    by_uuid = {node["uuid"]: node for node in stage_nodes}
    changed = True
    while changed:
        changed = False
        for node in stage_nodes[1:]:
            if node["uuid"] in escapes:
                continue
            move = node["homeTransition"]
            if not move:
                continue
            targets = options.get(move["actionNode"], ())
            # Reaching one stage that escapes is enough: the child presses home
            # again from there.
            if any(target in escapes and by_uuid.get(target) is not None for target in targets):
                escapes.add(node["uuid"])
                changed = True

    return escapes


def _enable_choice_wheel(stage_nodes, action_nodes):
    """Puts the wheel on the options, which is where the device looks for it.

    The wheel does not belong to the stage that asks the question — that one
    plays its prompt and moves on. It belongs to each option that stage leads
    to: the child lands on one, turns to hear the others, presses OK on the one
    they want.

    This is the opposite of what it looks like from the Telmi side, and getting
    it backwards leaves the wheel dead. Read off a genuine Lunii story, whose
    21 multi-option stages all have the wheel off while 44 other nodes have it
    on; and confirmed against the two packs that set it themselves, where every
    one of their 492 and 20 wheel stages is an option of a multi-option action
    and not one sits anywhere else.
    """
    chooseable = set()
    for action in action_nodes:
        if len(action["options"]) > 1:
            chooseable.update(action["options"])

    for node in stage_nodes[1:]:
        if node["uuid"] not in chooseable:
            continue
        controls = node["controlSettings"]
        controls["wheel"] = True
        # Turning takes time, which autoplay does not leave.
        controls["autoplay"] = False


def _start_uuid(stage_nodes, action_nodes):
    """Where the story begins: the first option of the cover's own transition."""
    move = stage_nodes[0]["okTransition"]
    if move:
        for action in action_nodes:
            if action["id"] == move["actionNode"] and action["options"]:
                return action["options"][0]
    return stage_nodes[1]["uuid"]


def _settle_controls(stage_nodes, start_uuid):
    """Gives an ending somewhere to go, and takes the OK button off it.

    Telmi writes ``ok: null`` on the stages that end a pack — the six endings
    of "La maison de la sorcière" use it, and so does the "yes, quit" branch of
    its back prompt. Left lit with nothing behind it, the device follows a
    transition that is not there and stops with an SD card error; a genuine
    Lunii story never has a lit OK without one.

    So the button goes out and the stage loops back to the start, which is what
    a Lunii story does when it ends — the child presses home to leave, and home
    is an exit everywhere by then.
    """
    action_nodes = []
    endings = [
        node for node in stage_nodes[1:]
        if node["controlSettings"].get("ok") and not node["okTransition"]
    ]
    if not endings:
        return action_nodes

    action_nodes.append({
        "id": RESTART_ACTION_ID,
        "name": RESTART_ACTION_ID,
        "position": {"x": 0, "y": 0},
        "options": [start_uuid],
    })
    for node in endings:
        node["okTransition"] = {"actionNode": RESTART_ACTION_ID, "optionIndex": 0}
        if node["controlSettings"].get("wheel"):
            # Also one of several options: the child has to be able to turn to
            # it and press OK, so the button stays lit and nothing autoplays.
            continue
        node["controlSettings"]["ok"] = False
        node["controlSettings"]["autoplay"] = True

    return action_nodes


def to_studio_zip(pack_dir, output_zip, progress=None):
    """Writes the STUdio archive matching the Telmi pack at ``pack_dir``."""
    pack_dir = find_pack_root(pack_dir)
    output_zip = Path(output_zip)
    output_zip.parent.mkdir(parents=True, exist_ok=True)

    metadata, nodes = read_pack(pack_dir)
    story_json, assets = build_story_json(metadata, nodes, pack_dir)

    thumbnail = _find_media(pack_dir, ".", metadata.get("image") or "cover.png", IMAGE_EXTS)

    total = len(assets) + 2
    with zipfile.ZipFile(output_zip, "w", zipfile.ZIP_STORED) as archive:
        archive.writestr("story.json", json.dumps(story_json, ensure_ascii=False))
        if thumbnail and thumbnail.is_file():
            archive.write(thumbnail, "thumbnail.png")
        if progress:
            progress(1, total)
        for index, (name, source) in enumerate(sorted(assets.items()), start=2):
            if name.lower().endswith(AUDIO_EXTS):
                # Catalogue packs are not all mono: whatever the device cannot
                # play is folded here, so the import never asks for FFMPEG.
                archive.writestr(f"assets/{name}", audio.to_lunii_mp3(source.read_bytes(), name))
            else:
                archive.write(source, f"assets/{name}")
            if progress:
                progress(index, total)

    return output_zip


def zip_to_studio_zip(telmi_zip, output_zip, work_dir, progress=None):
    """Unpacks then converts, cleaning the working folder either way."""
    work_dir = Path(work_dir)
    if work_dir.exists():
        shutil.rmtree(work_dir, ignore_errors=True)
    try:
        pack_dir = extract_pack(telmi_zip, work_dir)
        return to_studio_zip(pack_dir, output_zip, progress=progress)
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
