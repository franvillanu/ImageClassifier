#!/usr/bin/env python3
"""
Add a new version entry to changelog.html. Reads version from version.txt and prompts
for changelog entries. Inserts the new entry at the top of the version blocks.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_TXT = REPO_ROOT / "version.txt"
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


def parse_entries_from_args(args: list[str]) -> list[tuple[str, str]]:
    """Parse entries from command-line args in format 'EN|ES'."""
    entries = []
    for arg in args:
        if '|' in arg:
            en, es = arg.split('|', 1)
            entries.append((en.strip(), es.strip()))
        else:
            entries.append((arg.strip(), arg.strip()))
    return entries


def prompt_changelog_entries() -> list[tuple[str, str]]:
    """Prompt user for changelog entries (English and Spanish)."""
    entries = []
    print("\nEnter changelog entries (press Enter with empty line to finish):")
    print("For each entry, provide:")
    print("  1. English text")
    print("  2. Spanish text")
    print()
    i = 1
    while True:
        en = input(f"Entry {i} (English): ").strip()
        if not en:
            break
        es = input(f"Entry {i} (Spanish): ").strip()
        if not es:
            print("[WARNING] Spanish text empty, using English text")
            es = en
        entries.append((en, es))
        i += 1
    if not entries:
        print("[WARNING] No entries provided. Using placeholder.")
        entries = [("Bug fixes and improvements", "Correcciones y mejoras")]
    return entries


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
    print(f"\nVersion: v{version}")
    print(f"Date: {date}")

    # Check if version already exists
    html = CHANGELOG_HTML.read_text(encoding="utf-8")
    if f'<h2>v{version}</h2>' in html:
        print(f"[WARNING] Version v{version} already exists in changelog.")
        # If args provided, auto-update; otherwise prompt
        if len(sys.argv) > 1:
            print("Auto-updating (entries provided via command line)...")
        else:
            response = input("Update it? (y/N): ").strip().lower()
            if response != 'y':
                print("Aborted.")
                return 0
        # Remove existing version block
        pattern = rf'    <div class="version-block">\s*<h2>v{re.escape(version)}</h2>.*?</div>\s*\n'
        html = re.sub(pattern, '', html, flags=re.DOTALL)

    # Use command-line args if provided, otherwise prompt
    if len(sys.argv) > 1:
        entries = parse_entries_from_args(sys.argv[1:])
    else:
        entries = prompt_changelog_entries()
    new_block = create_version_block(version, date, entries)

    # Insert after back link and before first version-block
    # Try "<!-- Version Blocks -->" marker first, then fallback to back link
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
