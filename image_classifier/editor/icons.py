"""Editor icons in the app's own style (see ``ui/icons.py``).

Thin white strokes with a black halo, so they read on any photo and on the
black viewer. Each icon is rendered at every common display scale with the
pixmap's device pixel ratio set, which keeps them crisp and correctly sized
at 100-300 % Windows scaling.
"""
from __future__ import annotations

from PyQt6.QtCore import QByteArray, QRectF, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

# Path data in a 48x48 box. Each entry is drawn twice: black halo, then white line.
_PATHS = {
    "crop": ['<path d="M36 42V16C36 14 34 12 32 12H6"/>', '<path d="M14 4V30C14 32 16 34 18 34H44"/>'],
    "adjust": ['<circle cx="24" cy="24" r="9"/>',
               '<path d="M24 5V9M24 39V43M5 24H9M39 24H43M10.6 10.6L13.4 13.4M34.6 34.6L37.4 37.4'
               'M10.6 37.4L13.4 34.6M34.6 13.4L37.4 10.6"/>'],
    "undo": ['<path d="M17 11L9 19L17 27"/>', '<path d="M9 19H29A10 10 0 0 1 29 39H20"/>'],
    "redo": ['<path d="M31 11L39 19L31 27"/>', '<path d="M39 19H19A10 10 0 0 0 19 39H28"/>'],
    "reset": ['<path d="M11 26A13 13 0 1 0 15 14.5"/>', '<path d="M14 6V15H23"/>'],
    "compare": ['<rect x="7" y="11" width="34" height="26" rx="4"/>', '<path d="M24 6V42"/>',
                '<path d="M12 31L18 24L22 28"/>'],
    "rotate_left": ['<rect x="18" y="20" width="22" height="20" rx="3"/>',
                    '<path d="M10 28V20A10 10 0 0 1 20 10H27"/>', '<path d="M6 24L10 28L14 24"/>'],
    "rotate_right": ['<rect x="8" y="20" width="22" height="20" rx="3"/>',
                     '<path d="M38 28V20A10 10 0 0 0 28 10H21"/>', '<path d="M34 24L38 28L42 24"/>'],
    "flip_h": ['<path d="M20 10L7 37H20Z"/>', '<path d="M28 10L41 37H28Z" fill="white"/>',
               '<path d="M24 5V9M24 14V18M24 23V27M24 32V36M24 41V43"/>'],
    "flip_v": ['<path d="M10 20L37 7V20Z"/>', '<path d="M10 28L37 41V28Z" fill="white"/>',
               '<path d="M5 24H9M14 24H18M23 24H27M32 24H36M41 24H43"/>'],
    "aspect": ['<rect x="6" y="12" width="36" height="24" rx="3"/>',
               '<rect x="17" y="17" width="14" height="14" rx="2"/>'],
    "auto": ['<path d="M9 39L29 19"/>', '<path d="M26 16L32 22"/>',
             '<path d="M35 6V12M32 9H38M41 18V22M39 20H43M17 7V11M15 9H19"/>'],
    "close": ['<path d="M13 13L35 35M35 13L13 35"/>'],
    "chevron_down": ['<path d="M14 19L24 29L34 19"/>'],
    "check": ['<path d="M10 25L20 35L38 14"/>'],
    "zoom_in": ['<circle cx="21" cy="21" r="12"/>', '<path d="M30 30L41 41M21 15V27M15 21H27"/>'],
    "zoom_out": ['<circle cx="21" cy="21" r="12"/>', '<path d="M30 30L41 41M15 21H27"/>'],
    "fit": ['<path d="M14 6H6V14M34 6H42V14M14 42H6V34M34 42H42V34"/>'],
}
GLYPHS = tuple(_PATHS)

_SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
_cache: dict = {}


def _svg(name: str, halo: bool, color: str = "white") -> bytes:
    body = "".join(_PATHS[name])
    common = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    layers = []
    if halo:
        layers.append(f'<g stroke="black" stroke-width="4.5" {common}>{body.replace("white", "black")}</g>')
    layers.append(f'<g stroke="{color}" stroke-width="2" {common}>{body.replace("white", color)}</g>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
            + "".join(layers) + "</svg>").encode()


def pixmap(name: str, size: int, scale: float = 1.0, halo: bool = True, color: str = "white") -> QPixmap:
    """``size`` logical px at device ``scale``."""
    px = max(1, round(size * scale))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(QByteArray(_svg(name, halo, color))).render(p, QRectF(0, 0, px, px))
    p.end()
    pm.setDevicePixelRatio(scale)
    return pm


def icon(name: str, size: int = 32, halo: bool = True, color: str = "white") -> QIcon:
    key = (name, size, halo, color)
    if key not in _cache:
        result = QIcon()
        for scale in _SCALES:
            result.addPixmap(pixmap(name, size, scale, halo, color))
        _cache[key] = result
    return _cache[key]
