"""One-click automatic enhancement: picks adjustment values from the photo itself.

The estimate is expressed in the editor's own sliders (see ``adjust.py``), so
the result is fully editable afterwards and undoable in one step. Every value
is damped and capped: the goal is a better-balanced photo, not a restyled one,
and an already well-exposed photo should come back almost unchanged.

It works like levels, not like a light meter: the brightest part of the photo
is lifted towards white and dark midtones are opened up, but a light photo is
never darkened just for being light. A drawing on white paper, snow or a beach
are meant to be bright; pulling their average towards middle grey only makes
them murky. Light is taken back only where the photo is actually blown out,
and then with Highlights, which leaves the rest of the photo alone.
"""
from __future__ import annotations

import cv2
import numpy as np

from image_classifier.editor import adjust

ANALYSIS_SIDE = 512
WHITE = 0.96  # display level the brightest detail (99.5th percentile) is lifted to
MIDTONE = 0.42  # display level a dark-looking photo's median is opened up towards
MANAGED = ("exposure", "brightness", "contrast", "highlights", "shadows", "saturation", "warmth")


def _to_linear(x):
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _to_srgb(x):
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _clamp(v: float, lo: float, hi: float) -> int:
    return int(round(max(lo, min(hi, v))))


def _warmth(lin: np.ndarray, tone: np.ndarray, sat: np.ndarray) -> int:
    """White balance from the photo's whites (paper, clouds, walls); none if it has no whites.

    The average colour is no guide: grass, sky or a sunset are coloured on purpose.
    """
    lit = (tone > 0.5) & (tone < 0.985)
    if lit.mean() < 0.02 or float(sat.mean()) < 0.04:  # a grey photo has no cast worth correcting
        return 0
    # Paper or a white wall is only tinted by the light: lamps can make it quite orange (~0.35), but
    # anything bluer than a faint tint is more likely a sky than a white.
    warm = lin[..., 0] >= lin[..., 2]
    whites = lit & (tone >= np.percentile(tone[lit], 60)) & (sat < np.where(warm, 0.4, 0.18))
    if whites.mean() < 0.02:
        return 0
    # A cast tints every white alike, so the most neutral of them still shows it, while pale
    # coloured objects (a yellow shirt) drop out.
    whites &= sat <= np.percentile(sat[whites], 30)
    r = float(lin[..., 0][whites].mean())
    b = float(lin[..., 2][whites].mean())
    target = b / r  # want (1 + k w) r == (1 - k w) b
    if abs(target - 1.0) <= 0.06:
        return 0
    k = adjust.WARMTH_GAIN
    w_full = (target - 1.0) / (k * (target + 1.0))
    return _clamp(0.6 * w_full * 100, -25, 25)  # part of the way: warm light is often the point


def estimate(image: np.ndarray) -> dict[str, int]:
    """Adjustment values for an RGB or RGBA uint8 image: {name: -100..100} for ``MANAGED`` sliders."""
    rgb = image[..., :3]
    h, w = rgb.shape[:2]
    s = min(1.0, ANALYSIS_SIDE / max(h, w))
    if s < 1.0:
        rgb = cv2.resize(rgb, (max(1, int(w * s)), max(1, int(h * s))), interpolation=cv2.INTER_AREA)
    lin = _to_linear(rgb.astype(np.float32) / 255.0)
    lum = lin @ adjust.LUMA
    shown = _to_srgb(lum)
    clipped = float(np.mean(shown > 0.98))

    # Exposure = white point: lift the brightest detail up to near white. Never negative.
    exposure = 0
    top = float(np.percentile(shown, 99.5))
    if top < WHITE and clipped < 0.005:
        ev = min(adjust.EXPOSURE_EV, np.log2(_to_linear(WHITE) / max(float(_to_linear(top)), 1e-4)))
        if ev >= 0.1:
            exposure = _clamp(100 * ev / adjust.EXPOSURE_EV, 0, 100)
    tone = _to_srgb(lum * 2.0 ** (adjust.EXPOSURE_EV * exposure / 100))

    # Brightness = midtones: a photo that still looks dark (a lamp or window already sets its
    # white point) is opened up with the gamma curve, which keeps black and white in place.
    brightness = 0
    median = float(np.median(tone))
    if 0.02 < median < MIDTONE - 0.04:
        target = median + 0.7 * (MIDTONE - median)
        b = 2.0 * (1.0 - np.log(target) / np.log(median))
        brightness = _clamp(100 * b, 0, 45)
        tone = np.power(tone, adjust.brightness_gamma(brightness / 100))
        median = float(np.median(tone))

    # Contrast = black point: a hazy or washed-out photo has no real blacks.
    p1, p5, p95 = np.percentile(tone, [1, 5, 95])
    spread = float(p95 - p5)
    contrast = 0
    # The S-curve darkens shadows, which a dark photo cannot spare; a high-key photo with nothing
    # dark in it (snow, fog) has a narrow range on purpose. A drawing on paper still gets crisper lines.
    if median > 0.3 and (median < 0.85 or p5 < 0.6):
        contrast = max(_clamp((0.78 - spread) * 90, 0, 30), _clamp((float(p1) - 0.06) * 120, 0, 25))

    # Highlights only where the photo is blown out; Shadows only where it is crushed to black.
    highlights = -_clamp(clipped * 300 + max(0.0, float(np.percentile(shown, 98)) - 0.97) * 400, 0, 60) \
        if clipped >= 0.02 else 0
    crushed = float(np.mean(tone < 0.03))
    shadows = _clamp(crushed * 500 + max(0.0, 0.06 - float(np.percentile(tone, 2))) * 300, 0, 50)

    # Colour: lift dull colour a little, calm very loud colour, and neutralise the light.
    sat = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)[..., 1].astype(np.float32) / 255.0
    lit = (tone > 0.08) & (tone < 0.92)  # ignore near-black / near-white pixels
    mean_sat = float(sat[lit].mean()) if lit.any() else float(sat.mean())
    if lit.mean() < 0.05 or mean_sat < 0.06:  # no colour to lift, only noise
        saturation = 0
    elif mean_sat < 0.28:
        saturation = _clamp((0.28 - mean_sat) * 110, 0, 25)
    elif mean_sat > 0.6:
        saturation = -_clamp((mean_sat - 0.6) * 60, 0, 15)
    else:
        saturation = 0

    return {"exposure": exposure, "brightness": brightness, "contrast": contrast, "highlights": highlights,
            "shadows": shadows, "saturation": saturation, "warmth": _warmth(lin, tone, sat)}
