"""Translation catalogs must stay in step with the source strings."""

import json

import pytest

from luniistory import i18n
from tools.extract_strings import source_strings

CATALOGS = sorted(i18n.LOCALES_DIR.glob("*.json"))


@pytest.fixture(autouse=True)
def restore_language():
    previous = i18n.current_language()
    yield
    i18n.set_language(previous)


def test_english_is_the_source_language():
    i18n.set_language("en")
    assert i18n.current_language() == "en"
    # No catalog for English: the source string is the translation.
    assert i18n.translate("Ready") == "Ready"
    assert i18n.available_languages()[0] == "en"


def test_french_is_shipped():
    assert "fr" in i18n.available_languages()
    i18n.set_language("fr")
    assert i18n.translate("Ready") == "Prêt"
    assert i18n.translate("Transfer selection ({count})", count=3) == "Transférer la sélection (3)"


def test_unknown_language_falls_back_to_english():
    assert i18n.set_language("kl") == "en"
    assert i18n.translate("Ready") == "Ready"


def test_untranslated_string_keeps_its_source_text():
    i18n.set_language("fr")
    assert i18n.translate("Not in any catalog") == "Not in any catalog"


@pytest.mark.parametrize("catalog_path", CATALOGS, ids=lambda path: path.stem)
def test_catalog_covers_every_source_string(catalog_path):
    catalog = json.loads(catalog_path.read_text("utf-8"))
    sources = set(source_strings())

    assert not sources - set(catalog), "missing translations"
    assert not set(catalog) - sources, "orphaned entries"


@pytest.mark.parametrize("catalog_path", CATALOGS, ids=lambda path: path.stem)
def test_placeholders_match_the_source(catalog_path):
    """A translation that drops or invents a {placeholder} raises at format time."""
    import string

    catalog = json.loads(catalog_path.read_text("utf-8"))
    for source, translated in catalog.items():
        names = {name for _text, name, _spec, _conv in string.Formatter().parse(source) if name}
        translated_names = {name for _text, name, _spec, _conv in string.Formatter().parse(translated) if name}
        assert names == translated_names, f"placeholders differ for {source!r}"


def test_system_language_reads_the_environment(monkeypatch):
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    monkeypatch.delenv("LC_ALL", raising=False)
    monkeypatch.delenv("LC_MESSAGES", raising=False)
    assert i18n.system_language() == "fr"


def test_a_neutral_locale_is_not_a_language(monkeypatch):
    for variable in ("LC_ALL", "LC_MESSAGES", "LANGUAGE"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.setenv("LANG", "C")
    # "C" is the absence of a locale, not a language; detection must look further.
    assert i18n.system_language() != "c"


def test_explicit_setting_wins_over_the_system(monkeypatch, tmp_path):
    monkeypatch.setenv("LUNIISTORY_LANG", "en")
    monkeypatch.setenv("LANG", "fr_FR.UTF-8")
    assert i18n.detect_language() == "en"
