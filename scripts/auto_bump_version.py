#!/usr/bin/env python3
"""
Decide automatically whether a release is needed, and which version it is.

A release is pending when either:
  * the newest version in docs/release_notes.txt is not published yet, or
  * app files changed since the last release commit on main (see APP_PATHS): the patch version is
    bumped and, if the version has no line in release_notes.txt, one is written from the commit subjects.

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
FALLBACK_NOTE = "Improvements and fixes."


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


def note_from_subjects(subjects: list[str]) -> str:
    """One customer-facing sentence from conventional-commit subjects (feat/fix/perf/refactor only)."""
    parts = []
    for subject in subjects:
        match = NOTE_SUBJECT_RE.match(subject.strip())
        if match:
            text = match.group(3).strip().rstrip(".")
            if text and text[0].upper() + text[1:] not in parts:
                parts.append(text[0].upper() + text[1:])
    return "; ".join(parts) + "." if parts else FALLBACK_NOTE


def insert_notes_line(text: str, version: str, en: str, es: str) -> str:
    """Add `version|en|es` right after the header comments of release_notes.txt."""
    lines = text.split("\n")
    index = 0
    while index < len(lines) and lines[index].startswith("#"):
        index += 1
    lines.insert(index, f"{version}|{en}|{es}")
    return "\n".join(lines)


def ensure_notes(version: str, dry_run: bool = False) -> None:
    """Every release needs its notes line; write a placeholder from the commits if it is missing."""
    if notes_for_version(version) is not None:
        return
    note = note_from_subjects(commit_subjects_since_release())
    print(f"[INFO] No release note for {version}: writing one from the commits: {note}")
    if dry_run:
        return
    path = notes_path()
    raw = path.read_bytes().decode("utf-8")
    newline = "\r\n" if "\r\n" in raw else "\n"
    updated = insert_notes_line(raw.replace("\r\n", "\n"), version, note, note)
    path.write_bytes(updated.replace("\n", newline).encode("utf-8"))


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
