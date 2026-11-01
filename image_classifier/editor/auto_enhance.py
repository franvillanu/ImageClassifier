"""One-click automatic enhancement: picks adjustment values from the photo itself.

The estimate is expressed in the editor's own sliders (see ``adjust.py``), so
the result is fully editable afterwards and undoable in one step. Every value
is damped and capped: the goal is a better-balanced photo, not a restyled one,
and an already well-exposed photo should come back almost unchanged.
"""
from __future__ import annotations

import cv2
import numpy as np

from image_classifier.editor import adjust

ANALYSIS_SIDE = 512
MID_GREY = 0.18  # linear-light target for the median luminance (camera "middle grey")
MANAGED = ("exposure", "contrast", "highlights", "shadows", "saturation", "warmth")


def _to_linear(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _clamp(v: float, lo: float, hi: float) -> int:
    return int(round(max(lo, min(hi, v))))


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

    # Blown-out areas (a white sky) carry no information about exposure: leave them out,
    # and let Highlights deal with them instead.
    clipped_hi = float(np.mean(shown > 0.98))
    usable = (shown > 0.02) & (shown < 0.98)
    sample = lum[usable] if usable.mean() > 0.05 else lum

    # Exposure: bring the median towards middle grey, at 70 % strength, at most +-1.5 EV.
    median = float(np.median(sample))
    ev = 0.7 * np.log2(MID_GREY / max(median, 1e-4))
    ev = max(-adjust.EXPOSURE_EV, min(adjust.EXPOSURE_EV, ev))
    if abs(ev) < 0.15:
        ev = 0.0
    exposure = _clamp(100 * ev / adjust.EXPOSURE_EV, -100, 100)
    gain = 2.0 ** (adjust.EXPOSURE_EV * exposure / 100)

    # Tone is judged after the exposure change, in display (sRGB) terms.
    tone = _to_srgb(lum * gain)
    p2, p5, p95, p98 = np.percentile(tone, [2, 5, 95, 98])
    spread = float(p95 - p5)
    contrast = _clamp((0.78 - spread) * 90, 0, 35) if spread < 0.78 else 0

    clipped_hi = max(clipped_hi, float(np.mean(tone > 0.97)))
    crushed_lo = float(np.mean(tone < 0.03))
    highlights = -_clamp(clipped_hi * 300 + max(0.0, p98 - 0.97) * 400, 0, 60)
    shadows = _clamp(crushed_lo * 500 + max(0.0, 0.06 - p2) * 300, 0, 50)

    # Colour: lift dull colour a little, calm very loud colour; gentle grey-world white balance.
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
    sat = hsv[..., 1].astype(np.float32) / 255.0
    lit = (tone > 0.08) & (tone < 0.92)  # ignore near-black / near-white pixels
    mean_sat = float(sat[lit].mean()) if lit.any() else float(sat.mean())
    if mean_sat < 0.28:
        saturation = _clamp((0.28 - mean_sat) * 110, 0, 25)
    elif mean_sat > 0.6:
        saturation = -_clamp((mean_sat - 0.6) * 60, 0, 15)
    else:
        saturation = 0

    warmth = 0
    if lit.any() and mean_sat > 0.04:  # a grey photo has no cast worth correcting
        r = float(lin[..., 0][lit].mean())
        b = float(lin[..., 2][lit].mean())
        if r > 1e-4 and b > 1e-4:
            k = adjust.WARMTH_GAIN
            target = b / r  # want (1 + k w) r == (1 - k w) b
            w_full = (target - 1.0) / (k * (target + 1.0))
            # Only a clear cast is corrected, and only part of it: warm or cool light is often
            # the point of a photo (sunsets, candles, snow).
            if abs(target - 1.0) > 0.15:
                warmth = _clamp(0.3 * w_full * 100, -15, 15)

    return {"exposure": exposure, "contrast": contrast, "highlights": highlights, "shadows": shadows,
            "saturation": saturation, "warmth": warmth}
