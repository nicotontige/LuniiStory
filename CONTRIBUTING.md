# Contributing to luniiStory

Thanks for taking a look. This covers running the application from source, how
the conversion works, and how a release is cut.

## Running it

Clone, then launch — the script creates the virtual environment, fetches the
submodule and installs the dependencies on its first run:

```bash
git clone --recurse-submodules https://github.com/nicotontige/LuniiStory.git
cd LuniiStory
./run.sh           # Windows: run.bat
```

Arguments are passed through, so `./run.sh list` runs the command line instead
of opening the window.

Without the launcher:

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python -m luniistory
```

`pip install -e .` additionally puts a `luniistory` command on the path.

## Working on it

`make` runs locally what CI runs on push, creating the virtual environment on
first call:

| Command | What it does |
| --- | --- |
| `make` | tests, pyflakes, workflow lint, translation catalogs |
| `make run` | launches the app from the source tree |
| `make build` | packages for this machine, then smoke-tests the result |
| `make run-dist` | launches the packaged app |
| `make rehearse` | builds all four platforms in CI, publishing nothing |
| `make release` | tags the current version, refusing a dirty tree |
| `make clean` | drops `build/`, `dist/` and the caches |

While working on the code, `make run` is the one to use — it skips packaging and
starts in a second. `make run ARGS="list --age 5"` runs a command instead of
opening the window.

`make build` does not stop at a successful build: it runs the packaged binary
and checks that the translations shipped, that the config is reachable and that
the Lunii engine loads. A build that completes can still produce a bundle that
dies on launch, and that is the failure worth catching before a tag.

Only your own platform can be built locally — PyInstaller does not cross
compile — so `make rehearse` is the step that covers the rest. `actionlint`
checks the workflows if it is installed (`brew install actionlint`); keep it
current, since its list of runner labels is baked in at build time and goes
stale as GitHub retires images.

## What it builds on

One dependency is code. [Lunii.QT](https://github.com/o-daneel/Lunii.QT) is
vendored as a git submodule under `vendor/Lunii.QT` and does everything on the
device side: detection, ciphering, writing stories. `luniistory/lunii_api.py`
only puts it on the import path — none of its source is copied, so upstream
fixes come in with `git submodule update --remote`. It is also where this
project's GPL-3 licence comes from.

Everything else is written here: the library client, the converter, the interface.

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

Two things it fixes along the way, because Telmi OS answers them itself and a
Lunii does not:

- a button left lit with no transition behind it is sent to the cover node,
  which is the way out of a pack on the device. Telmi writes `ok: null` on the
  stages that end a story, and following a transition that is not there stops
  the device with an SD card error;
- a stage whose OK leads to an action with several options is given the wheel,
  which is how options are browsed on the device. Some packs never declare one,
  and without it the first option is forced and the rest of an interactive story
  is unreachable.

## Audio

The Lunii only plays mono 44.1 kHz MP3, and plenty of what the catalogs publish
is stereo — podcast episodes always, story packs often enough. Rather than pull
in an 80 MB FFMPEG binary to downmix a track, luniiStory decodes through
miniaudio and re-encodes through LAME: half a megabyte of ordinary wheels, and
about eight seconds for a 300-track pack. Audio that already fits is passed
through untouched. FFMPEG is still used if it happens to be installed, for the
formats those two do not cover.

## Language

The application ships in English and French. It starts in your system language
when that language is available, and in English otherwise.

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

## Tests

```bash
.venv/bin/python -m pytest
```

They cover the Telmi → STUdio conversion, its round trip through the Lunii.QT
engine, a full install onto a Lunii v2 simulated on disk — no hardware needed to
check that a story is written correctly — the audio conversion, and the
translation catalogs.

## Where things live

| Path | Contents |
| --- | --- |
| `~/.luniistory/stores.json` | configured libraries |
| `~/.luniistory/settings.json` | `language` and `check_updates` |
| `~/.luniistory/library/` | downloaded packs |
| `~/.luniistory/cache/` | thumbnails and the published library list |
| `~/.lunii-qt/` | Lunii.QT story databases and device metadata backups |

Set `LUNIISTORY_HOME` to move the first.

## Artwork

`python tools/make_icon.py` redraws the application icon and the README banner,
and writes the png, ico and icns. The results are committed, so a build never
depends on the fonts installed on the machine doing the building.

## Logs

Everything is written to `~/.luniistory/logs/luniistory.log`, rotated at 2 MB
with three backups. The file keeps DEBUG, which is the level that explains a
failure after the fact; the console and the window's log panel show less.

What goes in it: the version, the system, whether FFMPEG is around, every
device that is opened with its firmware and serial, every message the Lunii.QT
engine emits, and the stack trace of anything that fails. A failed transfer
used to lose its traceback entirely — it was emitted at DEBUG into a panel that
dropped DEBUG — which is exactly the thing a report needs.

```bash
python -m luniistory logs             # where it is, and how big
python -m luniistory logs --tail 60   # the last lines
python -m luniistory -v devices       # also print the debug level while running
```

The settings window has a button to open the folder, which is the route to
suggest when someone reports a problem.

## Update checks

On launch the application asks GitHub for the latest release and, if it is newer
than `__version__`, shows a button in the header pointing at the release page.
The answer is cached for a day, so launching repeatedly is one request, not one
per launch.

Nothing is downloaded or installed: the binaries are unsigned, and an
application that replaces itself from the network is a far bigger promise than
this one makes.

```bash
python -m luniistory version              # the version, and whether a newer one is out
python -m luniistory version --no-check   # just the version
python -m luniistory version --refresh    # ignore the cached answer
```

The check is opt-out, from the settings window or through `check_updates` in
`~/.luniistory/settings.json`.

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
