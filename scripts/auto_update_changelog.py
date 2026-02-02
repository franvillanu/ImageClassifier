#!/usr/bin/env python3
"""
Update changelog.html with user-facing release notes (for customers).

Uses docs/release_notes.txt (one sentence per version, EN|ES) so the changelog
shows what changed in the application for users — not internal/DevOps commits.

This script:
1. Reads version from version.txt
2. Reads user-facing note from docs/release_notes.txt (if present)
3. Otherwise uses default "Bug fixes and improvements" / "Correcciones y mejoras"
4. Updates changelog.html

Usage:
    py scripts/auto_update_changelog.py
"""
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_TXT = REPO_ROOT / "version.txt"
RELEASE_NOTES_TXT = REPO_ROOT / "docs" / "release_notes.txt"
CHANGELOG_HTML = REPO_ROOT / "docs" / "changelog.html"


def parse_version() -> str:
    """Read version from version.txt and return 3-digit version (e.g. 2.0.1)."""
    text = VERSION_TXT.read_text(encoding="utf-8")
    m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", text)
    if not m:
        raise SystemExit("[ERROR] Could not parse filevers from version.txt")
    major, minor, build, _rev = m.groups()
    return f"{major}.{minor}.{build}"


def get_today_date() -> str:
    """Return today's date in DD/MM/YYYY format."""
    return datetime.now().strftime("%d/%m/%Y")


def get_user_release_notes(version: str) -> list[tuple[str, str]]:
    """
    Get user-facing release note (EN, ES) for this version from docs/release_notes.txt.
    Format per line: version|English sentence|Spanish sentence
    Returns one entry (or default) so changelog is for customers, not internal commits.
    """
    if not RELEASE_NOTES_TXT.exists():
        return [("Bug fixes and improvements", "Correcciones y mejoras")]
    for line in RELEASE_NOTES_TXT.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 2)
        if len(parts) >= 3 and parts[0].strip() == version:
            return [(parts[1].strip(), parts[2].strip())]
    return [("Bug fixes and improvements", "Correcciones y mejoras")]


def create_version_block(version: str, date: str, entries: list[tuple[str, str]]) -> str:
    """Create HTML for a version block."""
    items = []
    for en, es in entries:
        items.append(
            f'        <li data-en="{en}"\n'
            f'            data-es="{es}">\n'
            f'          {en}\n'
            f'        </li>'
        )
    items_html = "\n".join(items)
    return f"""    <div class="version-block">
      <h2>v{version}</h2>
      <h3>{date}</h3>
      <p class="desc" data-en="Changes:" data-es="Cambios:">Changes:</p>
      <ul>
{items_html}
      </ul>
    </div>

"""


def main() -> int:
    if not CHANGELOG_HTML.exists():
        print(f"[ERROR] Changelog not found: {CHANGELOG_HTML}", file=sys.stderr)
        return 1

    version = parse_version()
    date = get_today_date()
    
    print(f"Version: v{version}")
    print(f"Date: {date}")
    
    # Check if version already exists
    html = CHANGELOG_HTML.read_text(encoding="utf-8")
    if f'<h2>v{version}</h2>' in html:
        print(f"[INFO] Version v{version} already exists in changelog. Updating...")
        # Remove existing version block
        pattern = rf'    <div class="version-block">\s*<h2>v{re.escape(version)}</h2>.*?</div>\s*\n'
        html = re.sub(pattern, '', html, flags=re.DOTALL)
    
    # Use user-facing release note (from release_notes.txt), not git commits
    entries = get_user_release_notes(version)
    print(f"Using user-facing note for v{version} (1 entry)")
    
    new_block = create_version_block(version, date, entries)
    
    # Insert after back link and before first version-block
    marker = "    <!-- Version Blocks -->"
    if marker in html:
        html = html.replace(marker, marker + "\n\n" + new_block, 1)
    else:
        # Insert after back link (before first version-block)
        back_link_pattern = r'(<a class="back-link"[^>]*>.*?</a>\s*\n)'
        match = re.search(back_link_pattern, html, re.DOTALL)
        if match:
            html = html[:match.end()] + "\n" + new_block + html[match.end():]
        else:
            print("[ERROR] Could not find insertion point in changelog.html", file=sys.stderr)
            return 1
    
    CHANGELOG_HTML.write_text(html, encoding="utf-8")
    print(f"\n[SUCCESS] Updated {CHANGELOG_HTML}")
    print(f"Added {len(entries)} user-facing changelog entry/entries")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
