"""Tests for release-note and website generation."""
import importlib.util
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script(name):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_missing_release_notes_stop_release(tmp_path):
    script = load_script("auto_update_changelog")
    script.RELEASE_NOTES_TXT = tmp_path / "release_notes.txt"
    script.RELEASE_NOTES_TXT.write_text(
        "2.0.3|Previous release|Versión anterior\n",
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="Missing customer-facing release notes"):
        script.get_user_release_notes("2.0.4")


def test_update_website_repairs_list_and_updates_attributed_date(tmp_path):
    script = load_script("update_website")
    script.INDEX_HTML = tmp_path / "index.html"
    script.INDEX_HTML.write_text(
        """
        <span id="versionNumber">2.0.3</span>
        <ul id="whatsNewList">
          <li id="whatsNewItem1">Old note</li>
        </div>
        <a id="downloadLink" href="old.exe"></a>
        <span id="publishDate" data-en="Old date" data-es="Fecha anterior">Old date</span>
        """,
        encoding="utf-8",
    )

    script.update_index_html(
        "2.0.4",
        "07/06/2026",
        [("Added HEIC support.", "Añadido soporte HEIC.")],
    )

    html = script.INDEX_HTML.read_text(encoding="utf-8")
    assert '<span id="versionNumber">2.0.4</span>' in html
    assert 'data-en="June 7, 2026"' in html
    assert 'data-es="7 de junio de 2026"' in html
    assert '<li id="whatsNewItem1"' in html
    assert "Added HEIC support." in html
    assert "</ul>" in html
    assert "ImageClassifierSetup_v2.0.4.exe" in html


def test_update_website_rejects_changelog_without_items(tmp_path):
    script = load_script("update_website")
    script.CHANGELOG_HTML = tmp_path / "changelog.html"
    script.CHANGELOG_HTML.write_text(
        """
        <div class="version-block">
          <h2>v2.0.4</h2>
          <h3>07/06/2026</h3>
          <ul></ul>
        </div>
        """,
        encoding="utf-8",
    )

    with pytest.raises(SystemExit, match="no customer-facing notes"):
        script.get_latest_changelog_entry()
