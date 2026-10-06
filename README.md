# luniiStory

[![License: GPL v3](https://img.shields.io/badge/license-GPL--3.0-blue.svg)](LICENSE)
[![Buy me a coffee](https://img.shields.io/badge/buy%20me%20a%20coffee-ffdd00?logo=buymeacoffee&logoColor=black)](https://buymeacoffee.com/nicotontige)

Browse community story stores and send the stories to a **Lunii**, on Windows,
macOS and Linux.

The free stories the community publishes come as Telmi packs, a format a Lunii
cannot read. luniiStory bridges the two: it fetches the store catalogs, converts
the packs it downloads, and writes them to the device.

## What it builds on

One dependency is code. [Lunii.QT](https://github.com/o-daneel/Lunii.QT) is
vendored as a git submodule under `vendor/Lunii.QT` and does everything on the
device side: detection, ciphering, writing stories. `luniistory/lunii_api.py`
only puts it on the import path — none of its source is copied, so upstream
fixes come in with `git submodule update --remote`. It is also where this
project's GPL-3 licence comes from.

Everything else is written here: the store client, the converter, the interface.

## How the conversion works

Store packs use the Telmi format — `metadata.json`, `nodes.json`, `title.mp3`,
`audios/`, `images/`. That format is a STUdio pack with its first stage node,
the cover, folded away: the node's UUID and media become the metadata and
`title.mp3`, its transition becomes `startAction`, and stages, actions and media
are renumbered `s0`, `a0`, `0.mp3`.

luniiStory walks that path backwards:

```
Telmi pack                      STUdio archive
  metadata.json  ──┐
  nodes.json     ──┼──────────▶  story.json   (cover node rebuilt,
  title.png      ──┤                           stages given back their UUIDs)
  title.mp3      ──┘
  images/*.png   ───────────────▶ assets/XXXXXXXX.png
  audios/*.mp3   ───────────────▶ assets/XXXXXXXX.mp3
  cover.png      ───────────────▶ thumbnail.png
```

Lunii.QT then takes over: it generates the `ri`, `si`, `li` and `ni` index files,
turns the images into 320×240 RLE4 bitmaps, ciphers whatever the device
generation requires, and updates `.pi`.

The conversion is deterministic: the same pack always yields the same archive,
and stage identifiers are derived from the story UUID.

## Running it

Clone, then launch — the script creates the virtual environment, fetches the
submodule and installs the dependencies on its first run:

```bash
git clone --recurse-submodules https://github.com/nicotontige/luniiStory.git
cd luniiStory
./run.sh           # Windows: run.bat
```

Pick the stories you want, plug the Lunii in, hit *Transfer selection*. Stories
already on the device are flagged as such, and a file dropped onto the window is
imported straight away.

Arguments are passed through, so `./run.sh list` runs the command line instead
of opening the window.

**FFMPEG is not required.** Store packs already ship mono 44.1 kHz MP3, exactly
what the Lunii expects. You only need FFMPEG to import a story whose audio is in
some other format.

### Without the launcher

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m luniistory
```

`pip install -e .` additionally puts a `luniistory` command on the path.

### As a standalone application

Grab the archive for your platform from the
[releases](../../releases) — nothing to install, Python, Qt and the engine are
inside. The builds are unsigned, so macOS quarantines them on first launch:

```bash
xattr -dr com.apple.quarantine /Applications/luniiStory.app
```

Building one yourself takes a single command:

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pyinstaller luniistory.spec
```

It produces `dist/luniistory/` on Windows and Linux, and a double-clickable
`dist/luniiStory.app` on macOS, around 100 MB.

## Usage

Command line:

```bash
python -m luniistory list --age 5              # filtered catalog
python -m luniistory list sorcier              # search
python -m luniistory devices                   # connected Lunii
python -m luniistory info                      # what is on the device
python -m luniistory install halloween         # download, convert, transfer
python -m luniistory import story.zip          # local archive (Telmi, STUdio, .pk)
python -m luniistory rm D8BD184F               # remove a story
python -m luniistory convert pack.zip out.zip  # conversion only, no device needed
python -m luniistory cache --clear             # drop downloaded packs
```

### Language

The application ships in **English and French**. It starts in your system
language when that language is available, and in English otherwise. The picker
in the window header switches at any time and remembers the choice.

```bash
python -m luniistory lang            # list the languages, * marks the current one
python -m luniistory lang fr         # switch and remember
python -m luniistory --lang fr list  # just for this run
```

`LUNIISTORY_LANG` overrides both.

Source strings are English, so English needs no catalog and an untranslated
string falls back to its English text rather than to a key. Adding a language
means dropping a `luniistory/locales/<code>.json` next to `fr.json`:

```bash
python tools/extract_strings.py          # report what each catalog is missing
python tools/extract_strings.py --sync   # fill the gaps with the English text
```

The test suite fails if a catalog drifts from the source strings, or if a
translation drops or invents a `{placeholder}`.

### Adding a store

A store is any URL serving a Telmi JSON catalog or a podcast RSS feed:

```bash
python -m luniistory store-add "My store" https://example.org/catalog.json
```

Two community catalogs — Telmi Interactive and Litteratureaudio.com — are
configured out of the box, so there is something to browse on first launch.

## Devices

| Device | Status |
| --- | --- |
| Lunii v1, v2 | supported |
| Lunii v3 | needs the device keys in `~/.lunii-qt/<serial>.keys` |
| Flam | not exposed yet |

These limits are Lunii.QT's; its [README](vendor/Lunii.QT/README.md) documents
the v3 key procedure.

## Where things live

| Path | Contents |
| --- | --- |
| `~/.luniistory/stores.json` | configured stores |
| `~/.luniistory/library/` | downloaded packs |
| `~/.luniistory/cache/` | thumbnails |
| `~/.lunii-qt/` | Lunii.QT third-party story database |

Set `LUNIISTORY_HOME` to move the first one.

## Development

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

The tests cover the Telmi → STUdio conversion, its round trip through the
Lunii.QT engine, a full install onto a Lunii v2 simulated on disk — no hardware
needed to check that a story is written correctly — and the translation
catalogs.

## Releases

Two workflows run in GitHub Actions, with every action pinned to a commit SHA:

- `tests.yml` runs the suite on Linux, macOS and Windows for every push and
  pull request;
- `release.yml` fires on a `v*` tag — it refuses to go on unless the tag matches
  `__version__`, runs the tests again, builds for Linux, Windows and both macOS
  architectures, then publishes the archives with their `SHA256SUMS` and a
  generated changelog.

Cutting a release is three commands, the version living in
`luniistory/__init__.py` alone:

```bash
sed -i '' 's/0.1.0/0.2.0/' luniistory/__init__.py
git commit -am "version 0.2.0"
git tag v0.2.0 && git push --follow-tags
```

Running the workflow by hand from the Actions tab builds every platform without
publishing anything, which is the way to rehearse a change to the recipe.

## Support

luniiStory is a spare-time project. If it saved you an evening of fiddling with
story files, you can [buy me a coffee](https://buymeacoffee.com/nicotontige).

## License

GPL-3.0, inherited from Lunii.QT whose engine this project builds on.

luniiStory distributes no stories of its own. It follows the public catalogs you
point it at, and transfers to your own Lunii the stories their authors chose to
make available.
