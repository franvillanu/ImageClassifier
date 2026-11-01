import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script():
    path = REPO_ROOT / "scripts" / "auto_bump_version.py"
    spec = importlib.util.spec_from_file_location("auto_bump_version", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_state_from_gh_result():
    script = load_script()
    assert script.release_state(0, "") is True
    assert script.release_state(1, "release not found") is False
    assert script.release_state(1, "HTTP 401: Bad credentials") is None
    assert script.release_state(1, "") is None


# -- which changes count as a release -----------------------------------------------
def test_app_files_trigger_a_release_but_docs_tests_and_scripts_do_not():
    script = load_script()
    for path in ("image_classifier/app.py", "image_classifier/ui/icons.py", "star.ico", "requirements.txt",
                 "Image_Classifier.iss", "image-classifier.py"):
        assert script.is_app_change(path), path
    for path in ("docs/index.html", "tests/test_x.py", "scripts/verify_release.py", ".vscode/pr_create_merge_update.ps1",
                 "README.md", "image_classifier/README.md", "Release.bat"):
        assert not script.is_app_change(path), path


# -- missing notes stop the release -------------------------------------------------
def test_missing_notes_stop_the_release_with_instructions(monkeypatch):
    import pytest
    script = load_script()
    monkeypatch.setattr(script, "notes_for_version", lambda v: None)
    monkeypatch.setattr(script, "commit_subjects_since_release", lambda: [
        "feat: put the star in the About title (#24)", "docs: update guide", "fix(viewer): keep zoom",
        "feat: put the star in the About title"])
    with pytest.raises(SystemExit) as info:
        script.ensure_notes("2.0.12")
    message = str(info.value)
    assert "2.0.12|" in message and "docs/release_notes.txt" in message
    assert "- put the star in the About title" in message and "- keep zoom" in message
    assert "update guide" not in message and message.count("About title") == 1


def test_existing_notes_or_dry_run_never_stop(monkeypatch, capsys):
    script = load_script()
    monkeypatch.setattr(script, "notes_for_version", lambda v: ("2.0.12", "en", "es"))
    script.ensure_notes("2.0.12")
    monkeypatch.setattr(script, "notes_for_version", lambda v: None)
    monkeypatch.setattr(script, "commit_subjects_since_release", lambda: [])
    script.ensure_notes("2.0.12", dry_run=True)
    assert "[WARN]" in capsys.readouterr().out


def test_insert_notes_line_goes_after_the_header_comments():
    script = load_script()
    text = "# one\n# two\n2.0.8|EN|ES\n"
    assert script.insert_notes_line(text, "2.0.9", "New", "Nuevo") == "# one\n# two\n2.0.9|New|Nuevo\n2.0.8|EN|ES\n"


# -- decisions ------------------------------------------------------------------------
def run(monkeypatch, published, current="2.0.8", top="2.0.9", app_changed=False, argv=()):
    """Run main() with everything external faked. `published` maps a tag to True/False/None."""
    script = load_script()
    calls = []
    monkeypatch.setattr(script, "is_published", lambda tag: published.get(tag))
    monkeypatch.setattr(script, "read_version", lambda: current)
    monkeypatch.setattr(script, "highest_notes_version", lambda: top)
    monkeypatch.setattr(script, "app_changed_since_release", lambda: app_changed)
    monkeypatch.setattr(script, "set_version", lambda v: calls.append(("set", v)))
    monkeypatch.setattr(script, "bump_patch", lambda: calls.append(("bump",)))
    monkeypatch.setattr(script, "sync", lambda v: calls.append(("sync",)))
    monkeypatch.setattr(script, "ensure_notes", lambda v, dry_run=False: calls.append(("notes", v)))
    code = script.main(list(argv))
    return code, calls


def test_notes_ahead_of_unpublished_version_sets_that_version(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": True, "v2.0.9": False})
    assert calls == [("set", "2.0.9"), ("sync",)]


def test_notes_can_jump_to_a_minor_version(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": True, "v2.1.0": False}, top="2.1.0")
    assert calls == [("set", "2.1.0"), ("sync",)]


def test_published_version_bumps_patch_and_writes_missing_notes(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": True}, top="2.0.8", app_changed=True)
    assert calls == [("bump",), ("sync",), ("notes", "2.0.8")]  # fake read_version keeps returning 2.0.8


def test_unpublished_current_version_is_kept_but_gets_notes(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": False}, top="2.0.8")
    assert calls == [("notes", "2.0.8")]


def test_unknown_state_never_changes_anything(monkeypatch):
    _, calls = run(monkeypatch, {}, top="2.0.8")
    assert calls == []


def test_dry_run_never_changes_anything(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": True, "v2.0.9": False}, argv=["--dry-run"])
    assert calls == []


def test_needs_release_exit_codes(monkeypatch):
    # notes version not published yet
    assert run(monkeypatch, {"v2.0.9": False}, argv=["--needs-release"])[0] == 10
    # everything published, nothing changed: no release
    assert run(monkeypatch, {"v2.0.9": True}, argv=["--needs-release"])[0] == 0
    # everything published but app files changed since the last release: release
    assert run(monkeypatch, {"v2.0.9": True}, app_changed=True, argv=["--needs-release"])[0] == 10
    # cannot tell whether it is published: never build blindly, even with app changes
    assert run(monkeypatch, {}, app_changed=True, argv=["--needs-release"])[0] == 0
    # no release notes at all but app changed: release (the notes get written)
    assert run(monkeypatch, {}, top=None, app_changed=True, argv=["--needs-release"])[0] == 10
    assert run(monkeypatch, {}, top=None, argv=["--needs-release"])[0] == 0
