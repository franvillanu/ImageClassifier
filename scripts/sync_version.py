#!/usr/bin/env python3
"""
Sync the 3-part version from version.txt (filevers=) into the other places that
carry it: image_classifier/__init__.py, pyproject.toml and package.json.

The in-app updater compares image_classifier.__version__ with the latest release,
so a stale __version__ would make the app offer the same update forever.
Run from Release.bat right after the version is read.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_TXT = REPO_ROOT / "version.txt"
INIT_PY = REPO_ROOT / "image_classifier" / "__init__.py"
PYPROJECT = REPO_ROOT / "pyproject.toml"
PACKAGE_JSON = REPO_ROOT / "package.json"


def read_version() -> str:
    text = VERSION_TXT.read_text(encoding="utf-8")
    m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", text)
    if not m:
        raise SystemExit("[ERROR] Could not parse filevers from version.txt")
    major, minor, build, _rev = m.groups()
    return f"{major}.{minor}.{build}"


def replace_first(path: Path, pattern: str, replacement: str) -> bool:
    """Replace the first match of pattern in path; returns True if the file changed."""
    if not path.exists():
        return False
    raw = path.read_bytes().decode("utf-8")
    new, count = re.subn(pattern, lambda m: m.group(1) + replacement + m.group(2), raw, count=1)
    if count == 0:
        raise SystemExit(f"[ERROR] No version found to update in {path.name}")
    if new == raw:
        return False
    path.write_bytes(new.encode("utf-8"))
    return True


def sync(version: str) -> list[str]:
    changed = []
    targets = [
        (INIT_PY, r'(__version__\s*=\s*")[^"]+(")'),
        (PYPROJECT, r'(?m)(^version\s*=\s*")[^"]+(")'),
        (PACKAGE_JSON, r'("version"\s*:\s*")[^"]+(")'),
    ]
    for path, pattern in targets:
        if replace_first(path, pattern, version):
            changed.append(path.name)
    return changed


def main() -> int:
    version = read_version()
    changed = sync(version)
    print(f"[INFO] Version {version}: " + (", ".join(changed) + " updated" if changed else "already in sync"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
