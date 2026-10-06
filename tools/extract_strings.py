"""Lists the translatable source strings and reports catalog gaps.

    python tools/extract_strings.py          # report
    python tools/extract_strings.py --sync   # add missing keys, untranslated
"""

import ast
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
LOCALES_DIR = ROOT / "luniistory" / "locales"


def source_strings():
    """Every literal passed to ``_()`` or ``translate()``, in reading order."""
    found = []
    for path in sorted((ROOT / "luniistory").rglob("*.py")):
        tree = ast.parse(path.read_text("utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and isinstance(node.func, ast.Name)
                    and node.func.id in ("_", "_n", "translate", "translate_plural")):
                # translate() takes the text first, translate_plural() the count.
                literals = node.args[1:3] if node.func.id in ("_n", "translate_plural") else node.args[:1]
                for argument in literals:
                    if (isinstance(argument, ast.Constant) and isinstance(argument.value, str)
                            and argument.value not in found):
                        found.append(argument.value)
    return found


def main(sync=False):
    sources = source_strings()
    status = 0

    for catalog_path in sorted(LOCALES_DIR.glob("*.json")):
        catalog = json.loads(catalog_path.read_text("utf-8"))
        missing = [text for text in sources if text not in catalog]
        orphans = [key for key in catalog if key not in sources]

        print(f"{catalog_path.name}: {len(catalog)} entries, "
              f"{len(missing)} missing, {len(orphans)} orphaned")
        for text in missing:
            print(f"  missing  {text!r}")
        for key in orphans:
            print(f"  orphan   {key!r}")

        if sync and (missing or orphans):
            merged = {text: catalog.get(text, text) for text in sources}
            catalog_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2) + "\n", "utf-8")
            print(f"  → {catalog_path.name} rewritten")
        elif missing or orphans:
            status = 1

    print(f"\n{len(sources)} source string(s)")
    return status


if __name__ == "__main__":
    sys.exit(main(sync="--sync" in sys.argv))
