"""Editor icons drawn from the Windows icon font (Segoe Fluent Icons, Win 11).

Using the system's own glyphs gives icons that match Windows Photos exactly
and stay crisp at any display scaling. Falls back to Segoe MDL2 Assets
(Windows 10), which shares most code points.
"""
from __future__ import annotations

import os

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QIcon, QPainter, QPixmap, QTransform

_FONT_FILES = (
    (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "SegoeIcons.ttf"), "Segoe Fluent Icons"),
    (os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "segmdl2.ttf"), "Segoe MDL2 Assets"),
)

# name -> (code point, transform): "mirror" flips horizontally, "rot90" turns a quarter
GLYPHS = {
    "zoom_in": (0xE8A3, None),
    "zoom_out": (0xE71F, None),
    "fit": (0xE9A6, None),
    "undo": (0xE7A7, None),
    "redo": (0xE7A6, None),
    "compare": (0xF57C, None),
    "crop": (0xE7A8, None),
    "adjust": (0xE706, None),
    "rotate_right": (0xE72C, None),
    "rotate_left": (0xE72C, "mirror"),
    "flip_h": (0xF1CB, None),
    "flip_v": (0xF1CB, "rot90"),
    "aspect": (0xF1A2, None),
    "auto": (0xE794, None),
    "chevron_down": (0xE70D, None),
    "brightness": (0xE706, None),
    "exposure": (0xE793, None),
    "contrast": (0xE7A1, None),
    "highlights": (0xED39, None),
    "shadows": (0xE708, None),
    "vignette": (0xF1A2, None),
    "saturation": (0xEF3C, None),
    "warmth": (0xE9CA, None),
    "tint": (0xEB42, None),
    "sharpness": (0xF157, None),
}

_family: str | None = None
_cache: dict = {}


def icon_family() -> str:
    global _family
    if _family is None:
        _family = ""
        for path, name in _FONT_FILES:
            if name in QFontDatabase.families():
                _family = name
                break
            if os.path.exists(path):
                fid = QFontDatabase.addApplicationFont(path)
                fams = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
                if fams:
                    _family = fams[0]
                    break
    return _family


def _render(code: int, transform: str | None, size: int, color: str, scale: float) -> QPixmap:
    px = max(1, round(size * scale))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    p.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
    if transform:
        c = px / 2.0
        t = QTransform().translate(c, c)
        t = t.scale(-1, 1) if transform == "mirror" else t.rotate(90)
        p.setTransform(t.translate(-c, -c))
    font = QFont(icon_family())
    font.setPixelSize(px)
    font.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    p.setFont(font)
    p.setPen(QColor(color))
    p.drawText(QRectF(0, 0, px, px), Qt.AlignmentFlag.AlignCenter, chr(code))
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, size: int = 16, color: str = "#ffffff") -> QIcon:
    """QIcon with crisp pixmaps for 100-300 % display scaling."""
    key = (name, size, color)
    if key not in _cache:
        code, transform = GLYPHS[name]
        result = QIcon()
        for scale in (1.0, 1.25, 1.5, 2.0, 2.5, 3.0):
            result.addPixmap(_render(code, transform, size, color, scale))
        _cache[key] = result
    return _cache[key]


def pixmap(name: str, size: int, color: str = "#ffffff", scale: float = 1.0) -> QPixmap:
    code, transform = GLYPHS[name]
    return _render(code, transform, size, color, scale)
