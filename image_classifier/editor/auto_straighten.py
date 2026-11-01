"""Auto-straighten: estimate the tilt of horizons and verticals.

Detects long straight edges (Canny + probabilistic Hough), keeps those within
``MAX_TILT`` of horizontal or vertical, and returns the length-weighted median
tilt as the straighten angle that levels them. Returns ``None`` when there is
not enough consistent evidence, so the UI can say so instead of guessing.
"""
from __future__ import annotations

import math

import cv2
import numpy as np

WORK_SIZE = 1024
MAX_TILT = 30.0
MIN_LINES = 3
MAX_SPREAD = 4.0  # degrees (weighted MAD) above which the estimate is rejected


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    v, w = values[order], weights[order]
    cum = np.cumsum(w)
    return float(v[np.searchsorted(cum, cum[-1] / 2.0)])


def estimate_angle(image: np.ndarray) -> float | None:
    """Straighten angle (degrees, editor convention) for an RGB/RGBA/gray uint8 image."""
    if image.ndim == 3:
        image = cv2.cvtColor(np.ascontiguousarray(image[..., :3]), cv2.COLOR_RGB2GRAY)
    h, w = image.shape
    s = min(1.0, WORK_SIZE / max(w, h))
    if s < 1.0:
        image = cv2.resize(image, (int(w * s), int(h * s)), interpolation=cv2.INTER_AREA)
    h, w = image.shape
    gray = cv2.GaussianBlur(image, (5, 5), 0)
    med = float(np.median(gray))
    edges = cv2.Canny(gray, max(10.0, 0.66 * med), min(255.0, max(40.0, 1.33 * med)))
    diag = math.hypot(w, h)
    lines = cv2.HoughLinesP(
        edges, 1, np.pi / 720, threshold=max(30, int(diag * 0.05)),
        minLineLength=diag * 0.08, maxLineGap=diag * 0.01,
    )
    if lines is None:
        return None
    tilts, weights = [], []
    for x1, y1, x2, y2 in lines[:, 0, :]:
        dx, dy = float(x2 - x1), float(y2 - y1)
        length = math.hypot(dx, dy)
        a = math.degrees(math.atan2(dy, dx))  # screen convention: positive = clockwise
        a = (a + 90.0) % 180.0 - 90.0  # (-90, 90]
        if abs(a) <= MAX_TILT:
            tilt = a
        elif abs(abs(a) - 90.0) <= MAX_TILT:
            tilt = a - 90.0 if a > 0 else a + 90.0
        else:
            continue
        tilts.append(tilt)
        weights.append(length)
    if len(tilts) < MIN_LINES:
        return None
    t, wt = np.array(tilts), np.array(weights)
    med = _weighted_median(t, wt)
    # Keep the dominant cluster, then refine.
    keep = np.abs(t - med) <= MAX_SPREAD
    if keep.sum() < MIN_LINES or wt[keep].sum() < 0.5 * wt.sum():
        return None
    med = _weighted_median(t[keep], wt[keep])
    spread = _weighted_median(np.abs(t[keep] - med), wt[keep])
    if spread > MAX_SPREAD / 2:
        return None
    # Lines tilted by +med (clockwise) are levelled by rotating the image by -med.
    angle = -med
    return 0.0 if abs(angle) < 0.05 else round(angle, 1)
