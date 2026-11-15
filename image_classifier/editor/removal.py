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
WINDOWED = True  # search only the window where copying is allowed (same result, far fewer pixels)
_stats = {"search_px": 0, "apply_px": 0}  # pixels the template search looked at (tests, evidence)
RADIUS = 0.6  # a patch is only copied from within this many hole-sizes of itself (0 = anywhere)
COH_W = 40.0  # weight of copying from the same place as the already filled neighbours (0 = off)
COH_CAP = 40000.0
CTX_W = 40.0  # weight of the surroundings match (below); 0 turns it off
CTX = 21  # window (working px) whose average colour describes a place's surroundings
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
    # surroundings of every candidate: the average colour of the real pixels around it (a pavement patch
    # beside the wall should not be used to fill the wall, even if the few known pixels of the hole agree)
    known0 = (~hole).astype(np.float32)
    k_sum = cv2.boxFilter(known0, -1, (CTX, CTX), normalize=False, borderType=cv2.BORDER_CONSTANT)
    ctx_img = cv2.boxFilter(lab * known0[..., None], -1, (CTX, CTX), normalize=False,
                            borderType=cv2.BORDER_CONSTANT) / np.maximum(k_sum, 1.0)[..., None]
    ctx_cand = ctx_img[r:H - r, r:W - r]
    half = CTX // 2
    hy, hx = np.nonzero(hole)
    radius2 = (max(RADIUS * max(hy.max() - hy.min() + 1, hx.max() - hx.min() + 1), 3.0 * patch)) ** 2 if RADIUS else 0.0
    filled = np.zeros((H, W), bool)
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
        tmpl = lab[win][..., :nch]
        mine = None
        if CTX_W:  # the average colour of what is really around this patch
            cy, cx = y0 + r, x0 + r
            sl = (slice(max(0, cy - half), cy + half + 1), slice(max(0, cx - half), cx + half + 1))
            seen = (~hole[sl]).astype(np.float32)
            if seen.sum() >= 1:
                mine = (lab[sl] * seen[..., None]).sum((0, 1)) / seen.sum()
        mdy = mdx = None
        if COH_W:
            fw = filled[win]
            if fw.any():  # continue from where the neighbours were copied from: coherent chunks, no stray scraps
                mdy, mdx = np.median(offsets[win][fw], axis=0)

        def search(wy0, wy1, wx0, wx1, circle):
            """Best source whose window top-left lies in the given rows/cols; None if the circle holds no usable one."""
            sh, sw = wy1 - wy0 - patch + 1, wx1 - wx0 - patch + 1
            sc = cv2.matchTemplate(lab[wy0:wy1, wx0:wx1, :nch], tmpl, cv2.TM_SQDIFF, mask=known3)
            _stats["search_px"] += sc.size
            gy_, gx_ = yy[wy0:wy0 + sh, wx0:wx0 + sw], xx[wy0:wy0 + sh, wx0:wx0 + sw]
            ok = valid[wy0:wy0 + sh, wx0:wx0 + sw]
            if mine is not None:
                sc += CTX_W * ((ctx_cand[wy0:wy0 + sh, wx0:wx0 + sw] - mine) ** 2).sum(-1)
            if mdy is not None:
                sc += np.minimum(COH_W * ((gy_ - y0 - mdy) ** 2 + (gx_ - x0 - mdx) ** 2), COH_CAP)
            d2 = (gy_ - y0) ** 2 + (gx_ - x0) ** 2
            sc += NEAR * d2 / float(H * H + W * W)
            sc[~ok] = _FAR
            if circle:  # only the neighbourhood of this patch is a candidate source (RM-12)
                near = d2 <= radius2
                if not (near & ok).any():
                    return None
                sc[~near] = _FAR
            iy, ix = np.unravel_index(int(np.argmin(sc)), sc.shape)
            return wy0 + int(iy), wx0 + int(ix)

        found = None
        if radius2:
            if WINDOWED:  # RM-13: nothing outside the circle can win, so do not even look there
                rad = int(np.ceil(np.sqrt(radius2)))
                found = search(max(0, y0 - rad), min(H, y0 + rad + patch), max(0, x0 - rad), min(W, x0 + rad + patch), True)
            else:
                found = search(0, H, 0, W, True)
        if found is None:
            found = search(0, H, 0, W, False)
        sy, sx = found
        src = (slice(sy, sy + patch), slice(sx, sx + patch))
        img[win][unknown] = img[src][unknown]
        lab[win][unknown] = lab[src][unknown]
        gray[win][unknown] = lab[src][..., 0][unknown]
        offsets[win][unknown] = (sy - y0, sx - x0)
        filled[win] |= unknown
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
    """Return a copy of ``img`` (RGBA or RGB uint8, any resolution of the source) with the stroke filled.

    Only the box of the painted area (plus a margin) is processed: that is where pixels change, and it is a
    small part of the region the fill was searched in (RM-16).
    """
    sx, sy = img.shape[1] / source_size[0], img.shape[0] / source_size[1]
    x0, y0, x1, y1 = plan.box
    ix0, iy0 = int(round(x0 * sx)), int(round(y0 * sy))
    ix1, iy1 = max(int(round(x1 * sx)), ix0 + 1), max(int(round(y1 * sy)), iy0 + 1)
    rh, rw = iy1 - iy0, ix1 - ix0
    ww, wh = plan.work
    s_work = ww / max(1e-6, (x1 - x0))
    # one working pixel less than the plan's own growth, so the area filled here lies inside the planned one
    margin_src = (MARGIN_WORK - 1.0) / s_work
    mask_full = stroke_mask((rh, rw), removal, sx, (ix0 / sx, iy0 / sy), margin_src * sx)
    bx, by, bw, bh = cv2.boundingRect(mask_full)
    if bw == 0 or bh == 0:
        return img
    pad = 8  # known pixels around the painted area for the blend
    cx0, cy0 = max(0, bx - pad), max(0, by - pad)
    cx1, cy1 = min(rw, bx + bw + pad), min(rh, by + bh + pad)
    mask = np.ascontiguousarray(mask_full[cy0:cy1, cx0:cx1])
    hole = mask > 0
    roi = img[iy0:iy1, ix0:ix1, :3]  # the full region: sources may lie anywhere in it
    crop = np.ascontiguousarray(roi[cy0:cy1, cx0:cx1])
    _stats["apply_px"] += crop.shape[0] * crop.shape[1]
    out = img.copy()
    if plan.offsets is None:
        filled = cv2.inpaint(crop, mask, 5, cv2.INPAINT_TELEA)
    else:
        filled = _blend(_copy_hole(roi, plan, hole, (cx0, cy0), rw / ww, rh / wh), crop, mask)
    out[iy0 + cy0:iy0 + cy1, ix0 + cx0:ix0 + cx1, :3][hole] = filled[hole]
    return out


