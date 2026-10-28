"""The updater compares __version__, so every copy of the version must agree."""
import importlib.util
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_script(name):
    path = REPO_ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_all_version_copies_agree():
    version = load_script("sync_version").read_version()
    from image_classifier import __version__

    assert __version__ == version
    assert json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))["version"] == version
    pyproject = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    assert re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject).group(1) == version
    iss = (REPO_ROOT / "Image_Classifier.iss").read_text(encoding="utf-8")
    assert re.search(r'MyAppVersion\s+"([^"]+)"', iss).group(1) == version


def test_sync_writes_all_targets(tmp_path):
    script = load_script("sync_version")
    script.INIT_PY = tmp_path / "__init__.py"
    script.PYPROJECT = tmp_path / "pyproject.toml"
    script.PACKAGE_JSON = tmp_path / "package.json"
    script.INIT_PY.write_text('__version__ = "1.0.0"\n', encoding="utf-8")
    script.PYPROJECT.write_text('[project]\nname = "x"\nversion = "1.0"\n', encoding="utf-8")
    script.PACKAGE_JSON.write_text('{"name": "x", "version": "1.0.0"}\n', encoding="utf-8")

    assert sorted(script.sync("2.1.3")) == ["__init__.py", "package.json", "pyproject.toml"]
    assert script.sync("2.1.3") == []
    assert '__version__ = "2.1.3"' in script.INIT_PY.read_text(encoding="utf-8")
    assert 'version = "2.1.3"' in script.PYPROJECT.read_text(encoding="utf-8")
    assert json.loads(script.PACKAGE_JSON.read_text(encoding="utf-8"))["version"] == "2.1.3"


def test_release_body_fills_version_and_appends_install_doc():
    script = load_script("create_github_release")
    body = script.release_body("## Version 2.0.8\n\n- Fix", "Get ImageClassifierSetup_v{version}.exe", "2.0.8")
    assert body.startswith("## Version 2.0.8")
    assert "ImageClassifierSetup_v2.0.8.exe" in body
    assert "{version}" not in body


def test_publish_script_targets_releases_repo_and_has_no_fallback_installer(tmp_path):
    script = load_script("create_github_release")
    assert script.RELEASES_REPO == "franvillanu/imageclassifier-releases"
    script.OUTPUT_DIR = tmp_path
    (tmp_path / "ImageClassifierSetup_v1.0.0.exe").write_bytes(b"old")
    assert script.find_installer_file("2.0.8") is None


def test_bump_updates_embedded_version_strings(tmp_path):
    script = load_script("bump_version")
    version_txt = tmp_path / "version.txt"
    version_txt.write_text(
        "filevers=(2, 0, 7, 0),\nprodvers=(2, 0, 7, 0),\n"
        "StringStruct('FileVersion', '2.0.7'),\nStringStruct('ProductVersion', '2.0.7')\n",
        encoding="utf-8",
    )
    script.update_version_txt(version_txt, (2, 0, 7, 0), (2, 0, 8, 0))
    text = version_txt.read_text(encoding="utf-8")
    assert "(2, 0, 8, 0)" in text
    assert text.count("'2.0.8'") == 2 and "2.0.7" not in text
