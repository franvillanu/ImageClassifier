#!/usr/bin/env python3
"""
Decide automatically whether a release is needed, and which version it is.

A release is pending when either:
  * the newest version in docs/release_notes.txt is not published yet, or
  * app files changed since the last release commit on main (see APP_PATHS): the patch version is
    bumped. That version needs a hand-written line in release_notes.txt, or the release stops.

Used in two ways:

    py scripts/auto_bump_version.py --needs-release
        Exit code 10 if a release is pending (the PR task then runs Release.bat), 0 otherwise.

    py scripts/auto_bump_version.py [--dry-run]
        Make version.txt (and release_notes.txt) match the pending release. Release.bat runs this
        first. If the current version is already published, the patch number is bumped.
"""
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from image_classifier.updates.check import RELEASES_REPO, parse_version  # noqa: E402
from image_classifier.updates.notes import load_release_notes, notes_for_version, notes_path  # noqa: E402
from sync_version import read_version, sync  # noqa: E402

RELEASE_PENDING = 10

# Changes to these paths are what users get, so they trigger a release. Docs, tests and release
# scripts do not.
APP_PATHS = ("image_classifier/", "image-classifier.py", "star.ico", "requirements.txt", "Image_Classifier.iss")
RELEASE_COMMIT_PATTERN = "^release: prepare v"
NOTE_SUBJECT_RE = re.compile(r"^(feat|fix|perf|refactor)(\([^)]*\))?!?:\s*(.+?)(\s*\(#\d+\))?$", re.IGNORECASE)


# -- release state ------------------------------------------------------------
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


# -- what changed since the last release ----------------------------------------
def git(*args: str) -> str:
    try:
        result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=REPO_ROOT)
    except FileNotFoundError:
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def last_release_commit() -> str:
    """The newest `release: prepare vX.Y.Z` commit on origin/main ('' if there is none)."""
    git("fetch", "origin", "main", "--quiet")
    return git("log", "origin/main", "-n", "1", "--format=%H", "-E", f"--grep={RELEASE_COMMIT_PATTERN}")


def is_app_change(path: str) -> bool:
    return any(path == p or path.startswith(p) for p in APP_PATHS if p) and not path.endswith(".md")


def app_changed_since_release() -> bool:
    base = last_release_commit()
    if not base:
        return False  # no previous release commit to compare with: never release blindly
    return any(is_app_change(p) for p in git("diff", "--name-only", base, "HEAD").splitlines())


def commit_subjects_since_release() -> list[str]:
    base = last_release_commit()
    return git("log", f"{base}..HEAD", "--format=%s").splitlines() if base else []


def insert_notes_line(text: str, version: str, en: str, es: str) -> str:
    """Add `version|en|es` right after the header comments of release_notes.txt."""
    lines = text.split("\n")
    index = 0
    while index < len(lines) and lines[index].startswith("#"):
        index += 1
    lines.insert(index, f"{version}|{en}|{es}")
    return "\n".join(lines)


def missing_notes_message(version: str, subjects: list[str]) -> str:
    """What to tell the person releasing when a version has no customer-facing notes."""
    lines = [
        f"[ERROR] v{version} has no release notes, and they are shown to customers in the app.",
        "Add a line at the top of docs/release_notes.txt (after the # comments), for example:",
        f"  {version}|new: What is new, for customers • fixed: What was fixed"
        "|new: Qué hay de nuevo, para los clientes • fixed: Qué se ha corregido",
        "Separate points with ' • ' and start each with new:, changed: or fixed: (in both languages).",
        "Nothing has been built, merged or published.",
    ]
    picked = [m.group(3).strip() for m in map(NOTE_SUBJECT_RE.match, subjects) if m]
    if picked:
        lines.append("Commits since the last release, for reference only:")
        lines += [f"  - {text}" for text in dict.fromkeys(picked)]
    return "\n".join(lines)


def ensure_notes(version: str, dry_run: bool = False) -> None:
    """Every release needs a hand-written notes line; stop (never invent one) if it is missing.

    Notes generated from commit subjects read like a git log (see v2.0.11), so they are not
    written automatically any more.
    """
    if notes_for_version(version) is not None:
        return
    message = missing_notes_message(version, commit_subjects_since_release())
    if dry_run:
        print(message.replace("[ERROR]", "[WARN]", 1))
        return
    raise SystemExit(message)


# -- actions ----------------------------------------------------------------------
def set_version(version: str) -> None:
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "bump_version.py"), version], check=True, cwd=REPO_ROOT)


def bump_patch() -> None:
    subprocess.run([sys.executable, str(REPO_ROOT / "scripts" / "bump_version.py"), "patch"], check=True, cwd=REPO_ROOT)


def release_pending() -> Optional[str]:
    """Why a release is pending, or None when nothing needs releasing."""
    top = highest_notes_version()
    if top:
        state = is_published(f"v{top}")
        if state is None:
            print(f"[WARNING] Could not check whether v{top} is published (is `gh` installed and logged in?).")
            return None
        if state is False:
            return f"v{top} is in release_notes.txt but not published."
    if app_changed_since_release():
        return "app files changed since the last release."
    return None


def main(argv=None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if "--needs-release" in args:
        reason = release_pending()
        if reason:
            print(f"[INFO] Release pending: {reason}")
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
        ensure_notes(current, dry_run)
        return 0

    print(f"[INFO] v{current} is already published: " + ("would bump" if dry_run else "bumping") + " the patch version.")
    if not dry_run:
        bump_patch()
        new_version = read_version()
        sync(new_version)
        print(f"[INFO] Version is now {new_version}.")
        ensure_notes(new_version)
    return 0


if __name__ == "__main__":
    sys.exit(main())
