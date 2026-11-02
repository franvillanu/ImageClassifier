"""Scale pop-up text and spacing with the window, so they stay readable on large screens."""

import re

BASE_HEIGHT = 1000  # window height at which sizes are used as written
MAX_SCALE = 1.8


def ui_scale(widget) -> float:
    """1.0 on small windows, growing with the window height up to MAX_SCALE."""
    try:
        height = widget.window().height() if widget is not None else BASE_HEIGHT
    except RuntimeError:
        height = BASE_HEIGHT
    return max(1.0, min(MAX_SCALE, height / BASE_HEIGHT))


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
