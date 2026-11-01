"""Crop geometry: pure, closed-form, Qt-free.

Invariant kept by every function here: the crop rectangle lies entirely inside
the oriented image ``[0, W] x [0, H]``. Because the image bounds are axis
aligned in O space, a rotated crop is inside them exactly when its axis-aligned
bounding box is, so every constraint is a linear inequality - no iteration or
binary search is needed.

See ``state.py`` for the coordinate conventions.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, replace

from image_classifier.editor.state import (
    ANGLE_LIMIT,
    CropGeometry,
    EditState,
    Orientation,
    full_crop,
)

Size = tuple[float, float]
Point = tuple[float, float]

EPS = 1e-6
DEFAULT_MIN_SIZE = 16.0

# handle name -> (sx, sy): which frame sides move (-1 = left/top, +1 = right/bottom)
HANDLES = {
    "top_left": (-1, -1),
    "top": (0, -1),
    "top_right": (1, -1),
    "right": (1, 0),
    "bottom_right": (1, 1),
    "bottom": (0, 1),
    "bottom_left": (-1, 1),
    "left": (-1, 0),
}


# --------------------------------------------------------------------------- basics

def frame_axes(angle: float) -> tuple[Point, Point]:
    """Unit vectors of the crop frame's x and y axes, expressed in O space."""
    a = math.radians(angle)
    c, s = math.cos(a), math.sin(a)
    return (c, -s), (s, c)


def half_extents(w: float, h: float, angle: float) -> tuple[float, float]:
    """Half width/height of the axis-aligned bounding box of a rotated w x h rect."""
    a = math.radians(angle)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    return (w * c + h * s) / 2.0, (w * s + h * c) / 2.0


def corners(crop: CropGeometry) -> list[Point]:
    """Crop corners in O space: top-left, top-right, bottom-right, bottom-left."""
    ux, uy = frame_axes(crop.angle)
    out = []
    for a, b in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        dx, dy = a * crop.w / 2.0, b * crop.h / 2.0
        out.append((crop.cx + dx * ux[0] + dy * uy[0], crop.cy + dx * ux[1] + dy * uy[1]))
    return out


def is_valid(crop: CropGeometry, bounds: Size, eps: float = 1e-6) -> bool:
    W, H = bounds
    ex, ey = half_extents(crop.w, crop.h, crop.angle)
    tol = eps * max(1.0, W, H)
    return (
        crop.w > 0
        and crop.h > 0
        and crop.cx - ex >= -tol
        and crop.cx + ex <= W + tol
        and crop.cy - ey >= -tol
        and crop.cy + ey <= H + tol
    )


def min_size_for(bounds: Size, requested: float = DEFAULT_MIN_SIZE) -> float:
    return max(1.0, min(requested, bounds[0], bounds[1]))


def _clamp(v: float, lo: float, hi: float) -> float:
    if lo > hi:  # degenerate: centre is forced
        return (lo + hi) / 2.0
    return max(lo, min(hi, v))


def fit_scale(w: float, h: float, angle: float, bounds: Size) -> float:
    """Largest factor s such that an (s*w x s*h) crop at ``angle`` fits somewhere in bounds."""
    ex, ey = half_extents(w, h, angle)
    return min(bounds[0] / (2.0 * ex), bounds[1] / (2.0 * ey))


def scale_at_center(crop: CropGeometry, bounds: Size) -> float:
    """Largest factor s such that the crop scaled about its own centre stays inside bounds."""
    W, H = bounds
    ex, ey = half_extents(crop.w, crop.h, crop.angle)
    cx = _clamp(crop.cx, 0.0, W)
    cy = _clamp(crop.cy, 0.0, H)
    return min(cx / ex, (W - cx) / ex, cy / ey, (H - cy) / ey)


def clamp_center(crop: CropGeometry, bounds: Size) -> CropGeometry:
    """Shrink the crop if it cannot fit at all, then move its centre the minimum amount to fit."""
    s = fit_scale(crop.w, crop.h, crop.angle, bounds)
    if s < 1.0:
        crop = replace(crop, w=crop.w * s, h=crop.h * s)
    W, H = bounds
    ex, ey = half_extents(crop.w, crop.h, crop.angle)
    return replace(crop, cx=_clamp(crop.cx, ex, W - ex), cy=_clamp(crop.cy, ey, H - ey))


