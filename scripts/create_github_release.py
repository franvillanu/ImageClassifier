#!/usr/bin/env python3
"""
Publish the installer to the public releases-only repo (franvillanu/imageclassifier-releases).

This script:
1. Reads the version from version.txt and checks it matches image_classifier.__version__
2. Builds release notes from docs/changelog.html plus docs/releases/installer.md
3. Creates the release (or edits it and re-uploads the asset if it already exists)

The source repo stays separate: the app and the website only ever see the releases repo.
Requires the GitHub CLI, logged in once with `gh auth login`. No token files, no `requests`.

Usage:
    py scripts/create_github_release.py
"""
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_TXT = REPO_ROOT / "version.txt"
INIT_PY = REPO_ROOT / "image_classifier" / "__init__.py"
CHANGELOG_HTML = REPO_ROOT / "docs" / "changelog.html"
INSTALLER_DOC = REPO_ROOT / "docs" / "releases" / "installer.md"
OUTPUT_DIR = REPO_ROOT / "Output"

RELEASES_REPO = "franvillanu/imageclassifier-releases"


def parse_version() -> str:
    """Read version from version.txt and return 3-digit version (major.minor.patch) e.g. '2.0.1'."""
    text = VERSION_TXT.read_text(encoding="utf-8")
    m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", text)
    if not m:
        raise SystemExit("[ERROR] Could not parse filevers from version.txt")
    major, minor, build, _rev = m.groups()
    return f"{major}.{minor}.{build}"


def package_version() -> Optional[str]:
    """The version baked into the app (what the updater compares against)."""
    m = re.search(r'__version__\s*=\s*"([^"]+)"', INIT_PY.read_text(encoding="utf-8"))
    return m.group(1) if m else None


def get_release_notes() -> str:
    """Extract release notes from changelog.html for the latest version."""
    if not CHANGELOG_HTML.exists():
        return "See changelog.html for details."

    html = CHANGELOG_HTML.read_text(encoding="utf-8")
    pattern = r'<div class="version-block">\s*<h2>v(\d+\.\d+(?:\.\d+)?)</h2>\s*<h3>(\d{2}/\d{2}/\d{4})</h3>.*?<ul>(.*?)</ul>'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return "See changelog.html for details."

    version, date_str, items_html = match.groups()
    items = [f"- {m.group(1)}" for m in re.finditer(r'<li[^>]*data-en="([^"]*)"', items_html)]
    if not items:
        return "See changelog.html for details."
    return f"## Version {version} ({date_str})\n\n" + "\n".join(items)


def release_body(notes: str, installer_doc: str, version: str) -> str:
    """Release notes followed by the install steps, with {version} filled in."""
    doc = installer_doc.replace("{version}", version).strip()
    return f"{notes}\n\n{doc}\n" if doc else f"{notes}\n"


def find_installer_file(version: str) -> Optional[Path]:
    """Exactly this version's installer; never an older build under a newer tag."""
    installer = OUTPUT_DIR / f"ImageClassifierSetup_v{version}.exe"
    return installer if installer.exists() else None


def gh(*args: str, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args, "--repo", RELEASES_REPO], cwd=REPO_ROOT, check=check)


def release_exists(tag: str) -> bool:
    result = subprocess.run(
        ["gh", "release", "view", tag, "--repo", RELEASES_REPO],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    return result.returncode == 0


def main() -> int:
    version = parse_version()
    tag = f"v{version}"

    baked = package_version()
    if baked != version:
        print(
            f"[ERROR] image_classifier/__init__.py has __version__ = {baked!r} but version.txt is {version}.\n"
            "  Run: py scripts/sync_version.py (the app would offer this update forever).",
            file=sys.stderr,
        )
        return 1

    installer = find_installer_file(version)
    if not installer:
        print(
            f"[ERROR] Installer not found: {OUTPUT_DIR / f'ImageClassifierSetup_v{version}.exe'}\n"
            "  Run Release.bat first.",
            file=sys.stderr,
        )
        return 1

    installer_doc = INSTALLER_DOC.read_text(encoding="utf-8") if INSTALLER_DOC.exists() else ""
    body = release_body(get_release_notes(), installer_doc, version)
    notes_file = OUTPUT_DIR / "release_notes.md"
    notes_file.write_text(body, encoding="utf-8")

    print(f"Version: {version}\nTag: {tag}\nInstaller: {installer.name}\nRepo: {RELEASES_REPO}")
    try:
        if release_exists(tag):
            print(f"[INFO] Release {tag} exists: updating notes and re-uploading the installer.")
            gh("release", "edit", tag, "--notes-file", str(notes_file))
            gh("release", "upload", tag, str(installer), "--clobber")
        else:
            gh(
                "release", "create", tag, str(installer),
                "--title", f"Image Classifier {version}",
                "--notes-file", str(notes_file),
                "--latest",
            )
    except FileNotFoundError:
        print("[ERROR] GitHub CLI (gh) not found. Install it and run `gh auth login`.", file=sys.stderr)
        return 1
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] gh failed with exit code {e.returncode}.", file=sys.stderr)
        return 1

    print("\n[SUCCESS] Release complete!")
    print(f"  Release URL: https://github.com/{RELEASES_REPO}/releases/tag/{tag}")
    print(f"  Download URL: https://github.com/{RELEASES_REPO}/releases/download/{tag}/{installer.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
