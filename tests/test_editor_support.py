"""Tests for editor history, the metadata-preserving saver and auto-straighten."""
import cv2
import numpy as np
import pytest
from PIL import Image

from image_classifier.editor import geometry as g
from image_classifier.editor import render as R
from image_classifier.editor.auto_straighten import estimate_angle
from image_classifier.editor.history import EditHistory
from image_classifier.editor.state import EditState
from image_classifier.imaging.saver import save_rgba


# ----------------------------------------------------------------- history

def test_history_undo_redo_and_dirty():
    s0 = EditState.initial((100, 80))
    h = EditHistory(s0)
    assert not h.can_undo() and not h.is_dirty
    s1 = s0.with_adjust(contrast=10)
    s2 = s1.with_adjust(exposure=-5)
    assert h.push(s1) and h.push(s2)
    assert not h.push(s2)  # duplicate ignored
    assert h.undo() == s1 and h.undo() == s0 and h.undo() == s0
    assert h.redo() == s1
    h.push(s0.with_adjust(tint=3))
    assert not h.can_redo()
    assert h.is_dirty


def test_history_limit_keeps_initial():
    s0 = EditState.initial((100, 80))
    h = EditHistory(s0, limit=5)
    for v in range(1, 20):
        h.push(s0.with_adjust(contrast=v))
    assert h.initial == s0
    assert h.current.adjust.contrast == 19


# ----------------------------------------------------------------- saver

def _rgba(w=64, h=48, alpha=255):
    arr = np.zeros((h, w, 4), np.uint8)
    arr[..., 0] = np.linspace(0, 255, w, dtype=np.uint8)[None, :]
    arr[..., 1] = 120
    arr[..., 3] = alpha
    return arr


def _jpeg_with_exif(path, orientation=6):
    img = Image.fromarray(_rgba()[..., :3], "RGB")
    exif = Image.Exif()
    exif[0x0112] = orientation
    exif[0x010F] = "TestCam"  # Make
    img.save(path, format="JPEG", exif=exif.tobytes(), quality=90)


def test_save_jpeg_keeps_exif_and_resets_orientation(tmp_path):
    src = tmp_path / "src.jpg"
    _jpeg_with_exif(src)
    out = tmp_path / "out.jpg"
    save_rgba(str(out), _rgba(), source_path=str(src))
    with Image.open(out) as img:
        exif = img.getexif()
        assert exif[0x0112] == 1
        assert exif[0x010F] == "TestCam"
        assert img.size == (64, 48)


def test_overwrite_in_place_is_atomic_and_keeps_exif(tmp_path):
    src = tmp_path / "photo.jpg"
    _jpeg_with_exif(src)
    save_rgba(str(src), _rgba(32, 32), source_path=str(src))
    with Image.open(src) as img:
        assert img.size == (32, 32)
        assert img.getexif()[0x010F] == "TestCam"
    assert [p.name for p in tmp_path.iterdir()] == ["photo.jpg"]  # no temp files left


def test_png_keeps_alpha_and_jpeg_flattens(tmp_path):
    arr = _rgba(alpha=100)
    save_rgba(str(tmp_path / "a.png"), arr)
    with Image.open(tmp_path / "a.png") as img:
        assert img.mode == "RGBA" and np.asarray(img)[..., 3].max() == 100
    save_rgba(str(tmp_path / "a.jpg"), arr)
    with Image.open(tmp_path / "a.jpg") as img:
        assert img.mode == "RGB"


def test_unsupported_extension_raises(tmp_path):
    with pytest.raises(OSError):
        save_rgba(str(tmp_path / "x.xyz"), _rgba())


def test_heic_roundtrip(tmp_path):
    pytest.importorskip("pillow_heif")
    out = tmp_path / "a.heic"
    save_rgba(str(out), _rgba())
    from image_classifier.imaging.loader import _ensure_heif_registered
    _ensure_heif_registered()
    with Image.open(out) as img:
        assert img.size == (64, 48)


# ----------------------------------------------------------------- auto-straighten

def _scene(w=900, h=600):
    img = np.full((h, w), 90, np.uint8)
    for y in range(80, h, 110):
        cv2.line(img, (0, y), (w, y), 230, 3)
    for x in range(120, w, 160):
        cv2.line(img, (x, 0), (x, h), 20, 3)
    cv2.rectangle(img, (300, 200), (600, 420), 250, -1)
    return img


@pytest.mark.parametrize("tilt", [-12.0, -6.6, -2.0, 0.0, 3.5, 9.0, 18.0])
def test_auto_straighten_recovers_tilt_and_levels_image(tilt):
    scene = _scene()
    h, w = scene.shape
    m = cv2.getRotationMatrix2D((w / 2, h / 2), tilt, 1.0)  # cv2: positive = counter-clockwise
    rotated = cv2.warpAffine(scene, m, (w, h), borderMode=cv2.BORDER_REFLECT)
    est = estimate_angle(rotated)
    assert est is not None
    # Self-consistency in editor terms: applying the estimate must level the image.
    rgba = np.dstack([rotated] * 3 + [np.full_like(rotated, 255)])
    state = EditState.initial((w, h))
    state = state.with_crop(g.fit_to_angle(state.crop, est, (w, h)))
    levelled = R.render(rgba, state)
    residual = estimate_angle(levelled)
    assert residual is not None and abs(residual) <= 0.5, (tilt, est, residual)
    assert abs(abs(est) - abs(tilt)) <= 0.5


def test_auto_straighten_rejects_noise():
    rng = np.random.default_rng(0)
    noise = cv2.GaussianBlur(rng.integers(0, 255, (500, 700), dtype=np.uint8), (3, 3), 0)
    assert estimate_angle(noise) is None
