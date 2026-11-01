"""Automatic enhancement: sensible directions, gentle amounts, near no-op on a good photo."""
import numpy as np

from image_classifier.editor import auto_enhance
from image_classifier.editor.adjust import apply_adjustments
from image_classifier.editor.state import Adjustments


def _scene(h=300, w=400, seed=0):
    """A well-exposed scene: full tonal range, neutral on average, with some colour and texture."""
    rng = np.random.default_rng(seed)
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    light = 0.06 + 0.88 * (x / (w - 1)) ** 1.1  # shadows to highlights, left to right
    hue = (x + 1.7 * y) / 40.0
    base = np.stack([light + 0.12 * np.sin(hue), light + 0.12 * np.sin(hue + 2.09),
                     light + 0.12 * np.sin(hue + 4.19)], axis=-1)
    base += rng.normal(0, 0.03, base.shape)
    return (np.clip(base, 0, 1) * 255).astype(np.uint8)


def _luma(img):
    return float((img.astype(np.float32) @ [0.2126, 0.7152, 0.0722]).mean())


def test_balanced_photo_is_left_mostly_alone():
    est = auto_enhance.estimate(_scene())
    assert set(est) == set(auto_enhance.MANAGED)
    assert all(abs(v) <= 15 for v in est.values()), est


def _drawing(paper=(214, 204, 186), gain=1.0):
    """A sketch on cream paper, photographed indoors: mostly light paper, some dark lines and colour."""
    img = np.empty((300, 240, 3), np.float32)
    img[:] = paper
    img[60:140, 50:190] = (80, 82, 88)  # hair
    img[140:220, 70:170] = (190, 150, 130)  # face
    img[230:280, 40:200] = (196, 80, 55)  # sweater
    img[::25, 30:210] = (60, 50, 50)  # pencil lines
    return np.clip(img * gain, 0, 255).astype(np.uint8)


def test_dark_photo_gets_brighter_and_bright_photo_never_brighter():
    scene = _scene()
    dark = (scene * 0.25).astype(np.uint8)
    bright = np.clip(scene.astype(np.int32) + 110, 0, 255).astype(np.uint8)
    assert auto_enhance.estimate(dark)["exposure"] > 20
    est = auto_enhance.estimate(bright)
    assert est["exposure"] == 0 and est["brightness"] == 0 and est["highlights"] < 0


def test_light_photo_is_never_darkened():
    """A drawing on paper is light on purpose: Auto lifts it to white instead of pulling it to grey."""
    for gain in (0.7, 0.85, 1.0, 1.1):
        img = _drawing(gain=gain)
        est = auto_enhance.estimate(img)
        assert est["exposure"] >= 0 and est["highlights"] == 0, (gain, est)
        assert _luma(apply_adjustments(img, Adjustments(**est))) >= _luma(img), (gain, est)


def test_unclipped_photos_never_get_darker():
    rng = np.random.default_rng(3)
    for _ in range(30):
        img = (_scene(seed=int(rng.integers(1000))).astype(np.float32) * rng.uniform(0.2, 0.95)
               + rng.uniform(0, 30)).astype(np.uint8)
        est = auto_enhance.estimate(img)
        assert _luma(apply_adjustments(img, Adjustments(**est))) >= _luma(img) * 0.99, est


def test_cream_paper_is_whitened_but_blue_sky_is_not_warmed():
    assert auto_enhance.estimate(_drawing())["warmth"] < 0
    sky = np.zeros((300, 400, 3), np.uint8)
    sky[:150] = (172, 202, 230)
    sky[150:] = (60, 100, 45)
    assert auto_enhance.estimate(sky)["warmth"] == 0


def test_snow_is_left_alone():
    snow = np.clip(240 + np.random.default_rng(0).normal(0, 6, (300, 400, 3)), 0, 255).astype(np.uint8)
    assert all(v == 0 for v in auto_enhance.estimate(snow).values())


def test_result_moves_a_dark_photo_towards_a_normal_one():
    dark = (_scene() * 0.3).astype(np.uint8)
    fixed = apply_adjustments(dark, Adjustments(**auto_enhance.estimate(dark)))
    assert _luma(fixed) > _luma(dark) * 1.5


def test_flat_photo_gets_contrast_and_dull_colour_gets_saturation():
    scene = _scene().astype(np.float32)
    grey = scene.mean(axis=-1, keepdims=True)
    flat = (128 + (scene - 128) * 0.35).astype(np.uint8)
    dull = (grey + (scene - grey) * 0.2).astype(np.uint8)
    assert auto_enhance.estimate(flat)["contrast"] > 10
    assert auto_enhance.estimate(dull)["saturation"] > 5


def test_blue_cast_is_warmed_and_orange_cast_is_cooled():
    scene = _scene().astype(np.float32)
    blue = np.clip(scene * [0.8, 0.95, 1.2], 0, 255).astype(np.uint8)
    orange = np.clip(scene * [1.2, 1.0, 0.75], 0, 255).astype(np.uint8)
    assert auto_enhance.estimate(blue)["warmth"] > 0
    assert auto_enhance.estimate(orange)["warmth"] < 0


def test_grey_photo_gets_no_colour_correction():
    grey = np.repeat(_scene().mean(axis=-1, keepdims=True), 3, axis=-1).astype(np.uint8)
    assert auto_enhance.estimate(grey)["warmth"] == 0


def test_clipped_highlights_are_pulled_back():
    scene = _scene().astype(np.int32)
    scene[:120] = 255  # a blown-out sky
    est = auto_enhance.estimate(scene.astype(np.uint8))
    assert est["highlights"] < 0


def test_accepts_rgba():
    rgba = np.dstack([_scene(), np.full((300, 400), 255, np.uint8)])
    assert set(auto_enhance.estimate(rgba)) == set(auto_enhance.MANAGED)
