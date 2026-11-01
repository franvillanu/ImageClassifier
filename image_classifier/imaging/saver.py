"""High-quality image saving that keeps the source's metadata.

Used by the photo editor: EXIF (with orientation reset to 1, since pixels are
saved upright) and the ICC profile are carried over from the source file, JPEG
is written at quality 95, and the write is atomic (temp file + replace) so a
failed save never corrupts the original.
"""
from __future__ import annotations

import os
import tempfile

import numpy as np
from PIL import Image

from image_classifier.imaging.loader import HEIF_EXTENSIONS, _ensure_heif_registered

EXIF_ORIENTATION = 0x0112
JPEG_QUALITY = 95
WEBP_QUALITY = 95
HEIF_QUALITY = 90

_FORMATS = {
    ".jpg": "JPEG", ".jpeg": "JPEG", ".jfif": "JPEG",
    ".png": "PNG", ".webp": "WEBP", ".bmp": "BMP", ".gif": "GIF",
    ".tif": "TIFF", ".tiff": "TIFF", ".heic": "HEIF", ".heif": "HEIF",
}


def _source_metadata(source_path: str | None) -> tuple[bytes | None, bytes | None]:
    if not source_path or not os.path.exists(source_path):
        return None, None
    try:
        if os.path.splitext(source_path)[1].lower() in HEIF_EXTENSIONS:
            _ensure_heif_registered()
        with Image.open(source_path) as img:
            icc = img.info.get("icc_profile")
            exif = img.getexif()
            if not exif:
                return None, icc
            if EXIF_ORIENTATION in exif:
                exif[EXIF_ORIENTATION] = 1
            return exif.tobytes(), icc
    except (OSError, ValueError, SyntaxError):
        return None, None


def _to_pil(arr: np.ndarray, keep_alpha: bool) -> Image.Image:
    if arr.ndim == 2:
        return Image.fromarray(arr, "L")
    if arr.shape[2] == 3:
        return Image.fromarray(np.ascontiguousarray(arr), "RGB")
    rgba = np.ascontiguousarray(arr)
    if keep_alpha and rgba[..., 3].min() < 255:
        return Image.fromarray(rgba, "RGBA")
    if rgba[..., 3].min() < 255:
        # Flatten onto white for formats without transparency.
        a = rgba[..., 3:4].astype(np.float32) / 255.0
        rgb = rgba[..., :3].astype(np.float32) * a + 255.0 * (1.0 - a)
        return Image.fromarray(np.clip(rgb + 0.5, 0, 255).astype(np.uint8), "RGB")
    return Image.fromarray(np.ascontiguousarray(rgba[..., :3]), "RGB")


def save_rgba(path: str, arr: np.ndarray, *, source_path: str | None = None) -> None:
    """Save an RGB/RGBA uint8 array to ``path``. Raises ``OSError`` on failure."""
    ext = os.path.splitext(path)[1].lower()
    fmt = _FORMATS.get(ext)
    if fmt is None:
        raise OSError(f"Unsupported file type: {ext or '(none)'}")
    exif, icc = _source_metadata(source_path)
    keep_alpha = fmt in ("PNG", "WEBP", "TIFF", "HEIF")
    img = _to_pil(arr, keep_alpha)

    kwargs = {}
    if exif and fmt in ("JPEG", "PNG", "WEBP", "TIFF", "HEIF"):
        kwargs["exif"] = exif
    if icc and fmt in ("JPEG", "PNG", "WEBP", "TIFF"):
        kwargs["icc_profile"] = icc
    if fmt == "JPEG":
        kwargs.update(quality=JPEG_QUALITY, subsampling=0 if JPEG_QUALITY >= 95 else 2)
    elif fmt == "WEBP":
        kwargs.update(quality=WEBP_QUALITY, method=4)
    elif fmt == "HEIF":
        _ensure_heif_registered()
        kwargs.update(quality=HEIF_QUALITY)
    elif fmt == "GIF":
        img = img.convert("RGB").quantize(colors=256, method=Image.Quantize.MEDIANCUT)
    elif fmt == "BMP":
        img = img.convert("RGB")

    folder = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(prefix=".edit-", suffix=ext, dir=folder)
    os.close(fd)
    try:
        img.save(tmp, format=fmt, **kwargs)
        os.replace(tmp, path)
    except (OSError, ValueError) as exc:
        try:
            os.remove(tmp)
        except OSError:
            pass
        raise OSError(str(exc)) from exc
