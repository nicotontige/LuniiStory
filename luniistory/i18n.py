"""Translations.

Source strings are English, so English needs no catalog and a missing
translation degrades to the original text rather than to a key.
"""

import json
import locale
import os
from pathlib import Path

LOCALES_DIR = Path(__file__).parent / "locales"
DEFAULT_LANGUAGE = "en"
LANGUAGE_NAMES = {"en": "English", "fr": "Français"}

# Which form a count selects. English pluralises zero, French does not.
PLURAL_RULES = {
    "en": lambda count: 0 if count == 1 else 1,
    "fr": lambda count: 0 if count in (0, 1) else 1,
}

_catalog = {}
_language = DEFAULT_LANGUAGE


def available_languages():
    """Language codes shipped with the application, English first."""
    codes = [DEFAULT_LANGUAGE]
    codes += sorted(path.stem for path in LOCALES_DIR.glob("*.json") if path.stem != DEFAULT_LANGUAGE)
    return codes


def language_name(code):
    return LANGUAGE_NAMES.get(code, code)


def system_language():
    """Language code the host is set to, or ``None``.

    ``locale.getdefaultlocale`` would do this in one call but is slated for
    removal in Python 3.15, so we read the environment first — which is what it
    did anyway — and only then ask the C library.
    """
    for variable in ("LC_ALL", "LC_MESSAGES", "LANG", "LANGUAGE"):
        value = os.environ.get(variable)
        if value and value not in ("C", "POSIX"):
            return value.split(".")[0].split("_")[0].lower()

    try:
        locale.setlocale(locale.LC_ALL, "")
        code = locale.getlocale()[0]
    except (locale.Error, ValueError):
        return None
    return code.split("_")[0].lower() if code else None


def detect_language():
    """Language to start with: explicit setting first, system locale second."""
    from luniistory import config

    requested = os.environ.get("LUNIISTORY_LANG") or config.load_settings().get("language")
    if requested in available_languages():
        return requested

    code = system_language()
    if code in available_languages():
        return code

    return DEFAULT_LANGUAGE


def set_language(code):
    """Loads the catalog for ``code``; falls back to English if unknown."""
    global _catalog, _language

    if code not in available_languages():
        code = DEFAULT_LANGUAGE

    _language = code
    if code == DEFAULT_LANGUAGE:
        _catalog = {}
        return code

    try:
        _catalog = json.loads((LOCALES_DIR / f"{code}.json").read_text("utf-8"))
    except (OSError, ValueError):
        _catalog = {}
    return code


def current_language():
    return _language


def translate(text, **kwargs):
    """Translates ``text`` and interpolates the given named arguments."""
    translated = _catalog.get(text, text)
    return translated.format(**kwargs) if kwargs else translated


def translate_plural(count, singular, plural, **kwargs):
    """Translates the form matching ``count`` under the current language's rule.

    Both forms are English source strings, so each is its own catalog key and a
    language that splits the forms differently still gets the right one.
    """
    rule = PLURAL_RULES.get(_language, PLURAL_RULES[DEFAULT_LANGUAGE])
    return translate(singular if rule(count) == 0 else plural, count=count, **kwargs)


# Short aliases, used everywhere user-facing text is produced.
_ = translate
_n = translate_plural
