#!/usr/bin/env python3
"""
Verify that a release really happened, instead of trusting that every step printed OK.

Checks, for the version in version.txt:
  1. image_classifier.__version__ matches (what the updater compares against)
  2. the release exists in the public releases repo and has the installer asset
  3. the published installer's SHA-256 equals Output/ImageClassifierSetup_v{version}.exe
  4. the release body carries the hidden bilingual notes the in-app updater shows

Exit code 0 when everything matches, 1 otherwise (problems are printed).

Usage:
    py scripts/verify_release.py
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Callable, Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from image_classifier.updates.check import RELEASES_REPO  # noqa: E402
from image_classifier.updates.notes import parse_notes_marker  # noqa: E402
from sync_version import INIT_PY, read_version  # noqa: E402

OUTPUT_DIR = REPO_ROOT / "Output"


def fetch_release(tag: str) -> Optional[dict]:
    """The release as {'assets': [...], 'body': str}, or None if it does not exist."""
    try:
        result = subprocess.run(
            ["gh", "release", "view", tag, "--repo", RELEASES_REPO, "--json", "assets,body"],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
    except FileNotFoundError:
        return None
    return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else None


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def baked_version() -> Optional[str]:
    import re

    m = re.search(r'__version__\s*=\s*"([^"]+)"', INIT_PY.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def verify(
    version: str,
    installer: Path,
    release: Optional[dict],
    baked: Optional[str],
    sha256: Callable[[Path], str] = sha256_of,
) -> list[str]:
    """Problems found (empty list means the release is exactly what was built)."""
    problems = []
    tag = f"v{version}"
    if baked != version:
        problems.append(f"image_classifier/__init__.py says {baked!r} but version.txt says {version}.")
    if release is None:
        return problems + [f"{tag} is not published in {RELEASES_REPO}."]

    name = f"ImageClassifierSetup_v{version}.exe"
    asset = next((a for a in release.get("assets", []) if a.get("name") == name), None)
    if asset is None:
        problems.append(f"{tag} has no {name} asset.")
    elif not installer.exists():
        problems.append(f"Local installer {installer} is missing, so the published one cannot be compared.")
    else:
        published = asset.get("digest") or ""
        local = "sha256:" + sha256(installer)
        if not published:
            problems.append(f"{tag}'s {name} has no checksum to compare.")
        elif published.lower() != local.lower():
            problems.append(f"The published {name} is not the installer that was built (checksums differ).")
    if parse_notes_marker(release.get("body")) is None:
        problems.append(f"{tag} has no in-app release notes (add the version's line to docs/release_notes.txt).")
    return problems


def main() -> int:
    version = read_version()
    installer = OUTPUT_DIR / f"ImageClassifierSetup_v{version}.exe"
    problems = verify(version, installer, fetch_release(f"v{version}"), baked_version())
    if problems:
        print(f"[ERROR] Release v{version} did NOT verify:", file=sys.stderr)
        for problem in problems:
            print(f"  - {problem}", file=sys.stderr)
        return 1
    print(f"[SUCCESS] Release v{version} verified: published installer matches the build, notes included.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
