#!/usr/bin/env python3
"""
Create a GitHub Release and upload the installer as an asset.

This script:
1. Reads version from version.txt
2. Extracts release notes from changelog.html
3. Creates a GitHub Release with tag v{VERSION}
4. Uploads the installer .exe file from Output/ as a release asset

Requires:
- GitHub Personal Access Token (PAT) with 'repo' scope
- Set GITHUB_TOKEN environment variable or create .github_token file (gitignored)
- Install: pip install requests

Usage:
    py scripts/create_github_release.py
"""
import os
import re
import sys
from pathlib import Path
from typing import Optional

try:
    import requests
except ImportError:
    print(
        "[ERROR] requests library not installed.\n"
        "  Install with: py -m pip install requests",
        file=sys.stderr,
    )
    sys.exit(1)

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_TXT = REPO_ROOT / "version.txt"
CHANGELOG_HTML = REPO_ROOT / "docs" / "changelog.html"
OUTPUT_DIR = REPO_ROOT / "Output"
GITHUB_TOKEN_FILE = REPO_ROOT / ".github_token"

# GitHub API endpoints
REPO_OWNER = "franvillanu"
REPO_NAME = "ImageClassifier"
GITHUB_API_BASE = "https://api.github.com"


def get_github_token() -> Optional[str]:
    """Get GitHub token from env var or .github_token file."""
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return token.strip()
    if GITHUB_TOKEN_FILE.exists():
        return GITHUB_TOKEN_FILE.read_text(encoding="utf-8").strip()
    return None


def parse_version() -> tuple[str, str]:
    """Read version from version.txt and return (short, full) e.g. ('2.0', '2.0.0.0')."""
    text = VERSION_TXT.read_text(encoding="utf-8")
    m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", text)
    if not m:
        raise SystemExit("[ERROR] Could not parse filevers from version.txt")
    major, minor, build, rev = m.groups()
    return f"{major}.{minor}", f"{major}.{minor}.{build}.{rev}"


def get_release_notes() -> str:
    """Extract release notes from changelog.html for the latest version."""
    if not CHANGELOG_HTML.exists():
        return "See changelog.html for details."
    
    html = CHANGELOG_HTML.read_text(encoding="utf-8")
    
    # Find first version block
    pattern = r'<div class="version-block">\s*<h2>v(\d+\.\d+)</h2>\s*<h3>(\d{2}/\d{2}/\d{4})</h3>.*?<ul>(.*?)</ul>'
    match = re.search(pattern, html, re.DOTALL)
    if not match:
        return "See changelog.html for details."
    
    version = match.group(1)
    date_str = match.group(2)
    items_html = match.group(3)
    
    # Extract English text from each <li>
    items = []
    for li_match in re.finditer(r'<li[^>]*data-en="([^"]*)"', items_html):
        en_text = li_match.group(1)
        items.append(f"- {en_text}")
    
    if not items:
        return "See changelog.html for details."
    
    notes = f"## Version {version} ({date_str})\n\n" + "\n".join(items)
    return notes


def find_installer_file(version_full: str) -> Optional[Path]:
    """Find the installer .exe file in Output/ directory."""
    expected_name = f"ImageClassifierSetup_v{version_full}.exe"
    installer = OUTPUT_DIR / expected_name
    if installer.exists():
        return installer
    
    # Fallback: find any ImageClassifierSetup_v*.exe (most recent)
    installers = list(OUTPUT_DIR.glob("ImageClassifierSetup_v*.exe"))
    if installers:
        # Return the most recently modified one
        return max(installers, key=lambda p: p.stat().st_mtime)
    
    return None


def create_release(token: str, tag: str, name: str, body: str) -> dict:
    """Create a GitHub release."""
    url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
    }
    data = {
        "tag_name": tag,
        "name": name,
        "body": body,
        "draft": False,
        "prerelease": False,
    }
    
    print(f"[INFO] Creating release: {tag}...")
    response = requests.post(url, json=data, headers=headers)
    
    if response.status_code == 201:
        return response.json()
    elif response.status_code == 422:
        # Release might already exist
        error_msg = response.json().get("message", "Unknown error")
        if "already exists" in error_msg.lower():
            print(f"[WARNING] Release {tag} already exists. Fetching existing release...")
            # Try to get the existing release
            get_url = f"{GITHUB_API_BASE}/repos/{REPO_OWNER}/{REPO_NAME}/releases/tags/{tag}"
            get_response = requests.get(get_url, headers=headers)
            if get_response.status_code == 200:
                return get_response.json()
        raise SystemExit(f"[ERROR] Failed to create release: {error_msg}")
    else:
        raise SystemExit(
            f"[ERROR] Failed to create release: {response.status_code} - {response.text}"
        )


def upload_release_asset(token: str, release_id: int, file_path: Path) -> None:
    """Upload a file as a release asset."""
    # GitHub API requires the uploads.github.com endpoint for release assets
    url = f"https://uploads.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/{release_id}/assets"
    
    # Query parameter for the filename
    params = {"name": file_path.name}
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "Content-Type": "application/octet-stream",
    }
    
    file_size = file_path.stat().st_size
    print(f"[INFO] Uploading {file_path.name} ({file_size / 1024 / 1024:.2f} MB)...")
    
    with open(file_path, "rb") as f:
        response = requests.post(url, headers=headers, params=params, data=f)
    
    if response.status_code == 201:
        print(f"[SUCCESS] Asset uploaded successfully!")
    elif response.status_code == 422:
        # Asset might already exist
        error_msg = response.json().get("message", "Unknown error")
        if "already exists" in error_msg.lower():
            print(f"[WARNING] Asset {file_path.name} already exists for this release.")
        else:
            raise SystemExit(f"[ERROR] Failed to upload asset: {error_msg}")
    else:
        raise SystemExit(
            f"[ERROR] Failed to upload asset: {response.status_code} - {response.text}"
        )


def main() -> int:
    # Check for GitHub token
    token = get_github_token()
    if not token:
        print(
            "[ERROR] GitHub token required.\n"
            "  Set GITHUB_TOKEN environment variable, or\n"
            "  Create .github_token file with your GitHub Personal Access Token (gitignored).\n"
            "  Token needs 'repo' scope.\n"
            "  Create token at: https://github.com/settings/tokens",
            file=sys.stderr,
        )
        return 1
    
    # Parse version
    version_short, version_full = parse_version()
    tag = f"v{version_short}"
    release_name = f"Image Classifier {version_short}"
    
    print(f"Version: {version_short} (full: {version_full})")
    print(f"Tag: {tag}")
    
    # Find installer file
    installer = find_installer_file(version_full)
    if not installer:
        print(
            f"[ERROR] Installer file not found in {OUTPUT_DIR}\n"
            f"  Expected: ImageClassifierSetup_v{version_full}.exe",
            file=sys.stderr,
        )
        return 1
    
    print(f"Installer: {installer.name}")
    
    # Get release notes
    release_notes = get_release_notes()
    print(f"\nRelease notes preview:\n{release_notes[:200]}...\n")
    
    # Create release
    try:
        release = create_release(token, tag, release_name, release_notes)
        release_id = release["id"]
        print(f"[SUCCESS] Release created: {release['html_url']}")
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1
    
    # Upload installer
    try:
        upload_release_asset(token, release_id, installer)
    except SystemExit as e:
        print(str(e), file=sys.stderr)
        return 1
    
    print(f"\n[SUCCESS] Release complete!")
    print(f"  Release URL: {release['html_url']}")
    print(f"  Download URL: https://github.com/{REPO_OWNER}/{REPO_NAME}/releases/download/{tag}/{installer.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
