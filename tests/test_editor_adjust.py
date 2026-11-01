"""Tests for the Ajuste pipeline."""
import cv2
import numpy as np
import pytest

from image_classifier.editor import adjust as A
from image_classifier.editor.state import Adjustments


def _photo(w=640, h=480, seed=0):
    """Smooth synthetic 'photo': gradients + blobs + mild noise, full tonal range."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    r = 0.5 + 0.5 * np.sin(x / w * 6.0)
    g = y / h
    b = 0.5 + 0.5 * np.cos((x + y) / (w + h) * 9.0)
    img = np.stack([r, g, b], axis=-1)
    img += rng.normal(0, 0.01, img.shape).astype(np.float32)
    return (np.clip(img, 0, 1) * 255).astype(np.uint8)


def _psnr(a, b):
    mse = np.mean((a.astype(np.float64) - b.astype(np.float64)) ** 2)
    return float("inf") if mse == 0 else 10 * np.log10(255.0 ** 2 / mse)


def test_identity_is_bit_exact_passthrough():
    img = _photo()
    out = A.apply_adjustments(img, Adjustments())
    assert out is img


@pytest.mark.parametrize("name", Adjustments.names())
def test_every_slider_changes_image_and_keeps_shape(name):
    img = _photo()
    for v in (-100, 100):
        out = A.apply_adjustments(img, Adjustments(**{name: v}))
        assert out.shape == img.shape and out.dtype == np.uint8
        assert not np.array_equal(out, img), (name, v)


def test_exposure_and_brightness_are_monotonic():
    img = _photo()
    for name in ("exposure", "brightness", "shadows"):
        means = [A.apply_adjustments(img, Adjustments(**{name: v})).mean() for v in (-100, -50, 0, 50, 100)]
        assert means == sorted(means), (name, means)


def test_contrast_increases_spread():
    img = _photo()
    stds = [A.apply_adjustments(img, Adjustments(contrast=v)).std() for v in (-100, 0, 100)]
    assert stds[0] < stds[1] < stds[2]


def test_tone_curve_keeps_endpoints_and_is_monotonic():
    x = np.linspace(0, 1, 1001)
    for b in (-1, -0.5, 0.5, 1):
        for c in (-1, -0.3, 0.3, 1):
            y = A.tone_curve(x.copy(), b, c)
            assert np.all(np.diff(y) >= -1e-12)
            if c >= 0:
                assert abs(y[0]) < 1e-12 and abs(y[-1] - 1) < 1e-12


def test_saturation_minus_100_is_grayscale():
    out = A.apply_adjustments(_photo(), Adjustments(saturation=-100)).astype(int)
    assert np.abs(out[..., 0] - out[..., 1]).max() <= 1
    assert np.abs(out[..., 1] - out[..., 2]).max() <= 1


def test_warmth_shifts_red_blue_balance():
    img = _photo()
    warm = A.apply_adjustments(img, Adjustments(warmth=60)).astype(float)
    cool = A.apply_adjustments(img, Adjustments(warmth=-60)).astype(float)
    ratio = lambda a: a[..., 0].mean() / max(1.0, a[..., 2].mean())
    assert ratio(warm) > ratio(img.astype(float)) > ratio(cool)


def test_vignette_leaves_centre_and_darkens_corners():
    img = np.full((400, 600, 3), 160, np.uint8)
    out = A.apply_adjustments(img, Adjustments(vignette=-80))
    assert np.array_equal(out[180:220, 280:320], img[180:220, 280:320])
    assert out[0, 0].mean() < 100 and out[-1, -1].mean() < 100
    light = A.apply_adjustments(img, Adjustments(vignette=80))
    assert light[0, 0].mean() > 200


def test_highlights_target_bright_and_shadows_target_dark():
    img = np.zeros((200, 400, 3), np.uint8)
    img[:, :200] = 40
    img[:, 200:] = 220
    hl = A.apply_adjustments(img, Adjustments(highlights=-100))
    sh = A.apply_adjustments(img, Adjustments(shadows=100))
    assert hl[:, 300:].mean() < 220 - 20 and abs(int(hl[:, 20:100].mean()) - 40) <= 2
    assert sh[:, 20:100].mean() > 40 + 15 and abs(int(sh[:, 300:380].mean()) - 220) <= 2


def test_strips_match_single_pass():
    img = _photo(500, 333)
    adj = Adjustments(highlights=-40, shadows=50, vignette=-60, contrast=20, saturation=30)
    plan = A.prepare(img, adj)
    whole = A.apply_rows(plan, img, 0)
    strips = np.concatenate([A.apply_rows(plan, img[y:y + 64], y) for y in range(0, 333, 64)])
    assert np.array_equal(whole, strips)


def test_preview_matches_full_resolution_render():
    """WYSIWYG: adjusting a proxy ~= downscaling the adjusted full image."""
    full = _photo(2400, 1600, seed=5)
    adj = Adjustments(exposure=20, contrast=30, highlights=-50, shadows=40, vignette=-40,
                      saturation=25, warmth=15, tint=-10, brightness=10)
    proxy = cv2.resize(full, (600, 400), interpolation=cv2.INTER_AREA)
    a = A.apply_adjustments(proxy, adj)
    b = cv2.resize(A.apply_adjustments(full, adj), (600, 400), interpolation=cv2.INTER_AREA)
    assert _psnr(a, b) >= 35.0
