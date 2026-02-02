#!/usr/bin/env python3
"""
Update website files (index.html) with latest version info from version.txt and changelog.html.
Run this after updating changelog to sync the website.
"""
import re
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_TXT = REPO_ROOT / "version.txt"
CHANGELOG_HTML = REPO_ROOT / "docs" / "changelog.html"
INDEX_HTML = REPO_ROOT / "docs" / "index.html"
STAR_ICO = REPO_ROOT / "star.ico"


def parse_version() -> tuple[str, str]:
    """Read version from version.txt and return (short, full) e.g. ('2.0', '2.0.0.0')."""
    text = VERSION_TXT.read_text(encoding="utf-8")
    m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", text)
    if not m:
        raise SystemExit("[ERROR] Could not parse filevers from version.txt")
    major, minor, build, rev = m.groups()
    return f"{major}.{minor}", f"{major}.{minor}.{build}.{rev}"


def get_latest_changelog_entry() -> tuple[str, str, list[tuple[str, str]]]:
    """Extract latest version, date, and changelog items (EN, ES) from changelog.html."""
    html = CHANGELOG_HTML.read_text(encoding="utf-8")
    
    # Find first version block
    pattern = r'<div class="version-block">\s*<h2>v(\d+\.\d+)</h2>\s*<h3>(\d{2}/\d{2}/\d{4})</h3>.*?<ul>(.*?)</ul>'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return ("2.0", "02/02/2026", [("Bug fixes and improvements", "Correcciones y mejoras")])
    
    version = match.group(1)
    date_str = match.group(2)
    items_html = match.group(3)
    
    # Extract both English and Spanish text from each <li>
    items = []
    for li_match in re.finditer(r'<li[^>]*data-en="([^"]*)"[^>]*data-es="([^"]*)"', items_html):
        en_text = li_match.group(1)
        es_text = li_match.group(2)
        items.append((en_text, es_text))
    
    if not items:
        items = [("Bug fixes and improvements", "Correcciones y mejoras")]
    
    return version, date_str, items


def format_date_for_index(date_str: str) -> tuple[str, str]:
    """Convert DD/MM/YYYY to English and Spanish date formats."""
    try:
        dt = datetime.strptime(date_str, "%d/%m/%Y")
        # English: "February 2, 2026"
        en_date = dt.strftime("%B %d, %Y").replace(" 0", " ")  # Remove leading zero from day
        # Spanish: "2 de Febrero de 2026"
        months_es = ["enero", "febrero", "marzo", "abril", "mayo", "junio",
                     "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
        day = dt.day
        month_es = months_es[dt.month - 1]
        year = dt.year
        es_date = f"{day} de {month_es} de {year}"
        return en_date, es_date
    except:
        return date_str, date_str


def update_index_html(version_short: str, version_full: str, changelog_date: str, changelog_items: list[tuple[str, str]]) -> None:
    """Update index.html with version info and changelog."""
    html = INDEX_HTML.read_text(encoding="utf-8")
    
    # Update version number
    html = re.sub(r'<span id="versionNumber">[^<]+</span>', f'<span id="versionNumber">{version_short}</span>', html)
    
    # Update publish date (with data-en and data-es for localization)
    en_date, es_date = format_date_for_index(changelog_date)
    html = re.sub(
        r'<span id="publishDate">[^<]+</span>',
        f'<span id="publishDate" data-en="{en_date}" data-es="{es_date}">{en_date}</span>',
        html
    )
    
    # Update changelog items in "What's New" list with data-en/data-es attributes
    items_html = ""
    for en_text, es_text in changelog_items[:3]:  # Max 3 items
        # Escape quotes in the text
        en_escaped = en_text.replace('"', '&quot;')
        es_escaped = es_text.replace('"', '&quot;')
        items_html += f'            <li id="whatsNewItem{len(items_html.split(chr(10))) + 1}" data-en="{en_escaped}" data-es="{es_escaped}">{en_text}</li>\n'
    
    # Find and replace the <ul id="whatsNewList"> content
    pattern = r'(<ul id="whatsNewList">)(.*?)(</ul>)'
    html = re.sub(pattern, r'\1\n' + items_html.rstrip() + '\n          \3', html, flags=re.DOTALL)
    
    # Remove any control characters (except newlines and tabs)
    import re as re_module
    html = re_module.sub(r'[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]', '', html)
    
    INDEX_HTML.write_text(html, encoding="utf-8", newline='\n')
    print(f"[INFO] Updated {INDEX_HTML}")


def copy_star_ico() -> None:
    """Copy star.ico to docs/ if it doesn't exist."""
    dest = REPO_ROOT / "docs" / "star.ico"
    if STAR_ICO.exists() and not dest.exists():
        import shutil
        shutil.copy2(STAR_ICO, dest)
        print(f"[INFO] Copied star.ico to docs/")


def main() -> int:
    if not INDEX_HTML.exists():
        print(f"[ERROR] index.html not found: {INDEX_HTML}", file=sys.stderr)
        return 1
    if not CHANGELOG_HTML.exists():
        print(f"[WARNING] changelog.html not found: {CHANGELOG_HTML}", file=sys.stderr)
    
    version_short, version_full = parse_version()
    changelog_version, changelog_date, changelog_items = get_latest_changelog_entry()
    
    print(f"Version: {version_short} (full: {version_full})")
    print(f"Latest changelog: v{changelog_version} ({changelog_date})")
    print(f"Changelog items: {len(changelog_items)}")
    
    update_index_html(version_short, version_full, changelog_date, changelog_items)
    copy_star_ico()
    
    print("[SUCCESS] Website files updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
