#!/usr/bin/env python3
"""
Automatically update changelog.html by extracting changes from git commits.

This script:
1. Reads version from version.txt
2. Extracts commit messages since last release (or uses default)
3. Updates changelog.html automatically
4. Returns changelog entries for website update

Usage:
    py scripts/auto_update_changelog.py
"""
import re
import subprocess
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


def get_git_commits_since_last_release() -> list[str]:
    """Extract commit messages since the last version tag or main branch."""
    try:
        # Try to find the last version tag
        result = subprocess.run(
            ["git", "describe", "--tags", "--abbrev=0"],
            capture_output=True,
            text=True,
            cwd=REPO_ROOT,
        )
        
        if result.returncode == 0 and result.stdout.strip():
            # Get commits since last tag
            since_tag = result.stdout.strip()
            result = subprocess.run(
                ["git", "log", f"{since_tag}..HEAD", "--pretty=%s", "--no-merges"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
        else:
            # No tags found, get commits since main branch
            result = subprocess.run(
                ["git", "log", "main..HEAD", "--pretty=%s", "--no-merges"],
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
            )
        
        if result.returncode == 0 and result.stdout.strip():
            commits = [line.strip() for line in result.stdout.strip().split("\n") if line.strip()]
            # Filter out release commits and merge commits
            commits = [c for c in commits if not c.startswith("release:") and not c.startswith("Merge")]
            return commits[:10]  # Limit to 10 most recent
    except Exception:
        pass
    
    return []


def create_changelog_entries(commits: list[str]) -> list[tuple[str, str]]:
    """Convert commit messages to changelog entries (EN, ES)."""
    entries = []
    
    for commit in commits:
        # Clean up commit message
        commit = commit.strip()
        
        # Skip if it's a release commit
        if commit.startswith("release:"):
            continue
        
        # Remove type prefixes (feat:, fix:, etc.)
        commit_clean = re.sub(r"^(feat|fix|refactor|docs|chore|style|test|perf):\s*", "", commit, flags=re.IGNORECASE)
        
        # Capitalize first letter
        if commit_clean:
            commit_clean = commit_clean[0].upper() + commit_clean[1:] if len(commit_clean) > 1 else commit_clean.upper()
        
        # Use same text for EN and ES (can be improved later with translation)
        entries.append((commit_clean, commit_clean))
    
    # If no commits found, use default entry
    if not entries:
        entries = [
            ("Bug fixes and improvements", "Correcciones y mejoras")
        ]
    
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
    
    print(f"Version: v{version}")
    print(f"Date: {date}")
    
    # Check if version already exists
    html = CHANGELOG_HTML.read_text(encoding="utf-8")
    if f'<h2>v{version}</h2>' in html:
        print(f"[INFO] Version v{version} already exists in changelog. Updating...")
        # Remove existing version block
        pattern = rf'    <div class="version-block">\s*<h2>v{re.escape(version)}</h2>.*?</div>\s*\n'
        html = re.sub(pattern, '', html, flags=re.DOTALL)
    
    # Get commits and create entries
    commits = get_git_commits_since_last_release()
    print(f"Found {len(commits)} commits since last release")
    entries = create_changelog_entries(commits)
    
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
    print(f"Added {len(entries)} changelog entries")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
