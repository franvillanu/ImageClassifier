"""Remove an object by painting over it (SPEC-005).

Exemplar-based inpainting (Criminisi et al.): the hole is filled patch by patch, most structured edge
first, each patch copied from the best-matching hole-free place in the photo. Real texture and edges
are copied instead of blurred, which is what a plain ``cv2.inpaint`` gives on anything bigger than a
speck.

The expensive part (finding where each pixel comes from) runs once per stroke on a downscaled working
copy of the stroke's surroundings and is kept as a *plan*: for every hole pixel, the offset to the pixel
it is copied from. Applying a plan works at any resolution (the preview proxy or the full photo), copying
real pixels at that resolution, so what you see while editing is what is saved (RM-4).

Pure numpy/OpenCV, no Qt.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

import cv2
import numpy as np

from image_classifier.editor.state import Removal

SEARCH_CHANNELS = 3  # Lab channels the patch search compares (1 = lightness only: ~3x faster)
WORK = 200  # longest side of the working copy the search runs on
PATCH = 9
MARGIN_WORK = 2.0  # working pixels the painted area is grown by, to swallow the object's soft edge
_FAR = 3e38
NEAR = 60000.0  # weight of the nearness preference, against a patch SSD of ~1e4..1e5


@dataclass(frozen=True)
class Plan:
    """Where a stroke's pixels come from. Geometry is in source pixels; the map is at working size."""

    box: tuple[int, int, int, int]  # x0, y0, x1, y1 of the working region, source pixels
    work: tuple[int, int]  # working size (w, h)
    offsets: np.ndarray | None  # (h, w, 2) int32 (dy, dx) in working pixels; None = use plain inpaint


# --------------------------------------------------------------------------- geometry
def _bbox(removal: Removal, source_size: tuple[int, int]) -> tuple[int, int, int, int]:
    """Working region: the stroke's box grown by its own size, so there is somewhere to copy from."""
    x0 = y0 = float("inf")
    x1 = y1 = float("-inf")
    for pts, r in removal.strokes():
        x0, x1 = min(x0, min(p[0] for p in pts) - r), max(x1, max(p[0] for p in pts) + r)
        y0, y1 = min(y0, min(p[1] for p in pts) - r), max(y1, max(p[1] for p in pts) + r)
    pad = max(x1 - x0, y1 - y0) * 0.9 + 24
    W, H = source_size
    return (max(0, int(x0 - pad)), max(0, int(y0 - pad)), min(W, int(np.ceil(x1 + pad))), min(H, int(np.ceil(y1 + pad))))


def stroke_mask(shape: tuple[int, int], removal: Removal, scale: float, origin: tuple[float, float] = (0.0, 0.0),
                margin: float = 0.0) -> np.ndarray:
    """uint8 mask (255 = remove) of the brush path on an image of ``shape`` (h, w) at ``scale`` image px per
    source px, whose top-left is source point ``origin``. ``margin`` (image px) grows the painted area."""
    mask = np.zeros(shape, np.uint8)
    shift = 4  # sub-pixel precision for cv2 drawing
    k = 1 << shift
    for points, radius in removal.strokes():
        pts = np.array([[(x - origin[0]) * scale, (y - origin[1]) * scale] for x, y in points], np.float32)
        r = max(0.5, radius * scale + margin)
        ip = np.round(pts * k).astype(np.int32)
        ir = int(round(r * k))
        for p in ip:
            cv2.circle(mask, (int(p[0]), int(p[1])), ir, 255, -1, cv2.LINE_8, shift)
        if len(ip) > 1:
            cv2.polylines(mask, [ip.reshape(-1, 1, 2)], False, 255, max(1, int(round(2 * r))), cv2.LINE_8, shift)
    return mask


def _work_geometry(removal: Removal, source_size):
    x0, y0, x1, y1 = _bbox(removal, source_size)
    s = min(1.0, WORK / max(x1 - x0, y1 - y0))
    ww, wh = max(PATCH + 2, int(round((x1 - x0) * s))), max(PATCH + 2, int(round((y1 - y0) * s)))
    return (x0, y0, x1, y1), s, (ww, wh)


