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


DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _parse_lines(path: Optional[Path]) -> list[tuple[str, str, str, Optional[str]]]:
    """[(version, english, spanish, date)] newest first. Lines are `version|English|Spanish[|YYYY-MM-DD]`."""
    path = path or notes_path()
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("|", 3)
        if len(parts) >= 3 and parse_version(parts[0]):
            version, en, es = (p.strip() for p in parts[:3])
            date = parts[3].strip() if len(parts) == 4 and DATE_RE.match(parts[3].strip()) else None
            rows.append((version, en, es or en, date))
    rows.sort(key=lambda r: parse_version(r[0]), reverse=True)
    return rows


def load_release_notes(path: Optional[Path] = None) -> list[tuple[str, str, str]]:
    """[(version, english, spanish)] newest first."""
    return [row[:3] for row in _parse_lines(path)]


def release_dates(path: Optional[Path] = None) -> dict[str, str]:
    """{version: 'YYYY-MM-DD'} for the versions whose notes line carries a date."""
    return {row[0]: row[3] for row in _parse_lines(path) if row[3]}


_MONTHS = {
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
    "es": ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"),
}


def format_release_date(iso: Optional[str], lang: str) -> Optional[str]:
    """'2026-11-02' -> '2 Nov 2026' (or '2 nov 2026'); None if there is no valid date."""
    if not iso or not DATE_RE.match(iso):
        return None
    year, month, day = (int(p) for p in iso.split("-"))
    if not 1 <= month <= 12:
        return None
    return f"{day} {_MONTHS['es' if lang == 'es' else 'en'][month - 1]} {year}"


POINT_SEPARATOR = "•"


def split_points(text: str) -> list[str]:
    """A note may list several points separated by ' • '; returns them in order."""
    return [part.strip() for part in text.split(POINT_SEPARATOR) if part.strip()]


# Each point may start with a section tag (same tag in both languages), like Sidera's notes:
#   new: ...  changed: ...  fixed: ...
SECTION_KINDS = ("new", "changed", "fixed")
_SECTION_RE = re.compile(r"^(new|changed|fixed)\s*:\s*", re.IGNORECASE)


def sections(text: str) -> list[tuple[Optional[str], list[str]]]:
    """[(kind, points)] in the order new, changed, fixed; untagged points come first with kind None."""
    groups: dict[Optional[str], list[str]] = {}
    for point in split_points(text):
        match = _SECTION_RE.match(point)
        kind = match.group(1).lower() if match else None
        body = point[match.end():].strip() if match else point
        if body:
            groups.setdefault(kind, []).append(body)
    ordered = [(None, groups[None])] if None in groups else []
    return ordered + [(kind, groups[kind]) for kind in SECTION_KINDS if kind in groups]


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
