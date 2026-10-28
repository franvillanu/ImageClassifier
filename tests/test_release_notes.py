from image_classifier.updates.check import DOWNLOAD_PREFIX, newer_release
from image_classifier.updates.notes import (
    load_release_notes,
    notes_for_version,
    notes_marker,
    parse_notes_marker,
    pick,
)

NOTES = """# comment
2.0.7|Seven EN|Siete ES
2.0.10|Ten EN|Diez ES
2.0.8|Eight EN|
not a version|x|y
"""


def write_notes(tmp_path):
    path = tmp_path / "release_notes.txt"
    path.write_text(NOTES, encoding="utf-8")
    return path


def test_load_sorts_numerically_and_skips_junk(tmp_path):
    entries = load_release_notes(write_notes(tmp_path))
    assert [e[0] for e in entries] == ["2.0.10", "2.0.8", "2.0.7"]


def test_missing_file_gives_no_notes(tmp_path):
    assert load_release_notes(tmp_path / "nope.txt") == []


def test_pick_language_and_spanish_falls_back_to_english(tmp_path):
    entries = load_release_notes(write_notes(tmp_path))
    assert pick(notes_for_version("2.0.7", entries), "es") == "Siete ES"
    assert pick(notes_for_version("2.0.7", entries), "en") == "Seven EN"
    assert pick(notes_for_version("2.0.8", entries), "es") == "Eight EN"
    assert notes_for_version("9.9.9", entries) is None


def test_marker_round_trip_with_accents_and_quotes():
    marker = notes_marker('Say "hi"', "Añadido ñ -- y > <")
    assert parse_notes_marker(f"## Version\n\n- item\n\n{marker}\n") == {
        "en": 'Say "hi"',
        "es": "Añadido ñ -- y > <",
    }


def test_bad_or_missing_marker_is_ignored():
    assert parse_notes_marker(None) is None
    assert parse_notes_marker("no marker here") is None
    assert parse_notes_marker("<!-- ic-notes {not json} -->") is None
    assert parse_notes_marker('<!-- ic-notes {"es": "solo"} -->') is None


def test_offer_carries_notes_from_release_body():
    name = "ImageClassifierSetup_v2.0.9.exe"
    release = {
        "tag_name": "v2.0.9",
        "body": "## Version 2.0.9\n\n" + notes_marker("New thing", "Cosa nueva"),
        "assets": [{"name": name, "browser_download_url": f"{DOWNLOAD_PREFIX}v2.0.9/{name}"}],
    }
    offer = newer_release("2.0.8", release)
    assert (offer.notes_en, offer.notes_es) == ("New thing", "Cosa nueva")
    release["body"] = "plain body"
    assert newer_release("2.0.8", release).notes_en is None


def test_current_version_has_bundled_notes():
    """Every release needs its customer-facing line, which the app shows after updating."""
    from image_classifier import __version__

    entry = notes_for_version(__version__)
    assert entry is not None and entry[1] and entry[2]
