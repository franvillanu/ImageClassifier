"""Installer download with progress and sha256 verification (no Qt)."""

from __future__ import annotations

import hashlib
import os
import re
import tempfile
import urllib.request
from typing import Callable, Optional

from image_classifier.updates.check import (
    DOWNLOAD_PREFIX,
    INSTALLER_NAME_RE,
    UpdateOffer,
)

CHUNK_SIZE = 64 * 1024
TIMEOUT_SECONDS = 30


class DownloadCancelled(Exception):
    pass


def update_dir() -> str:
    return os.path.join(tempfile.gettempdir(), "Image Classifier update")


def download_installer(
    offer: UpdateOffer,
    dest_dir: Optional[str] = None,
    on_progress: Optional[Callable[[int, int], None]] = None,
    is_cancelled: Callable[[], bool] = lambda: False,
    opener: Callable = urllib.request.urlopen,
) -> str:
    """Download the offered installer; returns the final .exe path or raises."""
    if not offer.url.startswith(DOWNLOAD_PREFIX):
        raise ValueError("Not an Image Classifier release link")
    if not INSTALLER_NAME_RE.match(offer.name) or not offer.url.endswith("/" + offer.name):
        raise ValueError("Not an installer")

    dest_dir = dest_dir or update_dir()
    os.makedirs(dest_dir, exist_ok=True)
    final_path = os.path.join(dest_dir, offer.name)
    part_path = final_path + ".part"
    digest = hashlib.sha256()
    got = 0

    try:
        with opener(offer.url, timeout=TIMEOUT_SECONDS) as response:
            total = int(response.headers.get("Content-Length") or 0) or (offer.size or 0)
            with open(part_path, "wb") as out:
                while True:
                    if is_cancelled():
                        raise DownloadCancelled()
                    chunk = response.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    out.write(chunk)
                    digest.update(chunk)
                    got += len(chunk)
                    if on_progress:
                        on_progress(got, total)
        if total and got != total:
            raise IOError("The download is incomplete")
        match = re.match(r"^sha256:([0-9a-f]{64})$", offer.digest or "", re.IGNORECASE)
        if match and digest.hexdigest() != match.group(1).lower():
            raise IOError("The download is damaged")
        os.replace(part_path, final_path)
    except BaseException:
        try:
            os.remove(part_path)
        except OSError:
            pass
        raise
    if on_progress:
        on_progress(got, got)
    return final_path
