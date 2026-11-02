"""Scale pop-up text and spacing with the screen's resolution, so they stay readable on large screens."""

import re

REFERENCE_HEIGHT = 1440  # physical screen height (pixels) up to which sizes are used as written
GENTLENESS = 0.28  # how much of the extra resolution turns into bigger text (the rest stays as space)
MAX_SCALE = 1.35


def ui_scale(widget) -> float:
    """1.0 on screens up to 1440p, then a gentle increase with the physical resolution (a 4K screen gets about 1.13).

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
    ratio = physical_height / REFERENCE_HEIGHT
    return max(1.0, min(MAX_SCALE, 1.0 + (ratio - 1.0) * GENTLENESS))


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
