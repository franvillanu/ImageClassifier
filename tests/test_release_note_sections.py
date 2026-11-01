"""Release notes grouped like Sidera's: new features, changes, fixes."""
import importlib.util
from pathlib import Path

from image_classifier.updates.notes import load_release_notes, sections

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_sections_group_tagged_points_in_a_fixed_order():
    text = "fixed: B is fixed • new: A is new • changed: C changed • new: D is new"
    assert sections(text) == [("new", ["A is new", "D is new"]), ("changed", ["C changed"]), ("fixed", ["B is fixed"])]


def test_untagged_notes_stay_a_plain_list():
    assert sections("One sentence.") == [(None, ["One sentence."])]
    assert sections("First • new: Second") == [(None, ["First"]), ("new", ["Second"])]


def test_every_tagged_release_has_matching_sections_in_both_languages():
    for version, en, es in load_release_notes():
        en_shape = [(kind, len(points)) for kind, points in sections(en)]
        es_shape = [(kind, len(points)) for kind, points in sections(es)]
        assert en_shape == es_shape, version


def test_changelog_page_groups_points_by_section():
    path = REPO_ROOT / "scripts" / "auto_update_changelog.py"
    spec = importlib.util.spec_from_file_location("auto_update_changelog", path)
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)
    html = script.create_version_block("9.9.9", "01/01/2030", [("new: A", "new: A es"), ("fixed: B", "fixed: B es")])
    assert html.index('data-en="New features:"') < html.index('data-en="Fixes:"')
    assert 'data-en="A"' in html and 'data-es="B es"' in html and "new:" not in html
    plain = script.create_version_block("9.9.8", "01/01/2030", [("Just this", "Solo esto")])
    assert 'data-en="Changes:"' in plain
