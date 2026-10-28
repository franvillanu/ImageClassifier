#!/usr/bin/env python3
"""
Decide the release version from docs/release_notes.txt and the public releases repo.

The newest line in docs/release_notes.txt is the version being released. If it is not published yet,
a release is pending. Used in two ways:

    py scripts/auto_bump_version.py --needs-release
        Exit code 10 if a release is pending (the PR task then runs Release.bat), 0 otherwise.

    py scripts/auto_bump_version.py [--dry-run]
        Make version.txt match the pending release (Release.bat runs this first). If there is no
        newer line but the current version is already published, bump the patch number instead.
"""
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from image_classifier.updates.check import RELEASES_REPO, parse_version  # noqa: E402
from image_classifier.updates.notes import load_release_notes  # noqa: E402
from sync_version import read_version, sync  # noqa: E402

RELEASE_PENDING = 10


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


def highest_notes_version() -> Optional[str]:
    """Newest version that has a customer-facing line, as 'X.Y.Z'."""
    entries = load_release_notes()
    return ".".join(map(str, parse_version(entries[0][0]))) if entries else None


def set_version(version: str) -> None:
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "bump_version.py"), version], check=True, cwd=REPO_ROOT)


def bump_patch() -> None:
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "bump_version.py"), "patch"], check=True, cwd=REPO_ROOT)


def needs_release() -> bool:
    """True when the newest release-notes version is not published yet."""
    top = highest_notes_version()
    if not top:
        return False
    state = is_published(f"v{top}")
    if state is None:
        print(f"[WARNING] Could not check whether v{top} is published (is `gh` installed and logged in?).")
    return state is False


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--needs-release" in args:
        if needs_release():
            print(f"[INFO] Release pending: v{highest_notes_version()} is in release_notes.txt but not published.")
            return RELEASE_PENDING
        return 0

    dry_run = "--dry-run" in args
    current = read_version()
    top = highest_notes_version()

    if top and parse_version(top) > parse_version(current) and is_published(f"v{top}") is False:
        print(f"[INFO] release_notes.txt is ahead ({top} > {current}): setting the version to {top}.")
        if not dry_run:
            set_version(top)
            sync(read_version())
        return 0

    state = is_published(f"v{current}")
    if state is None:
        print(f"[WARNING] Could not check whether v{current} is published (is `gh` installed and logged in?). Version unchanged.")
        return 0
    if state is False:
        print(f"[INFO] v{current} is not published yet: keeping version {current}.")
        return 0

    print(f"[INFO] v{current} is already published: " + ("would bump" if dry_run else "bumping") + " the patch version.")
    if not dry_run:
        bump_patch()
        new_version = read_version()
        sync(new_version)
        print(f"[INFO] Version is now {new_version}. Add its line to docs/release_notes.txt if it is missing.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
