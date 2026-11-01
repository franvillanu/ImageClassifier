"""Ajuste pipeline: one implementation for live preview and final export.

The work is split by cost so that both a 2560 px proxy and a 100 MP export
run the exact same maths:

1. Per-channel tone (exposure, warmth, tint in linear light; brightness and
   contrast in sRGB) folds into a single 256-entry LUT per channel.
2. Saturation is a 3x3 colour matrix (``cv2.transform``).
3. Local tone (highlights, shadows) and the vignette are smooth, so they are
   expressed as per-pixel ``gain`` and ``offset`` maps computed on a small
   (``MASK_SIZE``) copy of the image and upsampled bilinearly. The maps depend
   only on the image *content*, not its resolution, which keeps the preview
   faithful to the export.
4. Sharpness runs last on the whole image (it needs neighbouring rows).

``prepare`` builds a plan from a full-frame image; ``apply_rows`` then
processes any horizontal strip using global coordinates, so strips join
seamlessly.
"""
from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from image_classifier.editor.state import Adjustments
from image_classifier.imaging.sharpen import sharpen_array

MASK_SIZE = 512  # long side of the low-resolution map grid
LUMA = np.array([0.2126, 0.7152, 0.0722], dtype=np.float32)

# Strength constants (slider value v is normalised to [-1, 1]).
EXPOSURE_EV = 1.5
WARMTH_GAIN = 0.25
TINT_GAIN = 0.20
SHADOWS_EV = 1.5
HIGHLIGHTS_EV = 1.0
VIGNETTE_DARKEN = 0.75
VIGNETTE_LIGHTEN = 0.6
VIGNETTE_INNER = 0.35  # normalised radius where the vignette starts (corners = 1)
SHARPEN_AMOUNT = 1.6
SOFTEN_SIGMA = 0.0015  # fraction of the image diagonal at -100


def _srgb_to_linear(x: np.ndarray) -> np.ndarray:
    return np.where(x <= 0.04045, x / 12.92, ((x + 0.055) / 1.055) ** 2.4)


def _linear_to_srgb(x: np.ndarray) -> np.ndarray:
    x = np.clip(x, 0.0, 1.0)
    return np.where(x <= 0.0031308, x * 12.92, 1.055 * np.power(x, 1 / 2.4) - 0.055)