# --------------------------------------------------------------------------- operations

def default_crop(bounds: Size) -> CropGeometry:
    return full_crop((bounds[0], bounds[1]))


def fit_to_angle(base: CropGeometry, angle: float, bounds: Size) -> CropGeometry:
    """Straighten to ``angle`` starting from ``base`` (the crop when the gesture began).

    Keeps the centre and aspect, shrinking only as much as needed. Because the
    caller always passes the gesture's base crop, returning to the base angle
    restores the original crop exactly.
    """
    angle = max(-ANGLE_LIMIT, min(ANGLE_LIMIT, float(angle)))
    crop = replace(base, angle=angle)
    s = scale_at_center(crop, bounds)
    if s < 1.0:
        crop = replace(crop, w=crop.w * s, h=crop.h * s)
    return clamp_center(crop, bounds)


def pan(crop: CropGeometry, delta: Point, bounds: Size) -> CropGeometry:
    """Move the crop by ``delta`` (O space), stopping at the image edges."""
    return clamp_center(replace(crop, cx=crop.cx + delta[0], cy=crop.cy + delta[1]), bounds)


def zoom(
    crop: CropGeometry,
    factor: float,
    anchor: Point | None,
    bounds: Size,
    min_size: float | None = None,
) -> CropGeometry:
    """Zoom the view by ``factor`` (>1 = in = smaller crop) keeping ``anchor`` (O space) fixed."""
    if min_size is None:
        min_size = min_size_for(bounds)
    lo = max(min_size / crop.w, min_size / crop.h)
    hi = fit_scale(crop.w, crop.h, crop.angle, bounds)
    s = max(lo, min(hi, 1.0 / factor))
    if anchor is None:
        anchor = (crop.cx, crop.cy)
    ax, ay = anchor
    crop = replace(
        crop,
        cx=ax + (crop.cx - ax) * s,
        cy=ay + (crop.cy - ay) * s,
        w=crop.w * s,
        h=crop.h * s,
    )
    return clamp_center(crop, bounds)


def set_aspect(crop: CropGeometry, ratio: float | None, bounds: Size) -> CropGeometry:
    """Largest crop with w/h == ``ratio`` near the current centre. ``None`` keeps the crop."""
    if ratio is None:
        return crop
    ratio = float(ratio)
    s = fit_scale(ratio, 1.0, crop.angle, bounds)
    return clamp_center(replace(crop, w=ratio * s, h=s), bounds)


def _max_step(crop0: CropGeometry, crop1: CropGeometry, bounds: Size) -> float:
    """Largest t in [0, 1] such that lerp(crop0, crop1, t) is valid (same angle).

    Centre and size are affine in t, so the bounding-box extents are too and
    every constraint is linear: the answer is a min over four ratios.
    """
    W, H = bounds
    ex0, ey0 = half_extents(crop0.w, crop0.h, crop0.angle)
    ex1, ey1 = half_extents(crop1.w, crop1.h, crop1.angle)
    t = 1.0
    # each constraint: f(t) = a + b t >= 0
    for a0, a1 in (
        (crop0.cx - ex0, crop1.cx - ex1),
        (W - crop0.cx - ex0, W - crop1.cx - ex1),
        (crop0.cy - ey0, crop1.cy - ey1),
        (H - crop0.cy - ey0, H - crop1.cy - ey1),
    ):
        a, b = a0, a1 - a0
        if a < 0:  # start already violates (numerical slop) - don't move further out
            a = 0.0
        if b < -1e-12:
            t = min(t, a / -b)
    return max(0.0, t)


def _lerp_crop(c0: CropGeometry, c1: CropGeometry, t: float) -> CropGeometry:
    return replace(
        c0,
        cx=c0.cx + (c1.cx - c0.cx) * t,
        cy=c0.cy + (c1.cy - c0.cy) * t,
        w=c0.w + (c1.w - c0.w) * t,
        h=c0.h + (c1.h - c0.h) * t,
    )


def _from_local(start: CropGeometry, left: float, top: float, right: float, bottom: float) -> CropGeometry:
    """Build a crop from frame-local edges measured from the start crop's centre."""
    ux, uy = frame_axes(start.angle)
    lx, ly = (left + right) / 2.0, (top + bottom) / 2.0
    return replace(
        start,
        cx=start.cx + lx * ux[0] + ly * uy[0],
        cy=start.cy + lx * ux[1] + ly * uy[1],
        w=right - left,
        h=bottom - top,
    )


