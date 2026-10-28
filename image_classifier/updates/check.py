"""Update check against the public releases-only repo (no token, no Qt)."""

from __future__ import annotations

import json
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Callable, Optional

RELEASES_REPO = "franvillanu/imageclassifier-releases"
DOWNLOAD_PREFIX = f"https://github.com/{RELEASES_REPO}/releases/download/"
LATEST_API_URL = f"https://api.github.com/repos/{RELEASES_REPO}/releases/latest"
LATEST_PAGE_URL = f"https://github.com/{RELEASES_REPO}/releases/latest"
TIMEOUT_SECONDS = 8

_VERSION_RE = re.compile(r"^v?(\d+)\.(\d+)(?:\.(\d+))?$")
INSTALLER_NAME_RE = re.compile(r"^ImageClassifierSetup_v\d+\.\d+(?:\.\d+)?\.exe$")


@dataclass(frozen=True)
class UpdateOffer:
    version: str
    url: str
    name: str
    digest: Optional[str] = None
    size: Optional[int] = None


def parse_version(value) -> Optional[tuple[int, int, int]]:
    """Parse 'v2.0.7' or 'v2.0' (the first tag) into a 3-tuple; None if not a version."""
    match = _VERSION_RE.match(str(value or ""))
    if not match:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def current_version() -> str:
    override = os.environ.get("IMAGE_CLASSIFIER_FAKE_VERSION")
    if override:
        return override
    from image_classifier import __version__

    return __version__


def newer_release(current: str, release: dict) -> Optional[UpdateOffer]:
    """The newer release's installer, or None."""
    mine = parse_version(current)
    theirs = parse_version((release or {}).get("tag_name"))
    if not mine or not theirs or release.get("draft") or release.get("prerelease"):
        return None
    if theirs <= mine:
        return None
    for asset in release.get("assets") or []:
        name = str(asset.get("name", ""))
        url = str(asset.get("browser_download_url", ""))
        if not INSTALLER_NAME_RE.match(name) or not url.startswith(DOWNLOAD_PREFIX):
            continue
        # The URL must name the asset directly; reject traversal or encoded tricks.
        rest = url[len(DOWNLOAD_PREFIX):]
        if ".." in rest or "%" in rest or not rest.endswith("/" + name):
            continue
        digest = asset.get("digest")
        size = asset.get("size")
        return UpdateOffer(
            version=".".join(map(str, theirs)),
            url=url,
            name=name,
            digest=digest if isinstance(digest, str) else None,
            size=size if isinstance(size, int) and size > 0 else None,
        )
    return None


def release_from_tag(tag: str) -> dict:
    """A release known only by its tag: the installer is at the usual address."""
    parsed = parse_version(tag)
    if not parsed:
        raise ValueError(f"Not a version tag: {tag}")
    version = ".".join(map(str, parsed))
    name = f"ImageClassifierSetup_v{version}.exe"
    return {
        "tag_name": f"v{version}",
        "assets": [
            {
                "name": name,
                "browser_download_url": f"{DOWNLOAD_PREFIX}v{version}/{name}",
            }
        ],
    }


def fetch_json(url: str) -> dict:
    request = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
        return json.load(response)


def fetch_latest_tag() -> str:
    """Read the latest tag from the releases page redirect (not rate limited)."""
    with urllib.request.urlopen(LATEST_PAGE_URL, timeout=TIMEOUT_SECONDS) as response:
        match = re.search(r"/releases/tag/([^/?#]+)$", response.geturl())
    if not match:
        raise ValueError("No tag in redirect")
    return match.group(1)


def check_for_update(
    current: Optional[str] = None,
    fetch_json_fn: Callable[[str], dict] = fetch_json,
    fetch_latest_tag_fn: Callable[[], str] = fetch_latest_tag,
) -> dict:
    """Returns {'state': 'available', 'offer': UpdateOffer} | {'state': 'current'|'failed'}."""
    if os.environ.get("IMAGE_CLASSIFIER_UPDATES_OFFLINE") == "1":
        return {"state": "failed"}
    current = current or current_version()
    try:
        release = fetch_json_fn(LATEST_API_URL)
    except Exception:
        try:
            release = release_from_tag(fetch_latest_tag_fn())
        except Exception:
            return {"state": "failed"}
    offer = newer_release(current, release)
    if offer:
        return {"state": "available", "offer": offer}
    return {"state": "current"}
