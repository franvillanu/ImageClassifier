"""Scale pop-up text and spacing with the screen's resolution, so they stay readable on large screens."""

import re

REFERENCE_HEIGHT = 1440  # physical screen height (pixels) up to which sizes are used as written
MAX_SCALE = 1.6


def ui_scale(widget) -> float:
    """1.0 on screens up to 1440p, growing with the physical resolution up to MAX_SCALE.

    Uses the screen (not the window), so it does not change when the window is resized, and the
    physical pixel height (logical height x device pixel ratio), so a 4K display gets bigger text
    even when Windows display scaling already enlarges everything a little.
    """
    try:
        screen = widget.screen() if widget is not None else None
        if screen is None:
            return 1.0
        physical_height = screen.geometry().height() * screen.devicePixelRatio()
    except RuntimeError:
        return 1.0
    return max(1.0, min(MAX_SCALE, physical_height / REFERENCE_HEIGHT))


def px(value: float, scale: float) -> int:
    return max(1, round(value * scale)) if value else 0


_PX_RE = re.compile(r"(\d+(?:\.\d+)?)px")


def scale_css(css: str, scale: float) -> str:
    """Multiply every `Npx` in a stylesheet (1px hairlines stay 1px)."""
    if scale == 1.0:
        return css

    def bump(match):
        value = float(match.group(1))
        return match.group(0) if value <= 1 else f"{round(value * scale)}px"

    return _PX_RE.sub(bump, css)