def resize_handle(
    start: CropGeometry,
    handle: str,
    delta: Point,
    aspect: float | None,
    bounds: Size,
    min_size: float | None = None,
) -> CropGeometry:
    """Drag ``handle`` by ``delta`` (crop-frame pixels, i.e. along the frame axes).

    The opposite side/corner stays anchored. With ``aspect`` set, the ratio is
    kept: corner drags project the pointer onto the frame diagonal (both axes
    count), edge drags grow the other dimension symmetrically. The result never
    leaves the image and never drops below ``min_size``.
    """
    if min_size is None:
        min_size = min_size_for(bounds)
    start = clamp_center(start, bounds)
    sx, sy = HANDLES[handle]
    dx, dy = delta
    hw, hh = start.w / 2.0, start.h / 2.0
    left, top, right, bottom = -hw, -hh, hw, hh

    if aspect is None:
        if sx > 0:
            right = max(left + min_size, right + dx)
        elif sx < 0:
            left = min(right - min_size, left + dx)
        if sy > 0:
            bottom = max(top + min_size, bottom + dy)
        elif sy < 0:
            top = min(bottom - min_size, top + dy)
        target = _from_local(start, left, top, right, bottom)
        t = _max_step(start, target, bounds)
        result = _lerp_crop(start, target, t)
        if t < 1.0 and sx != 0 and sy != 0:
            # Corner hit an edge: let the free axis keep following the pointer.
            for axis in ("x", "y"):
                rl, rt = -result.w / 2.0, -result.h / 2.0
                rr, rb = result.w / 2.0, result.h / 2.0
                # result's edges in start-local coordinates
                ux, uy = frame_axes(start.angle)
                ox = (result.cx - start.cx) * ux[0] + (result.cy - start.cy) * ux[1]
                oy = (result.cx - start.cx) * uy[0] + (result.cy - start.cy) * uy[1]
                rl, rr, rt, rb = rl + ox, rr + ox, rt + oy, rb + oy
                if axis == "x":
                    rl, rr = (rl, right) if sx > 0 else (left, rr)
                else:
                    rt, rb = (rt, bottom) if sy > 0 else (top, rb)
                cand = _from_local(start, rl, rt, rr, rb)
                result = _lerp_crop(result, cand, _max_step(result, cand, bounds))
        return result

    # ---- ratio locked
    r = float(aspect)
    t_min = max(min_size / r, min_size)  # height scale such that both sides >= min_size
    if sx != 0 and sy != 0:
        w1 = max(0.0, start.w + sx * dx)
        h1 = max(0.0, start.h + sy * dy)
        t1 = (w1 * r + h1) / (r * r + 1.0)  # projection of (w1, h1) onto (r, 1)
        t1 = max(t_min, t1)
        nw, nh = r * t1, t1
        if sx > 0:
            left, right = -hw, -hw + nw
        else:
            left, right = hw - nw, hw
        if sy > 0:
            top, bottom = -hh, -hh + nh
        else:
            top, bottom = hh - nh, hh
    elif sx != 0:
        nw = max(t_min * r, start.w + sx * dx)
        nh = nw / r
        left, right = (-hw, -hw + nw) if sx > 0 else (hw - nw, hw)
        top, bottom = -nh / 2.0, nh / 2.0
    else:
        nh = max(t_min, start.h + sy * dy)
        nw = nh * r
        top, bottom = (-hh, -hh + nh) if sy > 0 else (hh - nh, hh)
        left, right = -nw / 2.0, nw / 2.0
    target = _from_local(start, left, top, right, bottom)
    return _lerp_crop(start, target, _max_step(start, target, bounds))


# --------------------------------------------------------------------------- orientation actions

def _map_point_rot_cw(p: Point, size: Size) -> Point:
    return size[1] - p[1], p[0]


