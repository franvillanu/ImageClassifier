"""Customer-facing release notes: the bundled history and the notes embedded in a GitHub release."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Optional

from image_classifier.updates.check import parse_version

NOTES_MARKER_RE = re.compile(r"<!--\s*ic-notes\s*(\{.*?\})\s*-->", re.DOTALL)


def notes_path() -> Path:
    """docs/release_notes.txt: bundled next to the app when frozen, in the repo otherwise."""
    if getattr(sys, "frozen", False):
        return Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent)) / "docs" / "release_notes.txt"
    return Path(__file__).resolve().parent.parent.parent / "docs" / "release_notes.txt"


def load_release_notes(path: Optional[Path] = None) -> list[tuple[str, str, str]]:
    """[(version, english, spanish)] newest first. Lines are `version|English|Spanish`."""
    path = path or notes_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 2)
        if len(parts) == 3 and parse_version(parts[0]):
            version, en, es = (p.strip() for p in parts)
            entries.append((version, en, es or en))
    entries.sort(key=lambda e: parse_version(e[0]), reverse=True)
    return entries


def pick(entry: tuple[str, str, str], lang: str) -> str:
    return entry[2] if lang == "es" else entry[1]


def notes_for_version(version: str, entries: Optional[list] = None) -> Optional[tuple[str, str, str]]:
    wanted = parse_version(version)
    for entry in entries if entries is not None else load_release_notes():
        if parse_version(entry[0]) == wanted:
            return entry
    return None


def notes_marker(en: str, es: str) -> str:
    """Hidden marker appended to a GitHub release body so the app can read the notes in both languages."""
    return f"<!-- ic-notes {json.dumps({'en': en, 'es': es}, ensure_ascii=False)} -->"


def parse_notes_marker(body: object) -> Optional[dict]:
    """{'en': ..., 'es': ...} from a release body, or None."""
    match = NOTES_MARKER_RE.search(body) if isinstance(body, str) else None
    if not match:
        return None
    try:
        data = json.loads(match.group(1))
    except ValueError:
        return None
    en, es = data.get("en"), data.get("es")
    if not isinstance(en, str) or not en.strip():
        return None
    return {"en": en.strip(), "es": es.strip() if isinstance(es, str) and es.strip() else en.strip()}