def _smoothstep(e0: float, e1: float, x: np.ndarray) -> np.ndarray:
    t = np.clip((x - e0) / (e1 - e0), 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def tone_curve(x: np.ndarray, brightness: float, contrast: float) -> np.ndarray:
    """Brightness (midtone lift, endpoints fixed) then contrast (S-curve about 0.5)."""
    if brightness:
        # y = x + k x (1 - x) is monotonic for |k| <= 1.
        x = x + brightness * x * (1.0 - x)
    if contrast > 0:
        x = x + contrast * (_smoothstep(0.0, 1.0, x) - x)
    elif contrast < 0:
        x = 0.5 + (x - 0.5) * (1.0 + 0.5 * contrast)
    return x


def build_lut(adj: Adjustments) -> np.ndarray | None:
    """(1, 256, 3) uint8 LUT in RGB order, or None if no per-channel stage is active."""
    e, w, t = adj.exposure / 100, adj.warmth / 100, adj.tint / 100
    b, c = adj.brightness / 100, adj.contrast / 100
    if not any((e, w, t, b, c)):
        return None
    x = np.arange(256, dtype=np.float64) / 255.0
    lin = _srgb_to_linear(x)
    gain = 2.0 ** (EXPOSURE_EV * e)
    gains = (
        gain * (1.0 + WARMTH_GAIN * w),
        gain * (1.0 - TINT_GAIN * t),  # positive tint -> magenta (less green)
        gain * (1.0 - WARMTH_GAIN * w),
    )
    channels = []
    for g in gains:
        y = _linear_to_srgb(lin * g)
        y = tone_curve(y, b, c)
        channels.append(np.clip(np.rint(y * 255.0), 0, 255))
    return np.stack(channels, axis=-1).astype(np.uint8)[np.newaxis, :, :]


def saturation_matrix(adj: Adjustments) -> np.ndarray | None:
    s = adj.saturation / 100
    if not s:
        return None
    k = 1.0 + s
    return (k * np.eye(3) + (1.0 - k) * np.tile(LUMA, (3, 1))).astype(np.float32)


@dataclass
class AdjustPlan:
    adj: Adjustments
    full_size: tuple[int, int]  # (width, height) of the frame the plan was built for
    lut: np.ndarray | None
    sat: np.ndarray | None
    gain: np.ndarray | None  # (mh, mw) float32 low-res maps, or None
    offset: np.ndarray | None
    vignette: bool

    @property
    def is_identity(self) -> bool:
        return self.adj.is_identity


def _point_ops(rgb: np.ndarray, lut, sat) -> np.ndarray:
    if lut is not None:
        rgb = cv2.LUT(rgb, lut)
    if sat is not None:
        rgb = cv2.transform(rgb, sat)
    return rgb


def _map_grid(full_size: tuple[int, int]) -> tuple[int, int]:
    W, H = full_size
    s = min(1.0, MASK_SIZE / max(W, H))
    return max(2, int(round(W * s))), max(2, int(round(H * s)))


def _vignette_maps(adj: Adjustments, mw: int, mh: int):
    v = adj.vignette / 100
    xs = (np.arange(mw, dtype=np.float32) + 0.5) / mw * 2.0 - 1.0
    ys = (np.arange(mh, dtype=np.float32) + 0.5) / mh * 2.0 - 1.0
    r = np.sqrt(xs[np.newaxis, :] ** 2 + ys[:, np.newaxis] ** 2) / np.sqrt(2.0)
    wgt = _smoothstep(VIGNETTE_INNER, 1.0, r).astype(np.float32)
    if v < 0:
        return 1.0 + v * VIGNETTE_DARKEN * wgt, np.zeros_like(wgt)
    a = v * VIGNETTE_LIGHTEN * wgt  # y = x (1 - a) + a  (lighten toward white)
    return 1.0 - a, a * 255.0


def prepare(rgb: np.ndarray, adj: Adjustments, *, vignette: bool = True) -> AdjustPlan:
    """Build an adjustment plan for the full frame ``rgb`` (H, W, 3 uint8)."""
    H, W = rgb.shape[:2]
    lut = build_lut(adj)
    sat = saturation_matrix(adj)
    gain = offset = None
    use_vig = vignette and adj.vignette != 0
    if adj.highlights or adj.shadows or use_vig:
        mw, mh = _map_grid((W, H))
        gain = np.ones((mh, mw), np.float32)
        offset = np.zeros((mh, mw), np.float32)
        if adj.highlights or adj.shadows:
            small = cv2.resize(rgb, (mw, mh), interpolation=cv2.INTER_AREA)
            small = _point_ops(small, lut, sat).astype(np.float32) / 255.0
            lum = small @ LUMA
            sigma = max(1.0, 0.012 * max(mw, mh))
            lum = cv2.GaussianBlur(lum, (0, 0), sigma)
            ws = (1.0 - _smoothstep(0.0, 0.5, lum)) ** 1.5
            wh = _smoothstep(0.5, 1.0, lum) ** 1.5
            ev = SHADOWS_EV * (adj.shadows / 100) * ws + HIGHLIGHTS_EV * (adj.highlights / 100) * wh
            gain *= np.exp2(ev).astype(np.float32)
        if use_vig:
            vg, vo = _vignette_maps(adj, mw, mh)
            gain = gain * vg
            offset = offset * vg + vo
    return AdjustPlan(adj, (W, H), lut, sat, gain, offset, use_vig)


def _upsample_rows(m: np.ndarray, full_size: tuple[int, int], y0: int, y1: int) -> np.ndarray:
    """Bilinear upsample of map ``m`` to full width for global rows [y0, y1) (half-pixel centres)."""
    W, H = full_size
    mh, mw = m.shape
    fy = (np.arange(y0, y1, dtype=np.float32) + 0.5) * (mh / H) - 0.5
    fy = np.clip(fy, 0, mh - 1)
    i0 = np.floor(fy).astype(np.int32)
    i1 = np.minimum(i0 + 1, mh - 1)
    t = (fy - i0)[:, np.newaxis]
    rows = m[i0] * (1.0 - t) + m[i1] * t
    return cv2.resize(rows, (W, y1 - y0), interpolation=cv2.INTER_LINEAR)


def apply_rows(plan: AdjustPlan, rgb: np.ndarray, y0: int = 0) -> np.ndarray:
    """Apply the plan's point and local stages to rows [y0, y0 + len) of the full frame."""
    if plan.is_identity:
        return rgb
    out = _point_ops(rgb, plan.lut, plan.sat)
    if plan.gain is not None:
        y1 = y0 + out.shape[0]
        g = _upsample_rows(plan.gain, plan.full_size, y0, y1)
        o = _upsample_rows(plan.offset, plan.full_size, y0, y1)
        f = out.astype(np.float32)
        f *= g[..., np.newaxis]
        f += o[..., np.newaxis]
        out = np.clip(f, 0, 255, out=f).astype(np.uint8)
    elif out is rgb:
        out = rgb.copy()
    return out


def finish(plan: AdjustPlan, rgb: np.ndarray) -> np.ndarray:
    """Whole-image stages (sharpness)."""
    v = plan.adj.sharpness / 100
    if not v:
        return rgb
    diag = float(np.hypot(*plan.full_size))
    if v > 0:
        radius = max(0.6, diag / 2500.0)
        return sharpen_array(rgb, radius, SHARPEN_AMOUNT * v, threshold=2)
    sigma = -v * SOFTEN_SIGMA * diag
    return cv2.GaussianBlur(rgb, (0, 0), max(0.3, sigma))


def apply_adjustments(rgb: np.ndarray, adj: Adjustments, *, vignette: bool = True) -> np.ndarray:
    """Convenience: adjust a whole RGB uint8 image in one call."""
    if adj.is_identity:
        return rgb
    plan = prepare(rgb, adj, vignette=vignette)
    return finish(plan, apply_rows(plan, rgb, 0))
