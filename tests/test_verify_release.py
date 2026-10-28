import importlib.util
from pathlib import Path

from image_classifier.updates.notes import notes_marker

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script():
    path = REPO_ROOT / "scripts" / "verify_release.py"
    spec = importlib.util.spec_from_file_location("verify_release", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


NAME = "ImageClassifierSetup_v2.0.9.exe"


def good_release(digest="sha256:abc"):
    return {"assets": [{"name": NAME, "digest": digest}], "body": "## 2.0.9\n\n" + notes_marker("New", "Nuevo")}


def check(tmp_path, release, baked="2.0.9", installer_exists=True, local_hash="abc"):
    script = load_script()
    installer = tmp_path / NAME
    if installer_exists:
        installer.write_bytes(b"x")
    return script.verify("2.0.9", installer, release, baked, sha256=lambda p: local_hash)


def test_everything_matching_passes(tmp_path):
    assert check(tmp_path, good_release()) == []


def test_not_published_fails(tmp_path):
    problems = check(tmp_path, None)
    assert len(problems) == 1 and "not published" in problems[0]


def test_published_installer_from_another_build_fails(tmp_path):
    """The v2.0.8 incident: same name, different file."""
    problems = check(tmp_path, good_release(digest="sha256:other"))
    assert any("checksums differ" in p for p in problems)


def test_missing_notes_marker_fails(tmp_path):
    release = good_release()
    release["body"] = "plain body"
    assert any("release notes" in p for p in check(tmp_path, release))


def test_missing_asset_or_checksum_fails(tmp_path):
    assert any("no ImageClassifierSetup" in p for p in check(tmp_path, {"assets": [], "body": notes_marker("a", "b")}))
    assert any("no checksum" in p for p in check(tmp_path, good_release(digest="")))


def test_stale_baked_version_fails(tmp_path):
    assert any("__init__.py" in p for p in check(tmp_path, good_release(), baked="2.0.8"))


def test_missing_local_installer_fails(tmp_path):
    assert any("missing" in p for p in check(tmp_path, good_release(), installer_exists=False))