def rotate90(state: EditState, clockwise: bool = True) -> EditState:
    """Rotate the whole picture a quarter turn; the selected content stays selected."""
    o = state.orientation
    W, H = state.oriented_size
    c = state.crop
    if clockwise:
        cx, cy = H - c.cy, c.cx
        k = o.rot90 - 1 if o.flip else o.rot90 + 1
    else:
        cx, cy = c.cy, W - c.cx
        k = o.rot90 + 1 if o.flip else o.rot90 - 1
    crop = CropGeometry(cx, cy, c.h, c.w, c.angle)
    aspect = None if state.aspect is None else 1.0 / state.aspect
    new = replace(state, orientation=Orientation(k, o.flip), crop=crop, aspect=aspect)
    return new.with_crop(clamp_center(new.crop, new.oriented_size))


def flip(state: EditState, horizontal: bool = True) -> EditState:
    """Mirror the picture; the selected content stays selected."""
    o = state.orientation
    W, H = state.oriented_size
    c = state.crop
    if horizontal:
        crop = CropGeometry(W - c.cx, c.cy, c.w, c.h, -c.angle)
        orient = Orientation(o.rot90, not o.flip)
    else:  # V = H-flip followed by a half turn
        crop = CropGeometry(c.cx, H - c.cy, c.w, c.h, -c.angle)
        orient = Orientation(o.rot90 + 2, not o.flip)
    return replace(state, orientation=orient, crop=crop)


def orientation_matrix(orientation: Orientation, source_size: Size) -> tuple[tuple[float, ...], ...]:
    """3x3 affine (row-major) mapping continuous S coordinates to O coordinates."""
    W, H = source_size
    k = orientation.rot90
    if k == 0:
        m = ((1, 0, 0), (0, 1, 0))
        ow = W
    elif k == 1:  # (x, y) -> (H - y, x)
        m = ((0, -1, H), (1, 0, 0))
        ow = H
    elif k == 2:  # (x, y) -> (W - x, H - y)
        m = ((-1, 0, W), (0, -1, H))
        ow = W
    else:  # (x, y) -> (y, W - x)
        m = ((0, 1, 0), (-1, 0, W))
        ow = H
    if orientation.flip:  # (x, y) -> (ow - x, y) applied after the rotation
        m = ((-m[0][0], -m[0][1], ow - m[0][2]), m[1])
    return (tuple(float(v) for v in m[0]), tuple(float(v) for v in m[1]), (0.0, 0.0, 1.0))


# --------------------------------------------------------------------------- view

@dataclass(frozen=True)
class View:
    """Maps O space to screen: ``screen = center + zoom * R(angle) * (p - focus)``.

    The crop frame is axis-aligned on screen; the image is drawn rotated.
    """

    focus: Point  # O-space point shown at ``center``
    center: Point  # screen point
    zoom: float
    angle: float

    def to_screen(self, p: Point) -> Point:
        a = math.radians(self.angle)
        c, s = math.cos(a), math.sin(a)
        x, y = p[0] - self.focus[0], p[1] - self.focus[1]
        return (
            self.center[0] + self.zoom * (x * c - y * s),
            self.center[1] + self.zoom * (x * s + y * c),
        )

    def to_image(self, q: Point) -> Point:
        a = math.radians(self.angle)
        c, s = math.cos(a), math.sin(a)
        x, y = (q[0] - self.center[0]) / self.zoom, (q[1] - self.center[1]) / self.zoom
        return self.focus[0] + x * c + y * s, self.focus[1] - x * s + y * c

    def delta_to_image(self, d: Point) -> Point:
        """Screen displacement -> O displacement."""
        a = math.radians(self.angle)
        c, s = math.cos(a), math.sin(a)
        x, y = d[0] / self.zoom, d[1] / self.zoom
        return x * c + y * s, -x * s + y * c

    def frame_rect(self, crop: CropGeometry) -> tuple[float, float, float, float]:
        """On-screen (x, y, w, h) of the crop frame."""
        cx, cy = self.to_screen((crop.cx, crop.cy))
        w, h = crop.w * self.zoom, crop.h * self.zoom
        return cx - w / 2.0, cy - h / 2.0, w, h


def fit_view(crop: CropGeometry, viewport: tuple[float, float, float, float], margin: float = 24.0) -> View:
    """View that centres the crop frame in ``viewport`` (x, y, w, h) as large as possible."""
    vx, vy, vw, vh = viewport
    aw, ah = max(1.0, vw - 2 * margin), max(1.0, vh - 2 * margin)
    z = min(aw / crop.w, ah / crop.h)
    return View((crop.cx, crop.cy), (vx + vw / 2.0, vy + vh / 2.0), z, crop.angle)
