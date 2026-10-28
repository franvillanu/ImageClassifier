#!/usr/bin/env python3
"""
Bump the patch version automatically when the current one is already published.

Release.bat runs this first. If v{version} already exists in the public releases repo, building again
would republish the same version (the updater would never offer it, and the PR task would skip it),
so the patch number is bumped. If it is not published yet, nothing changes.

Usage:
    py scripts/auto_bump_version.py            # bump when needed
    py scripts/auto_bump_version.py --dry-run  # only report
"""
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from image_classifier.updates.check import RELEASES_REPO  # noqa: E402
from sync_version import read_version, sync  # noqa: E402


def release_state(returncode: int, stderr: str) -> Optional[bool]:
    """True: published, False: not published, None: could not tell (no gh, no network, no login)."""
    if returncode == 0:
        return True
    if "not found" in (stderr or "").lower():
        return False
    return None


def is_published(tag: str) -> Optional[bool]:
    try:
        result = subprocess.run(
            ["gh", "release", "view", tag, "--repo", RELEASES_REPO],
            capture_output=True, text=True, cwd=REPO_ROOT,
        )
    except FileNotFoundError:
        return None
    return release_state(result.returncode, result.stderr)


def bump_patch() -> None:
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "bump_version.py"), "patch"], check=True, cwd=REPO_ROOT)


def main(argv=None) -> int:
    dry_run = "--dry-run" in (argv if argv is not None else sys.argv[1:])
    version = read_version()
    state = is_published(f"v{version}")

    if state is None:
        print(f"[WARNING] Could not check whether v{version} is published (is `gh` installed and logged in?). Version unchanged.")
        return 0
    if state is False:
        print(f"[INFO] v{version} is not published yet: keeping version {version}.")
        return 0

    if dry_run:
        print(f"[INFO] v{version} is already published: would bump the patch version.")
        return 0
    print(f"[INFO] v{version} is already published: bumping the patch version.")
    bump_patch()
    new_version = read_version()
    sync(new_version)
    print(f"[INFO] Version is now {new_version}. Add its line to docs/release_notes.txt if it is missing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