def _copy_hole(roi: np.ndarray, plan: Plan, hole: np.ndarray, origin: tuple[int, int], fx: float, fy: float) -> np.ndarray:
    """The box of ``roi`` starting at ``origin`` with the hole pixels copied from where the plan says.

    ``plan`` offsets are working pixels (scaled by fx, fy here); sources are read from the whole ``roi`` with
    one ``cv2.remap``.
    """
    ox, oy = origin
    bh, bw = hole.shape
    rh, rw = roi.shape[:2]
    wh, ww = plan.offsets.shape[:2]
    cy = np.clip(((np.arange(bh) + oy) / fy).astype(np.int32), 0, wh - 1)
    cx = np.clip(((np.arange(bw) + ox) / fx).astype(np.int32), 0, ww - 1)
    off = plan.offsets[cy[:, None], cx[None, :]]  # nearest working cell of every pixel
    usable = (off != 0).any(-1)  # a cell the plan did not fill has no source: the pixel stays as it is
    gy, gx = np.mgrid[0:bh, 0:bw].astype(np.float32)
    map_x = np.clip(np.round(gx + ox + off[..., 1] * fx), 0, rw - 1).astype(np.float32)
    map_y = np.clip(np.round(gy + oy + off[..., 0] * fy), 0, rh - 1).astype(np.float32)
    copied = cv2.remap(roi, map_x, map_y, cv2.INTER_NEAREST)
    base = roi[oy:oy + bh, ox:ox + bw]
    return np.where((hole & usable)[..., None], copied, base)


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
