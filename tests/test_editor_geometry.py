"""Property-style tests for the crop geometry: the crop must never leave the image."""
import math
from dataclasses import replace

import numpy as np
import pytest

from image_classifier.editor import geometry as g
from image_classifier.editor.state import CropGeometry, EditState, Orientation

BOUNDS = [(4000, 3000), (3000, 4000), (1157, 1033), (64, 4000), (20, 20)]


def _rand_crop(rng, bounds):
    W, H = bounds
    angle = float(rng.uniform(-45, 45))
    w = float(rng.uniform(0.05, 1.0) * W)
    h = float(rng.uniform(0.05, 1.0) * H)
    crop = CropGeometry(float(rng.uniform(0, W)), float(rng.uniform(0, H)), w, h, angle)
    return g.fit_to_angle(crop, angle, bounds)


def _assert_valid(crop, bounds, min_size=None):
    assert g.is_valid(crop, bounds), (crop, bounds)
    for x, y in g.corners(crop):
        assert -1e-6 * max(bounds) <= x <= bounds[0] * (1 + 1e-9) + 1e-6
        assert -1e-6 * max(bounds) <= y <= bounds[1] * (1 + 1e-9) + 1e-6
    if min_size is not None:
        assert crop.w >= min_size - 1e-6 and crop.h >= min_size - 1e-6


def test_half_extents_matches_corners():
    crop = CropGeometry(50, 40, 30, 10, 17.0)
    ex, ey = g.half_extents(crop.w, crop.h, crop.angle)
    xs = [p[0] for p in g.corners(crop)]
    ys = [p[1] for p in g.corners(crop)]
    assert math.isclose(max(xs) - min(xs), 2 * ex)
    assert math.isclose(max(ys) - min(ys), 2 * ey)


@pytest.mark.parametrize("bounds", BOUNDS)
def test_default_crop_is_full_image(bounds):
    crop = g.default_crop(bounds)
    assert (crop.cx, crop.cy, crop.w, crop.h, crop.angle) == (bounds[0] / 2, bounds[1] / 2, bounds[0], bounds[1], 0)
    _assert_valid(crop, bounds)


@pytest.mark.parametrize("bounds", BOUNDS)
def test_fit_to_angle_always_valid_and_reversible(bounds):
    rng = np.random.default_rng(1)
    base = g.default_crop(bounds)
    for _ in range(300):
        angle = float(rng.uniform(-45, 45))
        crop = g.fit_to_angle(base, angle, bounds)
        _assert_valid(crop, bounds)
        assert math.isclose(crop.w / crop.h, base.w / base.h, rel_tol=1e-9)
    back = g.fit_to_angle(base, 0.0, bounds)
    assert back == base


def test_fit_to_angle_full_image_is_largest_inscribed_rect():
    bounds = (4000, 3000)
    crop = g.fit_to_angle(g.default_crop(bounds), 10.0, bounds)
    # Corners touch the image edges: the rect cannot grow at its centre.
    assert math.isclose(g.scale_at_center(crop, bounds), 1.0, rel_tol=1e-9)
    assert (crop.cx, crop.cy) == (2000, 1500)


