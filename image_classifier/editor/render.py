"""Turn an ``EditState`` plus source pixels into output pixels.

Geometry (orientation, straighten, crop) is a single affine warp, so the
source is resampled exactly once. Unrotated crops take a slicing fast path
and are bit-exact. Large outputs are processed in horizontal strips to keep
peak memory bounded.
"""
from __future__ import annotations

import cv2
import numpy as np

from image_classifier.editor import adjust
from image_classifier.editor.geometry import frame_axes, orientation_matrix
from image_classifier.editor.state import EditState, Orientation

STRIP_ROWS = 1024


def output_size(state: EditState, scale: float = 1.0) -> tuple[int, int]:
    return max(1, int(round(state.crop.w * scale))), max(1, int(round(state.crop.h * scale)))


def output_to_source_matrix(state: EditState, src_shape: tuple[int, int], out_size: tuple[int, int]) -> np.ndarray:
    """3x3 matrix mapping output pixel indices to source-array pixel indices (cv2 convention)."""
    sh, sw = src_shape
    ow, oh = out_size
    c = state.crop
    ux, uy = frame_axes(c.angle)
    kx, ky = c.w / ow, c.h / oh
    # output continuous (u, v) -> O space
    crop_m = np.array([
        [ux[0] * kx, uy[0] * ky, c.cx - (ux[0] * c.w + uy[0] * c.h) / 2.0],
        [ux[1] * kx, uy[1] * ky, c.cy - (ux[1] * c.w + uy[1] * c.h) / 2.0],
        [0.0, 0.0, 1.0],
    ])
    o_from_s = np.array(orientation_matrix(state.orientation, state.source_size))
    s_from_o = np.linalg.inv(o_from_s)
    W, H = state.source_size
    arr_from_s = np.diag([sw / W, sh / H, 1.0])
    half = np.array([[1, 0, 0.5], [0, 1, 0.5], [0, 0, 1.0]])
    unhalf = np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]])
    return unhalf @ arr_from_s @ s_from_o @ crop_m @ half


def orient_array(arr: np.ndarray, orientation: Orientation) -> np.ndarray:
    """Apply an orientation to an array (returns a view)."""
    out = np.rot90(arr, k=-orientation.rot90) if orientation.rot90 else arr
    return out[:, ::-1] if orientation.flip else out


def _integer_crop(state: EditState, src_shape, out_size):
    """(x0, y0) if the crop is an exact unrotated pixel slice of the oriented source."""
    c = state.crop
    if c.angle != 0.0 or (src_shape[1], src_shape[0]) != state.source_size:
        return None
    ow, oh = out_size
    x0, y0 = c.cx - c.w / 2.0, c.cy - c.h / 2.0
    vals = (x0, y0, c.w, c.h)
    if any(abs(v - round(v)) > 1e-6 for v in vals) or (round(c.w), round(c.h)) != (ow, oh):
        return None
    return int(round(x0)), int(round(y0))


def warp(src: np.ndarray, state: EditState, out_size: tuple[int, int], *, interpolation=cv2.INTER_LANCZOS4,
         strip_rows: int = STRIP_ROWS) -> np.ndarray:
    ow, oh = out_size
    origin = _integer_crop(state, src.shape[:2], out_size)
    if origin is not None:
        x0, y0 = origin
        return np.ascontiguousarray(orient_array(src, state.orientation)[y0:y0 + oh, x0:x0 + ow])
    m = output_to_source_matrix(state, src.shape[:2], out_size)
    out = np.empty((oh, ow) + src.shape[2:], src.dtype)
    for y0 in range(0, oh, strip_rows):
        rows = min(strip_rows, oh - y0)
        ms = m @ np.array([[1, 0, 0], [0, 1, y0], [0, 0, 1.0]])
        out[y0:y0 + rows] = cv2.warpAffine(
            src, ms[:2].astype(np.float64), (ow, rows),
            flags=interpolation | cv2.WARP_INVERSE_MAP, borderMode=cv2.BORDER_REPLICATE,
        ).reshape((rows, ow) + src.shape[2:])
    return out


def adjust_rgba(rgba: np.ndarray, adj, *, vignette: bool = True, strip_rows: int = STRIP_ROWS) -> np.ndarray:
    """Apply adjustments to an RGBA uint8 array, keeping alpha. Returns a new array unless identity."""
    if adj.is_identity:
        return rgba
    out = rgba.copy()
    rgb = np.ascontiguousarray(rgba[..., :3])
    plan = adjust.prepare(rgb, adj, vignette=vignette)
    for y0 in range(0, rgb.shape[0], strip_rows):
        y1 = min(rgb.shape[0], y0 + strip_rows)
        out[y0:y1, :, :3] = adjust.apply_rows(plan, rgb[y0:y1], y0)
    if plan.adj.sharpness:
        out[..., :3] = adjust.finish(plan, np.ascontiguousarray(out[..., :3]))
    return out


def render(src: np.ndarray, state: EditState, *, scale: float = 1.0, interpolation=cv2.INTER_LANCZOS4,
           vignette: bool = True) -> np.ndarray:
    """Final pixels for ``state``: oriented, straightened, cropped and adjusted.

    ``src`` may be a downscaled proxy of the state's source; ``scale`` sizes the
    output relative to the crop's full-resolution size.
    """
    out = warp(src, state, output_size(state, scale), interpolation=interpolation)
    return adjust_rgba(out, state.adjust, vignette=vignette)


def fit_scale_for(state: EditState, max_side: int) -> float:
    """Scale that makes the output's long side at most ``max_side``."""
    w, h = state.crop.w, state.crop.h
    return min(1.0, max_side / max(w, h)) if max(w, h) > 0 else 1.0


def downscale(arr: np.ndarray, max_side: int) -> np.ndarray:
    h, w = arr.shape[:2]
    s = max_side / max(w, h)
    if s >= 1.0:
        return arr
    size = (max(1, int(round(w * s))), max(1, int(round(h * s))))
    return cv2.resize(arr, size, interpolation=cv2.INTER_AREA)

