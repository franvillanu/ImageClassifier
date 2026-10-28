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


def run(monkeypatch, state, argv=()):
    script = load_script()
    calls = []
    monkeypatch.setattr(script, "is_published", lambda tag: state)
    monkeypatch.setattr(script, "bump_patch", lambda: calls.append("bump"))
    monkeypatch.setattr(script, "sync", lambda version: calls.append("sync"))
    script.main(list(argv))
    return calls


def test_bumps_only_when_current_version_is_published(monkeypatch):
    assert run(monkeypatch, True) == ["bump", "sync"]
    assert run(monkeypatch, False) == []


def test_unknown_state_never_bumps(monkeypatch):
    assert run(monkeypatch, None) == []


def test_dry_run_never_bumps(monkeypatch):
    assert run(monkeypatch, True, ["--dry-run"]) == []
