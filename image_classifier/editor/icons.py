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
    # photo with a small "restore" badge: reads as "back to the original", not as undo
    "reset": ['<path d="M27 33H11A4 4 0 0 1 7 29V12A4 4 0 0 1 11 8H31A4 4 0 0 1 35 12V22"/>',
              '<path d="M11 28L17.5 20.5L22 25L24.5 22.5"/>', '<circle cx="27.5" cy="15" r="2"/>',
              '<path d="M43 35.5A7.5 7.5 0 1 1 40.4 29.8"/>', '<path d="M41.5 25V30H36.5"/>'],
    # before / after split with a round handle
    "compare": ['<path d="M24 9H13A5 5 0 0 0 8 14V34A5 5 0 0 0 13 39H24Z" fill="white"/>',
                '<path d="M24 9H35A5 5 0 0 1 40 14V34A5 5 0 0 1 35 39H24"/>',
                '<path d="M24 4V44"/>', '<circle cx="24" cy="24" r="4.5" fill="black"/>'],
    "rotate_left": ['<rect x="18" y="20" width="22" height="20" rx="3"/>',
                    '<path d="M10 28V20A10 10 0 0 1 20 10H27"/>', '<path d="M6 24L10 28L14 24"/>'],
    "rotate_right": ['<rect x="8" y="20" width="22" height="20" rx="3"/>',
                     '<path d="M38 28V20A10 10 0 0 0 28 10H21"/>', '<path d="M34 24L38 28L42 24"/>'],
    # soft mirrored halves under a curved arrow
    "flip_h": ['<path d="M19.5 19.5V38A2 2 0 0 1 17.5 40H9.6A1.6 1.6 0 0 1 8.2 37.6L16.6 19A1.5 1.5 0 0 1 19.5 19.5Z"/>',
               '<path d="M28.5 19.5V38A2 2 0 0 0 30.5 40H38.4A1.6 1.6 0 0 0 39.8 37.6L31.4 19'
               'A1.5 1.5 0 0 0 28.5 19.5Z" fill="white"/>',
               '<path d="M12 12Q24 3 36 12"/>', '<path d="M31.5 11.5L36 12L35.5 7.5"/>',
               '<path d="M24 20V22M24 27V29M24 34V36"/>'],
    "flip_v": ['<g transform="rotate(90 24 24)">'
               '<path d="M19.5 19.5V38A2 2 0 0 1 17.5 40H9.6A1.6 1.6 0 0 1 8.2 37.6L16.6 19A1.5 1.5 0 0 1 19.5 19.5Z"/>'
               '<path d="M28.5 19.5V38A2 2 0 0 0 30.5 40H38.4A1.6 1.6 0 0 0 39.8 37.6L31.4 19'
               'A1.5 1.5 0 0 0 28.5 19.5Z" fill="white"/>'
               '<path d="M12 12Q24 3 36 12"/><path d="M31.5 11.5L36 12L35.5 7.5"/>'
               '<path d="M24 20V22M24 27V29M24 34V36"/></g>'],
    # frame with resize corners
    "aspect": ['<rect x="6" y="11" width="36" height="26" rx="5"/>',
               '<path d="M13 22V17H19M35 26V31H29"/>'],
    # a real wand: rounded body, tip band, curved sparkles
    "auto": ['<path d="M8.6 39.4L25.5 22.5L29.5 26.5L12.6 43.4A2.8 2.8 0 0 1 8.6 43.4A2.8 2.8 0 0 1 8.6 39.4Z"/>',
             '<path d="M25.5 22.5L28.5 19.5A2.8 2.8 0 0 1 32.5 23.5L29.5 26.5"/>',
             '<path d="M36 5Q37 10.5 42 11.5Q37 12.5 36 18Q35 12.5 30 11.5Q35 10.5 36 5Z" fill="white"/>',
             '<path d="M20 6Q20.6 9.2 23.5 9.8Q20.6 10.4 20 13.6Q19.4 10.4 16.5 9.8Q19.4 9.2 20 6Z" fill="white"/>',
             '<path d="M41 24Q41.5 26.6 44 27Q41.5 27.4 41 30Q40.5 27.4 38 27Q40.5 26.6 41 24Z" fill="white"/>'],
    "close": ['<path d="M13 13L35 35M35 13L13 35"/>'],
    "chevron_down": ['<path d="M14 19L24 29L34 19"/>'],
    "check": ['<path d="M10 25L20 35L38 14"/>'],
    "copy": ['<rect x="16" y="15" width="23" height="27" rx="4"/>',
             '<path d="M32 15V11A4 4 0 0 0 28 7H13A4 4 0 0 0 9 11V30A4 4 0 0 0 13 34H16"/>'],
    "replace": ['<path d="M12 7H31L40 16V37A4 4 0 0 1 36 41H12A4 4 0 0 1 8 37V11A4 4 0 0 1 12 7Z"/>',
                '<path d="M16 7V15A1 1 0 0 0 17 16H29A1 1 0 0 0 30 15V7"/>',
                '<path d="M15 41V29A2 2 0 0 1 17 27H31A2 2 0 0 1 33 29V41"/>'],
    "clipboard": ['<path d="M17 9H13A4 4 0 0 0 9 13V38A4 4 0 0 0 13 42H35A4 4 0 0 0 39 38V13A4 4 0 0 0 35 9H31"/>',
                  '<rect x="17" y="5" width="14" height="8" rx="2.5"/>', '<path d="M17 24H31M17 32H26"/>'],
    "zoom_in": ['<circle cx="21" cy="21" r="12"/>', '<path d="M30 30L41 41M21 15V27M15 21H27"/>'],
    "zoom_out": ['<circle cx="21" cy="21" r="12"/>', '<path d="M30 30L41 41M15 21H27"/>'],
    "fit": ['<path d="M14 6H6V14M34 6H42V14M14 42H6V34M34 42H42V34"/>'],
}
GLYPHS = tuple(_PATHS)

_SCALES = (1.0, 1.25, 1.5, 1.75, 2.0, 2.5, 3.0)
_cache: dict = {}


def _stroke(size: int) -> float:
    """Optical sizing: small icons get proportionally heavier lines so they stay legible."""
    return min(4.0, 2.0 * max(1.0, 24.0 / max(1, size)))


def _svg(name: str, halo: bool, color: str = "white", size: int = 32) -> bytes:
    body = "".join(_PATHS[name])
    common = 'fill="none" stroke-linecap="round" stroke-linejoin="round"'
    w = _stroke(size)
    layers = []
    if halo:
        layers.append(f'<g stroke="black" stroke-width="{w + 2.5:.2f}" {common}>{body.replace("white", "black")}</g>')
    layers.append(f'<g stroke="{color}" stroke-width="{w:.2f}" {common}>{body.replace("white", color)}</g>')
    return ('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
            + "".join(layers) + "</svg>").encode()


def pixmap(name: str, size: int, scale: float = 1.0, halo: bool = True, color: str = "white") -> QPixmap:
    """``size`` logical px at device ``scale``."""
    px = max(1, round(size * scale))
    pm = QPixmap(px, px)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    QSvgRenderer(QByteArray(_svg(name, halo, color, size))).render(p, QRectF(0, 0, px, px))
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
