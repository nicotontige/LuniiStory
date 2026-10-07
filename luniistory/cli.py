"""Command line interface."""

import argparse
import logging
import sys
import unicodedata

from luniistory import __version__, config, eject, i18n, library, stores, transfer, updates, usb
from luniistory.convert import telmi
from luniistory.i18n import _, _n

LEVEL_PREFIX = {
    logging.DEBUG: "   ",
    logging.INFO: "   ",
    logging.WARNING: " ! ",
    logging.ERROR: " ✗ ",
}


def _normalize(text):
    """Lowercase and unaccented, for a forgiving search."""
    decomposed = unicodedata.normalize("NFD", str(text).lower())
    return "".join(char for char in decomposed if unicodedata.category(char) != "Mn")


def _log(level, message):
    print(f"{LEVEL_PREFIX.get(level, '   ')}{message}")


def _progress(label, current, total):
    if not total:
        return
    percent = min(100, current * 100 // total)
    print(f"\r   {label} {percent:3d} %", end="", flush=True)
    if current >= total:
        print()


def _catalog(args):
    def report(store, error):
        print(_(" ! library “{name}” unreachable: {error}", name=store["name"], error=error), file=sys.stderr)

    catalog = stores.fetch_all(on_error=report)

    if getattr(args, "store", None):
        wanted = _normalize(args.store)
        catalog = [story for story in catalog if wanted in _normalize(story.store_name)]
    if getattr(args, "age", None) is not None:
        catalog = [story for story in catalog if story.age <= args.age]
    for term in getattr(args, "search", None) or []:
        needle = _normalize(term)
        catalog = [
            story for story in catalog
            if needle in _normalize(story.title)
            or needle in _normalize(story.description)
            or needle == _normalize(story.uuid)
        ]
    return catalog


def _pick_device(args):
    mount_points = [args.device] if getattr(args, "device", None) else transfer.find_lunii()
    if not mount_points:
        if usb.is_lunii_attached():
            raise SystemExit(_(" ✗ A Lunii is connected but has not opened its storage. Switch it on."))
        raise SystemExit(_(" ✗ No Lunii found. Plug one in and try again."))
    if len(mount_points) > 1 and not getattr(args, "device", None):
        listing = "\n".join(f"   - {point}" for point in mount_points)
        raise SystemExit(_(" ✗ Several devices found, pass --device:\n{listing}", listing=listing))
    return transfer.open_device(mount_points[0])


def cmd_stores(args):
    for store in config.load_stores():
        mark = " " if store.get("deletable", True) else "*"
        print(f" {mark} {store['name']}\n     {store['url']}")
    print("\n" + _("   * default library, cannot be removed"))
    return 0


def cmd_store_add(args):
    config.add_store(args.name, args.url)
    print(_(" ✓ Library “{name}” added", name=args.name))
    return 0


def cmd_store_rm(args):
    config.remove_store(args.url)
    print(_(" ✓ Library removed"))
    return 0


def cmd_list(args):
    catalog = _catalog(args)
    for story in catalog:
        badges = "".join([
            "★" if story.is_new else "",
            "↻" if story.is_updated and not story.is_new else "",
            "✓" if library.is_downloaded(story) else "",
        ])
        print(f" {story.age:>2}+ {badges:<3} {story.title}")
        print(f"       {story.store_name} · {story.category or _('uncategorised')} · {story.key[:8]}")
    print("\n   " + _(
        "{stories} — ★ new, ↻ updated, ✓ already downloaded",
        stories=_n(len(catalog), "{count} story", "{count} stories"),
    ))
    return 0


def cmd_devices(args):
    mount_points = transfer.find_lunii()
    if not mount_points:
        if usb.is_lunii_attached():
            print(_(" ! A Lunii is connected but has not opened its storage. Switch it on."))
        else:
            print(_(" ✗ No Lunii found"))
        return 1
    for mount_point in mount_points:
        device = transfer.open_device(mount_point)
        print(f" ✓ {mount_point} — {transfer.describe(device)}")
    return 0


def cmd_info(args):
    device = _pick_device(args)
    print(f" ✓ {device.mount_point} — {transfer.describe(device)}\n")
    for index, story in enumerate(transfer.installed_stories(device), start=1):
        night = " 🌙" if story["night_mode"] else ""
        print(f" {index:>3}. {story['name']}{night}")
        print(f"      {story['uuid']}")
    return 0


def cmd_install(args):
    catalog = _catalog(args)
    if not catalog:
        print(_(" ✗ No story matches"), file=sys.stderr)
        return 1
    if len(catalog) > 1 and not args.all:
        print(_(" ! Several stories match, narrow the search or add --all:"))
        for story in catalog:
            print(f"   - {story.title} ({story.store_name})")
        return 1

    device = _pick_device(args)
    failures = 0
    for story in catalog:
        print(f"\n ▸ {story.title}")
        try:
            transfer.install_story(device, story, on_log=_log, on_progress=_progress)
            print(_(" ✓ “{title}” transferred", title=story.title))
        except Exception as error:
            failures += 1
            print(f" ✗ {error}", file=sys.stderr)
    transfer.cleanup_tmp()
    return 1 if failures else 0


def cmd_import(args):
    device = _pick_device(args)
    failures = 0
    for path in args.archives:
        print(f"\n ▸ {path}")
        try:
            transfer.install_archive(device, path, on_log=_log, on_progress=_progress)
            print(_(" ✓ {path} transferred", path=path))
        except Exception as error:
            failures += 1
            print(f" ✗ {error}", file=sys.stderr)
    transfer.cleanup_tmp()
    return 1 if failures else 0


def cmd_rm(args):
    device = _pick_device(args)
    for short_uuid in args.uuids:
        if transfer.remove_story(device, short_uuid.upper()):
            print(_(" ✓ {uuid} removed", uuid=short_uuid))
        else:
            print(_(" ✗ {uuid} not found on the device", uuid=short_uuid), file=sys.stderr)
    return 0


def cmd_convert(args):
    output = telmi.zip_to_studio_zip(
        args.archive, args.output, config.TMP_DIR / "convert",
        progress=lambda current, total: _progress(_("Converting"), current, total),
    )
    print(_(" ✓ STUdio archive written: {path}", path=output))
    return 0


def cmd_cache(args):
    if args.clear:
        library.clear()
        print(_(" ✓ Downloads emptied"))
        return 0
    index = library.load_index()
    for entry in index.values():
        print(f"   {entry.get('title')} — {entry.get('store')}")
    print("\n   " + _(
        "{packs}, {size:.0f} MB in {path}",
        packs=_n(len(index), "{count} pack", "{count} packs"),
        size=library.downloaded_size() / 1e6, path=config.LIBRARY_DIR,
    ))
    return 0


def cmd_eject(args):
    mount_points = [args.device] if args.device else transfer.find_lunii()
    if not mount_points:
        print(_(" ✗ No Lunii found"), file=sys.stderr)
        return 1
    for mount_point in mount_points:
        try:
            eject.eject(mount_point)
            print(_(" ✓ {path} ejected, the Lunii can be unplugged", path=mount_point))
        except Exception as error:
            print(_(" ✗ Could not eject the Lunii: {error}", error=error), file=sys.stderr)
            return 1
    return 0


def cmd_version(args):
    print(f"luniistory {__version__}")

    if args.no_check:
        return 0
    latest = updates.latest_version(use_cache=not args.refresh)
    if latest is None:
        print(_("   could not reach the release page"))
    elif updates.is_newer(latest):
        print(_("   version {version} is out: {url}", version=latest, url=updates.RELEASES_PAGE))
    else:
        print(_("   up to date"))
    return 0


def cmd_lang(args):
    if args.language:
        config.save_setting("language", i18n.set_language(args.language))
        print(_(" ✓ Language set to {name}", name=i18n.language_name(i18n.current_language())))
        return 0
    for code in i18n.available_languages():
        mark = "*" if code == i18n.current_language() else " "
        print(f" {mark} {code} — {i18n.language_name(code)}")
    return 0


def cmd_gui(args):
    from luniistory.ui.app import run

    return run()


def build_parser():
    parser = argparse.ArgumentParser(
        prog="luniistory",
        description=_("Browse community story libraries and send the stories to a Lunii."),
    )
    parser.add_argument("--lang", choices=i18n.available_languages(),
                        help=_("language for this run"))
    subparsers = parser.add_subparsers(dest="command")

    def with_filters(sub):
        sub.add_argument("search", nargs="*", help=_("terms searched in title and description"))
        sub.add_argument("--store", help=_("restrict to one library"))
        sub.add_argument("--age", type=int, help=_("maximum recommended age"))
        return sub

    with_filters(subparsers.add_parser("list", help=_("list the stories in the libraries"))).set_defaults(func=cmd_list)

    install = with_filters(subparsers.add_parser("install", help=_("transfer a story to the Lunii")))
    install.add_argument("--device", help=_("mount point of the Lunii"))
    install.add_argument("--all", action="store_true", help=_("transfer every match"))
    install.set_defaults(func=cmd_install)

    subparsers.add_parser("libraries", help=_("list the configured libraries")).set_defaults(func=cmd_stores)

    store_add = subparsers.add_parser("library-add", help=_("add a library"))
    store_add.add_argument("name")
    store_add.add_argument("url")
    store_add.set_defaults(func=cmd_store_add)

    store_rm = subparsers.add_parser("library-remove", help=_("remove a library"))
    store_rm.add_argument("url")
    store_rm.set_defaults(func=cmd_store_rm)

    subparsers.add_parser("devices", help=_("list the connected Lunii")).set_defaults(func=cmd_devices)

    info = subparsers.add_parser("info", help=_("details of the Lunii and its contents"))
    info.add_argument("--device")
    info.set_defaults(func=cmd_info)

    import_cmd = subparsers.add_parser("import", help=_("transfer a local archive (Telmi, STUdio, .pk)"))
    import_cmd.add_argument("archives", nargs="+")
    import_cmd.add_argument("--device")
    import_cmd.set_defaults(func=cmd_import)

    remove = subparsers.add_parser("rm", help=_("remove a story from the Lunii"))
    remove.add_argument("uuids", nargs="+", help=_("short UUID shown by “info”"))
    remove.add_argument("--device")
    remove.set_defaults(func=cmd_rm)

    convert = subparsers.add_parser("convert", help=_("convert a Telmi pack into a STUdio archive"))
    convert.add_argument("archive")
    convert.add_argument("output")
    convert.set_defaults(func=cmd_convert)

    cache = subparsers.add_parser("cache", help=_("state of the downloaded packs"))
    cache.add_argument("--clear", action="store_true", help=_("delete the downloaded packs"))
    cache.set_defaults(func=cmd_cache)

    eject_cmd = subparsers.add_parser("eject", help=_("unmount the Lunii so it can be unplugged"))
    eject_cmd.add_argument("--device")
    eject_cmd.set_defaults(func=cmd_eject)

    version = subparsers.add_parser("version", help=_("show the version and look for a newer one"))
    version.add_argument("--no-check", action="store_true", help=_("do not ask whether a newer one is out"))
    version.add_argument("--refresh", action="store_true", help=_("ignore the cached answer"))
    version.set_defaults(func=cmd_version)

    language = subparsers.add_parser("lang", help=_("show or set the interface language"))
    language.add_argument("language", nargs="?", choices=i18n.available_languages())
    language.set_defaults(func=cmd_lang)

    subparsers.add_parser("gui", help=_("open the graphical interface")).set_defaults(func=cmd_gui)

    return parser


def main(argv=None):
    # The language has to be settled before the parser is built, since its help
    # strings are translated as they are declared.
    argv = list(sys.argv[1:] if argv is None else argv)
    requested = next(
        (argv[index + 1] for index, value in enumerate(argv) if value == "--lang" and index + 1 < len(argv)),
        None,
    )
    i18n.set_language(requested or i18n.detect_language())

    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "func", None):
        return cmd_gui(args)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("\n" + _(" ! Interrupted"))
        return 130


if __name__ == "__main__":
    sys.exit(main())
