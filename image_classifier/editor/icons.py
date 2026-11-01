"""Line icons for the photo editor (24x24 viewBox, Fluent-like strokes)."""
from __future__ import annotations

from PyQt6.QtCore import QByteArray, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_S = 'fill="none" stroke="{c}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"'

_PATHS = {
    "zoom_in": '<circle cx="10.5" cy="10.5" r="6.5" {s}/><path d="M15.5 15.5L21 21M10.5 7.5v6M7.5 10.5h6" {s}/>',
    "zoom_out": '<circle cx="10.5" cy="10.5" r="6.5" {s}/><path d="M15.5 15.5L21 21M7.5 10.5h6" {s}/>',
    "fit": '<path d="M4 9V5a1 1 0 0 1 1-1h4M15 4h4a1 1 0 0 1 1 1v4M20 15v4a1 1 0 0 1-1 1h-4M9 20H5a1 1 0 0 1-1-1v-4" {s}/>',
    "undo": '<path d="M9 14L4 9l5-5" {s}/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11" {s}/>',
    "redo": '<path d="M15 14l5-5-5-5" {s}/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13" {s}/>',
    "compare": '<rect x="3" y="5" width="18" height="14" rx="2" {s}/><path d="M12 3v18" {s}/><path d="M12 5h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-7z" fill="{c}" fill-opacity="0.35" stroke="none"/>',
    "crop": '<path d="M6 2v14a2 2 0 0 0 2 2h14M2 6h14a2 2 0 0 1 2 2v14" {s}/>',
    "adjust": '<circle cx="12" cy="12" r="4" {s}/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" {s}/>',
    "rotate_left": '<path d="M3 4v5h5" {s}/><path d="M3.5 9A8.5 8.5 0 1 1 5 15.5" {s}/>',
    "rotate_right": '<path d="M21 4v5h-5" {s}/><path d="M20.5 9A8.5 8.5 0 1 0 19 15.5" {s}/>',
    "flip_h": '<path d="M12 3v18" {s} stroke-dasharray="2 2.5"/><path d="M9 6L3 18h6zM15 6l6 12h-6z" {s}/>',
    "flip_v": '<path d="M3 12h18" {s} stroke-dasharray="2 2.5"/><path d="M6 9L18 3v6zM6 15l12 6v-6z" {s}/>',
    "aspect": '<rect x="3" y="6" width="18" height="12" rx="2" {s}/><path d="M7 10v4h4M17 14v-4h-4" {s}/>',
    "auto": '<path d="M4 20L15 9M13 7l2-2 4 4-2 2z" {s}/><path d="M7 3v3M5.5 4.5h3M19 14v3M17.5 15.5h3M10 3.5l.01 0" {s}/>',
    "chevron_down": '<path d="M6 9l6 6 6-6" {s}/>',
    "brightness": '<circle cx="12" cy="12" r="4.5" {s}/><path d="M12 2.5v2M12 19.5v2M2.5 12h2M19.5 12h2M5.3 5.3l1.4 1.4M17.3 17.3l1.4 1.4M5.3 18.7l1.4-1.4M17.3 6.7l1.4-1.4" {s}/>',
    "exposure": '<circle cx="12" cy="12" r="9" {s}/><path d="M5.6 18.4L18.4 5.6" {s}/><path d="M7 9h4M9 7v4M13 15.5h4" {s}/>',
    "contrast": '<circle cx="12" cy="12" r="9" {s}/><path d="M12 3a9 9 0 0 1 0 18z" fill="{c}" stroke="none"/>',
    "highlights": '<circle cx="12" cy="12" r="9" {s}/><path d="M12 3a9 9 0 0 1 9 9h-9z" fill="{c}" stroke="none"/>',
    "shadows": '<circle cx="12" cy="12" r="9" {s}/><path d="M12 21a9 9 0 0 1-9-9h9z" fill="{c}" stroke="none"/>',
    "vignette": '<rect x="3" y="4" width="18" height="16" rx="2" {s}/><ellipse cx="12" cy="12" rx="5.5" ry="4.5" {s}/>',
    "saturation": '<path d="M19 3l2 2-9.5 9.5-3 1 1-3z" {s}/><path d="M8 16l-4.5 4.5" {s}/>',
    "warmth": '<path d="M10 14.5V5a2 2 0 1 1 4 0v9.5a4 4 0 1 1-4 0z" {s}/><path d="M12 9v7" {s}/>',
    "tint": '<path d="M12 3s6 6.5 6 11a6 6 0 0 1-12 0c0-4.5 6-11 6-11z" {s}/>',
    "sharpness": '<path d="M6 3h12l4 6-10 12L2 9z" {s}/><path d="M2 9h20M9 3l3 18 3-18" {s}/>',
}

_cache: dict = {}


def icon(name: str, size: int = 20, color: str = "#ffffff") -> QIcon:
    key = (name, size, color)
    if key in _cache:
        return _cache[key]
    body = _PATHS[name].replace("{s}", _S).replace("{c}", color)
    svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24">{body}</svg>'
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    result = QIcon()
    for scale in (1, 2):
        pm = QPixmap(size * scale, size * scale)
        pm.fill(Qt.GlobalColor.transparent)
        pm.setDevicePixelRatio(scale)
        painter = QPainter(pm)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
        painter.end()
        result.addPixmap(pm)
    _cache[key] = result
    return result