# --------------------------------------------------------------------------- the search
def _exemplar_fill(img: np.ndarray, hole: np.ndarray, patch: int | None = None):
    """Fill ``hole`` (bool, h x w) of ``img`` (uint8 RGB). Returns the offset map (dy, dx) per hole pixel,
    or None when there is nowhere hole-free to copy from."""
    patch = patch or PATCH
    H, W = hole.shape
    r = patch // 2
    hole = hole.copy()
    lab = cv2.cvtColor(img, cv2.COLOR_RGB2LAB).astype(np.float32)
    nch = SEARCH_CHANNELS
    # a source window is usable only if it contains no hole pixel at all (checked once, on the original hole)
    count = cv2.boxFilter(hole.astype(np.float32), -1, (patch, patch), normalize=False,
                          borderType=cv2.BORDER_CONSTANT)
    valid = count[r:H - r, r:W - r] < 0.5
    if not valid.any():
        return None
    offsets = np.zeros((H, W, 2), np.int32)
    conf = (~hole).astype(np.float32)
    gray = lab[..., 0].copy()
    gray[hole] = 0
    erode_k = np.ones((3, 3), np.uint8)
    yy, xx = np.mgrid[0:H - patch + 1, 0:W - patch + 1].astype(np.float32)
    while hole.any():
        hm = hole.astype(np.uint8)
        front = hm - cv2.erode(hm, erode_k, borderType=cv2.BORDER_CONSTANT, borderValue=0)
        fy, fx = np.nonzero(front)
        if len(fy) == 0:
            break
        # priority = confidence (how much of the patch is real) x data (an edge running into the hole)
        c_box = cv2.boxFilter(conf, -1, (patch, patch), normalize=True)
        gl = cv2.GaussianBlur(gray, (0, 0), 1.0)
        gx = cv2.Sobel(gl, cv2.CV_32F, 1, 0, ksize=3)
        gy = cv2.Sobel(gl, cv2.CV_32F, 0, 1, ksize=3)
        mb = cv2.GaussianBlur(hole.astype(np.float32), (0, 0), 1.5)
        nx = cv2.Sobel(mb, cv2.CV_32F, 1, 0, ksize=3)
        ny = cv2.Sobel(mb, cv2.CV_32F, 0, 1, ksize=3)
        norm = np.sqrt(nx * nx + ny * ny) + 1e-6
        data = np.abs(-gy * nx + gx * ny) / norm / 255.0
        k = int(np.argmax(c_box[fy, fx] * (data[fy, fx] + 0.001)))
        y, x = int(fy[k]), int(fx[k])
        y0 = min(max(0, y - r), H - patch)
        x0 = min(max(0, x - r), W - patch)
        win = (slice(y0, y0 + patch), slice(x0, x0 + patch))
        unknown = hole[win]
        known3 = np.repeat((~unknown)[..., None], nch, 2).astype(np.float32)
        score = cv2.matchTemplate(lab[..., :nch], lab[win][..., :nch], cv2.TM_SQDIFF, mask=known3)
        # prefer sources near the target: far-away patches are what brings in the wrong scenery (walls, benches)
        score += NEAR * ((yy - y0) ** 2 + (xx - x0) ** 2) / float(H * H + W * W)
        score[~valid] = _FAR
        sy, sx = np.unravel_index(int(np.argmin(score)), score.shape)
        src = (slice(sy, sy + patch), slice(sx, sx + patch))
        img[win][unknown] = img[src][unknown]
        lab[win][unknown] = lab[src][unknown]
        gray[win][unknown] = lab[src][..., 0][unknown]
        offsets[win][unknown] = (sy - y0, sx - x0)
        conf[win][unknown] = c_box[y, x]
        hole[win] = False
    return offsets


def fill_plan(img: np.ndarray, removal: Removal, source_size: tuple[int, int]) -> Plan:
    """Work out where ``removal``'s pixels come from, looking at ``img`` (RGB(A) of any resolution of the source)."""
    box, s, (ww, wh) = _work_geometry(removal, source_size)
    sx, sy = img.shape[1] / source_size[0], img.shape[0] / source_size[1]
    x0, y0, x1, y1 = box
    roi = img[int(round(y0 * sy)):max(int(round(y1 * sy)), int(round(y0 * sy)) + 1),
              int(round(x0 * sx)):max(int(round(x1 * sx)), int(round(x0 * sx)) + 1), :3]
    small = np.ascontiguousarray(cv2.resize(roi, (ww, wh), interpolation=cv2.INTER_AREA))
    hole = stroke_mask((wh, ww), removal, s, (x0, y0), MARGIN_WORK) > 0
    if not hole.any() or hole.all():
        return Plan(box, (ww, wh), None)
    return Plan(box, (ww, wh), _exemplar_fill(small, hole))