@pytest.mark.parametrize("bounds", BOUNDS)
def test_random_gestures_never_leave_image(bounds):
    rng = np.random.default_rng(42)
    min_size = g.min_size_for(bounds)
    handles = list(g.HANDLES)
    aspects = [None, 1.0, 16 / 9, 9 / 16, 4 / 3, bounds[0] / bounds[1]]
    for _ in range(2000):
        crop = _rand_crop(rng, bounds)
        aspect = aspects[rng.integers(len(aspects))]
        if aspect is not None:
            crop = g.set_aspect(crop, aspect, bounds)
            _assert_valid(crop, bounds)
            assert math.isclose(crop.w / crop.h, aspect, rel_tol=1e-6)
        op = rng.integers(4)
        scale = max(bounds) * 2
        if op == 0:
            out = g.resize_handle(
                crop, handles[rng.integers(len(handles))],
                (float(rng.uniform(-scale, scale)), float(rng.uniform(-scale, scale))),
                aspect, bounds, min_size,
            )
            if aspect is not None:
                assert math.isclose(out.w / out.h, aspect, rel_tol=1e-6)
            _assert_valid(out, bounds, min_size=min(min_size, crop.w, crop.h))
        elif op == 1:
            out = g.pan(crop, (float(rng.uniform(-scale, scale)), float(rng.uniform(-scale, scale))), bounds)
            assert math.isclose(out.w, crop.w) and math.isclose(out.h, crop.h)
            _assert_valid(out, bounds)
        elif op == 2:
            factor = float(np.exp(rng.uniform(-3, 3)))
            anchor = (float(rng.uniform(0, bounds[0])), float(rng.uniform(0, bounds[1])))
            out = g.zoom(crop, factor, anchor, bounds, min_size)
            assert math.isclose(out.w / out.h, crop.w / crop.h, rel_tol=1e-6)
            _assert_valid(out, bounds, min_size=min(min_size, crop.w, crop.h))
        else:
            out = g.fit_to_angle(crop, float(rng.uniform(-45, 45)), bounds)
            _assert_valid(out, bounds)


def test_ratio_corner_drag_uses_both_axes():
    bounds = (4000, 4000)
    crop = CropGeometry(2000, 2000, 1000, 1000, 0.0)
    only_y = g.resize_handle(crop, "bottom_right", (0, 400), 1.0, bounds)
    assert only_y.w > crop.w and math.isclose(only_y.w, only_y.h)
    # Anchored at the opposite (top-left) corner.
    tl = g.corners(only_y)[0]
    assert math.isclose(tl[0], 1500) and math.isclose(tl[1], 1500)


def test_resize_cannot_collapse_below_min_size():
    bounds = (1000, 1000)
    crop = CropGeometry(500, 500, 400, 300, 0.0)
    for handle in g.HANDLES:
        for aspect in (None, 4 / 3):
            out = g.resize_handle(crop, handle, (-5000, -5000), aspect, bounds, 16)
            out2 = g.resize_handle(crop, handle, (5000, 5000), aspect, bounds, 16)
            for o in (out, out2):
                assert o.w >= 16 - 1e-9 and o.h >= 16 - 1e-9
                _assert_valid(o, bounds)


def test_free_edge_drag_keeps_opposite_edge():
    bounds = (1000, 1000)
    crop = CropGeometry(500, 500, 400, 300, 0.0)
    out = g.resize_handle(crop, "right", (50, 999), None, bounds)
    assert math.isclose(out.w, 450) and math.isclose(out.h, 300)
    assert math.isclose(out.cx - out.w / 2, 300)


def test_free_corner_slides_along_edge():
    bounds = (1000, 1000)
    crop = CropGeometry(500, 500, 200, 200, 0.0)
    # Pointer goes far right but only a little down: x saturates at the image edge, y keeps following.
    out = g.resize_handle(crop, "bottom_right", (5000, 100), None, bounds)
    assert math.isclose(out.cx + out.w / 2, 1000)
    assert math.isclose(out.h, 300)


def test_pan_stops_at_edges():
    bounds = (1000, 800)
    crop = CropGeometry(500, 400, 200, 200, 0.0)
    out = g.pan(crop, (-10_000, 0), bounds)
    assert math.isclose(out.cx, 100) and math.isclose(out.cy, 400)


def test_zoom_out_capped_at_fit():
    bounds = (1000, 800)
    crop = CropGeometry(500, 400, 200, 100, 0.0)
    out = g.zoom(crop, 0.001, None, bounds)
    assert math.isclose(g.fit_scale(out.w, out.h, out.angle, bounds), 1.0, rel_tol=1e-9)


def _state(size=(4000, 3000), **kw):
    return EditState.initial(size).with_crop(CropGeometry(**kw)) if kw else EditState.initial(size)


