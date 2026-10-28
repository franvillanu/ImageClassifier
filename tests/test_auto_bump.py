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


def run(monkeypatch, published, current="2.0.8", top="2.0.9", argv=()):
    """Run main() with everything external faked. `published` maps a tag to True/False/None."""
    script = load_script()
    calls = []
    monkeypatch.setattr(script, "is_published", lambda tag: published.get(tag))
    monkeypatch.setattr(script, "read_version", lambda: current)
    monkeypatch.setattr(script, "highest_notes_version", lambda: top)
    monkeypatch.setattr(script, "set_version", lambda v: calls.append(("set", v)))
    monkeypatch.setattr(script, "bump_patch", lambda: calls.append(("bump",)))
    monkeypatch.setattr(script, "sync", lambda v: calls.append(("sync",)))
    code = script.main(list(argv))
    return code, calls


def test_notes_ahead_of_unpublished_version_sets_that_version(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": True, "v2.0.9": False})
    assert calls == [("set", "2.0.9"), ("sync",)]


def test_notes_can_jump_to_a_minor_version(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": True, "v2.1.0": False}, top="2.1.0")
    assert calls == [("set", "2.1.0"), ("sync",)]


def test_published_version_without_newer_notes_bumps_patch(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": True}, top="2.0.8")
    assert calls == [("bump",), ("sync",)]


def test_unpublished_current_version_is_kept(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": False}, top="2.0.8")
    assert calls == []


def test_unknown_state_never_changes_anything(monkeypatch):
    _, calls = run(monkeypatch, {}, top="2.0.8")
    assert calls == []


def test_dry_run_never_changes_anything(monkeypatch):
    _, calls = run(monkeypatch, {"v2.0.8": True, "v2.0.9": False}, argv=["--dry-run"])
    assert calls == []


def test_needs_release_exit_codes(monkeypatch):
    code, calls = run(monkeypatch, {"v2.0.9": False}, argv=["--needs-release"])
    assert code == 10 and calls == []
    code, _ = run(monkeypatch, {"v2.0.9": True}, argv=["--needs-release"])
    assert code == 0
    code, _ = run(monkeypatch, {}, argv=["--needs-release"])  # cannot tell: never build blindly
    assert code == 0
    code, _ = run(monkeypatch, {"v2.0.9": False}, top=None, argv=["--needs-release"])
    assert code == 0