# --------------------------------------------------------------------------- applying a plan
def apply_plan(img: np.ndarray, removal: Removal, plan: Plan, source_size: tuple[int, int]) -> np.ndarray:
    """Return a copy of ``img`` (RGBA or RGB uint8, any resolution of the source) with the stroke filled."""
    sx, sy = img.shape[1] / source_size[0], img.shape[0] / source_size[1]
    x0, y0, x1, y1 = plan.box
    ix0, iy0 = int(round(x0 * sx)), int(round(y0 * sy))
    ix1, iy1 = max(int(round(x1 * sx)), ix0 + 1), max(int(round(y1 * sy)), iy0 + 1)
    roi = np.ascontiguousarray(img[iy0:iy1, ix0:ix1, :3])
    rh, rw = roi.shape[:2]
    ww, wh = plan.work
    s_work = ww / max(1e-6, (x1 - x0))
    # one working pixel less than the plan's own growth, so the area filled here lies inside the planned one
    margin_src = (MARGIN_WORK - 1.0) / s_work
    mask = stroke_mask((rh, rw), removal, sx, (ix0 / sx, iy0 / sy), margin_src * sx)
    hole = mask > 0
    if not hole.any():
        return img
    out = img.copy()
    if plan.offsets is None:
        filled = cv2.inpaint(roi, mask, 5, cv2.INPAINT_TELEA)
    else:
        fx, fy = rw / ww, rh / wh
        off = cv2.resize(plan.offsets.astype(np.float32), (rw, rh), interpolation=cv2.INTER_NEAREST)
        gy, gx = np.mgrid[0:rh, 0:rw].astype(np.float32)
        map_x = np.clip(np.round(gx + off[..., 1] * fx), 0, rw - 1).astype(np.float32)
        map_y = np.clip(np.round(gy + off[..., 0] * fy), 0, rh - 1).astype(np.float32)
        copied = cv2.remap(roi, map_x, map_y, cv2.INTER_NEAREST)
        filled = np.where(hole[..., None], copied, roi)
        filled = _blend(filled, roi, mask)
    out[iy0:iy1, ix0:ix1, :3][hole] = filled[hole]
    return out


def _blend(filled: np.ndarray, original: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """Poisson-blend the copied pixels into the photo so the seam and any colour step vanish."""
    pad = 8
    f = cv2.copyMakeBorder(filled, pad, pad, pad, pad, cv2.BORDER_REFLECT)
    o = cv2.copyMakeBorder(original, pad, pad, pad, pad, cv2.BORDER_REFLECT)
    m = cv2.copyMakeBorder(mask, pad, pad, pad, pad, cv2.BORDER_CONSTANT, value=0)
    x, y, w, h = cv2.boundingRect(m)
    if w < 3 or h < 3:
        return filled
    try:
        out = cv2.seamlessClone(f, o, m, (x + w // 2, y + h // 2), cv2.NORMAL_CLONE)
    except cv2.error:
        return filled
    return out[pad:-pad, pad:-pad]


# --------------------------------------------------------------------------- caches + entry point
_lock = threading.Lock()
_plans: dict = {}
_last: dict = {}


def _plan_for(img, removals, i, source_size):
    key = (source_size, removals[:i + 1])
    with _lock:
        plan = _plans.get(key)
    if plan is None:
        plan = fill_plan(img, removals[i], source_size)
        with _lock:
            _plans[key] = plan
            while len(_plans) > 48:
                _plans.pop(next(iter(_plans)))
    return plan


def clear_caches():
    """Free the kept plans and the last result (editor closed)."""
    with _lock:
        _plans.clear()
        _last.clear()


def apply_removals(img: np.ndarray, removals: tuple[Removal, ...], source_size: tuple[int, int]) -> np.ndarray:
    """``img`` (RGBA/RGB uint8; the source or a proxy of it) with every stroke filled, in order.

    Returns ``img`` itself when there are none. The last result is kept, so adding one more stroke only
    fills that stroke and dragging an adjustment slider afterwards costs nothing.
    """
    if not removals:
        return img
    with _lock:
        last = dict(_last)
    start, base = 0, img
    if last.get("src") is img and last.get("size") == source_size:
        prev = last["removals"]
        if removals[:len(prev)] == prev:
            if len(prev) == len(removals):
                return last["out"]
            start, base = len(prev), last["out"]
    out = base
    for i in range(start, len(removals)):
        plan = _plan_for(out, removals, i, source_size)
        out = apply_plan(out, removals[i], plan, source_size)
    with _lock:
        _last.clear()
        _last.update(src=img, size=source_size, removals=removals, out=out)
    return out
