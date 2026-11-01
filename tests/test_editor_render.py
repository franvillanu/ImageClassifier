"""Tests for the editor renderer (geometry warp + adjustments)."""
from dataclasses import replace

import numpy as np
import pytest

from image_classifier.editor import geometry as g
from image_classifier.editor import render as R
from image_classifier.editor.state import Adjustments, CropGeometry, EditState, Orientation


def _checker(w=300, h=200):
    y, x = np.mgrid[0:h, 0:w]
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 0] = (x * 255 // max(1, w - 1)).astype(np.uint8)
    rgba[..., 1] = (y * 255 // max(1, h - 1)).astype(np.uint8)
    rgba[..., 2] = (((x // 10) + (y // 10)) % 2 * 255).astype(np.uint8)
    rgba[..., 3] = 255
    return rgba


def test_unrotated_crop_is_bit_exact_slice():
    src = _checker()
    state = EditState.initial((300, 200)).with_crop(CropGeometry(150, 80, 100, 60, 0.0))
    out = R.render(src, state)
    assert out.shape == (60, 100, 4)
    assert np.array_equal(out, src[50:110, 100:200])


def test_identity_state_returns_source_pixels():
    src = _checker()
    out = R.render(src, EditState.initial((300, 200)))
    assert np.array_equal(out, src)


@pytest.mark.parametrize("k", range(4))
@pytest.mark.parametrize("flipped", [False, True])
def test_orientation_matches_numpy_and_warp_path(k, flipped):
    src = _checker(30, 20)
    state = EditState((30, 20), Orientation(k, flipped))
    fast = R.render(src, state)
    expected = np.rot90(src, -k)
    if flipped:
        expected = expected[:, ::-1]
    assert np.array_equal(fast, expected)
    # Force the general affine path with a tiny non-integer offset and compare.
    W, H = state.oriented_size
    slow = R.warp(src, state.with_crop(CropGeometry(W / 2 + 1e-4, H / 2, W - 1e-3, H, 0.0)), (W, H))
    assert np.abs(slow.astype(int) - expected.astype(int)).mean() < 2.0


def test_rotated_crop_dimensions():
    src = _checker()
    crop = g.fit_to_angle(CropGeometry(150, 100, 300, 200, 0.0), 12.0, (300, 200))
    state = EditState.initial((300, 200)).with_crop(crop)
    out = R.render(src, state)
    assert out.shape[:2] == (round(crop.h), round(crop.w))


def test_no_empty_corners_at_any_angle():
    """Regression for the old crop: a maximal straightened crop must contain only image content."""
    h, w = 240, 360
    src = np.zeros((h, w, 4), np.uint8)
    src[..., :3] = 200  # opaque mid-grey; any empty/border wedge would show up as alpha != 255 or black
    src[..., 3] = 255
    rng = np.random.default_rng(7)
    base = EditState.initial((w, h))
    for angle in list(np.linspace(-45, 45, 19)) + list(rng.uniform(-45, 45, 20)):
        for aspect in (None, 1.0, 16 / 9, 9 / 16):
            crop = g.set_aspect(base.crop, aspect, (w, h)) if aspect else base.crop
            crop = g.fit_to_angle(crop, float(angle), (w, h))
            # push it into a corner too
            for delta in ((0, 0), (-1e6, -1e6), (1e6, 1e6), (1e6, -1e6)):
                c = g.pan(crop, delta, (w, h))
                out = R.render(src, base.with_crop(c))
                assert out[..., 3].min() == 255, (angle, aspect, delta)
                assert out[..., :3].min() >= 199, (angle, aspect, delta)


def test_render_from_proxy_matches_full_render():
    full = _checker(600, 400)
    proxy = R.downscale(full, 300)
    crop = g.fit_to_angle(CropGeometry(300, 200, 400, 300, 0.0), -6.6, (600, 400))
    state = EditState.initial((600, 400)).with_crop(crop)
    small = R.render(proxy, state, scale=0.5)
    big = R.downscale(R.render(full, state), max(small.shape[:2][::-1]))
    assert small.shape == big.shape
    assert np.abs(small[..., :3].astype(int) - big[..., :3].astype(int)).mean() < 12


def test_strip_warp_matches_single_strip():
    src = _checker(500, 300)
    crop = g.fit_to_angle(CropGeometry(250, 150, 400, 250, 0.0), 9.0, (500, 300))
    state = EditState.initial((500, 300)).with_crop(crop)
    size = R.output_size(state)
    a = R.warp(src, state, size, strip_rows=37)
    b = R.warp(src, state, size, strip_rows=10_000)
    assert np.array_equal(a, b)


def test_adjustments_keep_alpha():
    src = _checker()
    src[..., 3] = 128
    state = EditState.initial((300, 200)).with_adjust(exposure=40, vignette=-50, sharpness=40)
    out = R.render(src, state)
    assert np.all(out[..., 3] == 128)
    assert not np.array_equal(out[..., :3], src[..., :3])


def test_rotate90_render_selects_same_content():
    src = _checker(300, 200)
    s0 = EditState.initial((300, 200)).with_crop(CropGeometry(100, 60, 80, 40, 0.0))
    a = R.render(src, s0)
    b = R.render(src, g.rotate90(s0, True))
    assert np.array_equal(np.rot90(a, -1), b)
    c = R.render(src, g.flip(s0, True))
    assert np.array_equal(a[:, ::-1], c)