@pytest.mark.parametrize("clockwise", [True, False])
def test_rotate90_four_times_is_identity(clockwise):
    s0 = _state(cx=1200, cy=900, w=800, h=500, angle=7.5)
    s = s0
    for _ in range(4):
        s = g.rotate90(s, clockwise)
        assert g.is_valid(s.crop, s.oriented_size)
    assert s.orientation == s0.orientation
    for a, b in zip((s.crop.cx, s.crop.cy, s.crop.w, s.crop.h, s.crop.angle),
                    (s0.crop.cx, s0.crop.cy, s0.crop.w, s0.crop.h, s0.crop.angle)):
        assert math.isclose(a, b, abs_tol=1e-9)


@pytest.mark.parametrize("horizontal", [True, False])
def test_flip_twice_is_identity(horizontal):
    s0 = _state(cx=1200, cy=900, w=800, h=500, angle=7.5)
    s = g.flip(g.flip(s0, horizontal), horizontal)
    assert s == s0


def test_rotate_cw_then_ccw_is_identity_with_flip():
    s0 = g.flip(_state(cx=1200, cy=900, w=800, h=500, angle=-3.0), True)
    assert g.rotate90(g.rotate90(s0, True), False) == s0


def test_rotate90_swaps_aspect():
    s = replace(_state(cx=2000, cy=1500, w=1600, h=900, angle=0.0), aspect=16 / 9)
    r = g.rotate90(s)
    assert math.isclose(r.aspect, 9 / 16)
    assert (r.crop.w, r.crop.h) == (900, 1600)


def _apply(m, p):
    return (m[0][0] * p[0] + m[0][1] * p[1] + m[0][2], m[1][0] * p[0] + m[1][1] * p[1] + m[1][2])


@pytest.mark.parametrize("k", range(4))
@pytest.mark.parametrize("flipped", [False, True])
def test_orientation_matrix_maps_onto_oriented_bounds(k, flipped):
    size = (40, 30)
    o = Orientation(k, flipped)
    m = g.orientation_matrix(o, size)
    W, H = EditState(size, o).oriented_size
    pts = [_apply(m, p) for p in ((0, 0), (40, 0), (0, 30), (40, 30))]
    assert sorted({round(x) for x, _ in pts}) == [0, W]
    assert sorted({round(y) for _, y in pts}) == [0, H]


def test_actions_consistent_with_orientation_matrix():
    """After rotate/flip, the crop centre must still point at the same source pixel."""
    size = (400, 300)
    s0 = _state(size, cx=120, cy=90, w=80, h=50, angle=0.0)
    src_point = (120, 90)  # orientation is identity at start
    rng = np.random.default_rng(3)
    s = s0
    for _ in range(50):
        op = rng.integers(4)
        s = (g.rotate90(s, True) if op == 0 else g.rotate90(s, False) if op == 1
             else g.flip(s, True) if op == 2 else g.flip(s, False))
        m = g.orientation_matrix(s.orientation, size)
        x, y = _apply(m, src_point)
        assert math.isclose(x, s.crop.cx, abs_tol=1e-9) and math.isclose(y, s.crop.cy, abs_tol=1e-9)


def test_view_roundtrip_and_frame_axis_aligned():
    crop = CropGeometry(1000, 700, 600, 400, -6.6)
    view = g.fit_view(crop, (0, 0, 1600, 1000))
    for p in [(0, 0), (1000, 700), (1234.5, 321.0)]:
        q = view.to_screen(p)
        back = view.to_image(q)
        assert math.isclose(back[0], p[0], abs_tol=1e-9) and math.isclose(back[1], p[1], abs_tol=1e-9)
    xs = [view.to_screen(c) for c in g.corners(crop)]
    # On screen the frame is axis aligned: TL/TR share y, TL/BL share x.
    assert math.isclose(xs[0][1], xs[1][1], abs_tol=1e-6)
    assert math.isclose(xs[0][0], xs[3][0], abs_tol=1e-6)
    x, y, w, h = view.frame_rect(crop)
    assert math.isclose(x + w / 2, 800) and math.isclose(y + h / 2, 500)
