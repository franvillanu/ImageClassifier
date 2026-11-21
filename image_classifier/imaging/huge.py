"""Huge images (maps, orthomosaics): never decoded whole into the viewer (SPEC-007).

Everything here works on the file with Pillow and reports real progress: the fraction of the
file's bytes consumed so far. No Qt in this module; ``rotate_file`` imports the saver lazily.
"""
from __future__ import annotations

import io
import os
from contextlib import contextmanager
from typing import Callable, Optional

from PIL import Image

HUGE_PIXELS = 100_000_000          # HI-1
DETAIL_DIMENSION = 8192            # HI-4: long side of the detail frame
EXIF_ORIENTATION = 0x0112
EDIT_STRIP_ROWS = 512              # HI-10: output rows rendered per progress step

Progress = Callable[[str, Optional[float]], None]

# EXIF orientation -> the transpose that makes the stored pixels upright.
_ORIENTATION_OPS = {
    2: Image.Transpose.FLIP_LEFT_RIGHT,
    3: Image.Transpose.ROTATE_180,
    4: Image.Transpose.FLIP_TOP_BOTTOM,
    5: Image.Transpose.TRANSPOSE,
    6: Image.Transpose.ROTATE_270,
    7: Image.Transpose.TRANSVERSE,
    8: Image.Transpose.ROTATE_90,
}
# Clockwise quarter turns (what the viewer's R key does) -> Pillow transpose (counter-clockwise names).
_CLOCKWISE_OPS = {
    1: Image.Transpose.ROTATE_270,
    2: Image.Transpose.ROTATE_180,
    3: Image.Transpose.ROTATE_90,
}


def megapixels(width, height) -> int:
    return round(int(width) * int(height) / 1_000_000)


def status_text(state: str, percent: int, source_size, detail_px: int, lang: str, error: str = "") -> str:
    """HI-5: the status line for ``state`` in ("loading", "ready", "failed")."""
    from image_classifier.i18n.translations import translations

    t = translations.get(lang, translations["en"])
    width, height = source_size
    return t[f"huge_status_{state}"].format(
        w=width, h=height, mp=megapixels(width, height), pct=percent, detail=detail_px, error=error)


class Cancelled(Exception):
    """The caller no longer wants this job."""


def is_huge(width, height) -> bool:
    """HI-1: more than ``HUGE_PIXELS`` pixels."""
    return int(width) * int(height) > HUGE_PIXELS


@contextmanager
def _no_pixel_limit():
    """The viewer's own files are trusted: lift Pillow's decompression-bomb limit while we work."""
    previous = Image.MAX_IMAGE_PIXELS
    Image.MAX_IMAGE_PIXELS = None
    try:
        yield
    finally:
        Image.MAX_IMAGE_PIXELS = previous


class _ProgressReader(io.BufferedReader):
    """File that reports bytes consumed / file size (monotonic, whole percent steps) and can abort."""

    def __init__(self, path: str, report: Callable[[float], None], cancelled: Callable[[], bool]):
        super().__init__(io.FileIO(path, "rb"))
        self._total = max(1, os.path.getsize(path))
        self._done = 0
        self._last = -1
        self._report = report
        self._cancelled = cancelled

    def read(self, size=-1):
        if self._cancelled():
            raise Cancelled()
        data = super().read(size)
        self._done += len(data)
        percent = min(100, self._done * 100 // self._total)
        if percent != self._last:
            self._last = percent
            self._report(percent / 100.0)
        return data


def _never() -> bool:
    return False


def _prepare(path: str) -> None:
    """HEIC/HEIF need Pillow's plugin registered before ``Image.open``."""
    from image_classifier.imaging.loader import HEIF_EXTENSIONS, _ensure_heif_registered

    if os.path.splitext(path)[1].lower() in HEIF_EXTENSIONS:
        _ensure_heif_registered()


def _orientation_op(img: Image.Image):
    try:
        return _ORIENTATION_OPS.get(int(img.getexif().get(EXIF_ORIENTATION, 1)))
    except (TypeError, ValueError):
        return None


def _oriented_size(img: Image.Image, op) -> tuple[int, int]:
    width, height = img.size
    swaps = op in (Image.Transpose.TRANSPOSE, Image.Transpose.TRANSVERSE,
                   Image.Transpose.ROTATE_90, Image.Transpose.ROTATE_270)
    return (height, width) if swaps else (width, height)


def decode_reduced(path: str, max_dimension: int = DETAIL_DIMENSION, *,
                   progress: Optional[Callable[[float], None]] = None,
                   cancelled: Callable[[], bool] = _never):
    """HI-4: decode ``path`` at most ``max_dimension`` px on the long side, EXIF-upright.

    Returns ``(RGB image, (source_width, source_height))`` with the source size upright too.
    JPEGs are decoded with DCT scaling (fast); other formats are decoded whole and shrunk.
    """
    _prepare(path)
    reader = _ProgressReader(path, progress or (lambda _f: None), cancelled)
    try:
        with _no_pixel_limit():
            img = Image.open(reader)
            op = _orientation_op(img)
            source_size = _oriented_size(img, op)
            img.draft("RGB", (max_dimension, max_dimension))  # no-op except for JPEG
            img.load()
            if img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((max_dimension, max_dimension), Image.Resampling.BILINEAR)
            if op is not None:
                img = img.transpose(op)
            return img, source_size
    finally:
        reader.close()


def edit_file(src: str, dst: str, state, *, progress: Progress,
              cancelled: Callable[[], bool] = _never) -> None:
    """HI-10: render the editor's geometry (turn/flip, straighten, crop) from ``src`` into ``dst``.

    ``state`` is an editor ``EditState`` in true source pixels. The same matrix the editor uses
    (``output_to_source_matrix``) drives one Pillow resampling, done in strips of ``EDIT_STRIP_ROWS``
    output rows so progress is real: ``progress("render", fraction)`` per strip, then ``("write", None)``.
    Edges outside the photo (the editor keeps the crop inside) would be black, not replicated.
    Raises ``Cancelled`` or ``OSError``; ``dst`` may equal ``src`` (atomic replace, original kept on failure).
    """
    import numpy as np

    from image_classifier.editor.render import _integer_crop, output_size, output_to_source_matrix
    from image_classifier.imaging.saver import save_image

    _prepare(src)
    reader = _ProgressReader(src, lambda f: progress("read", f), cancelled)
    try:
        with _no_pixel_limit():
            img = Image.open(reader)
            exif_op = _orientation_op(img)
            try:
                img.load()
                reader.close()  # release the file: overwrite replaces it (Windows)
                if exif_op is not None:
                    rotated = img.transpose(exif_op)
                    img.close()
                    img = rotated
                if img.mode not in ("RGB", "RGBA", "L"):
                    converted = img.convert("RGB")
                    img.close()
                    img = converted
                if img.size != tuple(state.source_size):
                    raise OSError("The file changed while it was being edited.")
                out_w, out_h = output_size(state)
                matrix = output_to_source_matrix(state, (img.height, img.width), (out_w, out_h))
                half = np.array([[1, 0, 0.5], [0, 1, 0.5], [0, 0, 1.0]])
                unhalf = np.array([[1, 0, -0.5], [0, 1, -0.5], [0, 0, 1.0]])
                continuous = half @ matrix @ unhalf  # Pillow maps pixel centres, cv2-style indices differ by 0.5
                exact = _integer_crop(state, (img.height, img.width), (out_w, out_h)) is not None
                resample = Image.Resampling.NEAREST if exact else Image.Resampling.BICUBIC
                result = Image.new(img.mode, (out_w, out_h))
                try:
                    for y0 in range(0, out_h, EDIT_STRIP_ROWS):
                        if cancelled():
                            raise Cancelled()
                        rows = min(EDIT_STRIP_ROWS, out_h - y0)
                        m = continuous @ np.array([[1, 0, 0], [0, 1, y0], [0, 0, 1.0]])
                        strip = img.transform((out_w, rows), Image.Transform.AFFINE,
                                              tuple(float(v) for v in m[:2].ravel()), resample=resample)
                        result.paste(strip, (0, y0))
                        progress("render", (y0 + rows) / out_h)
                    if cancelled():
                        raise Cancelled()
                    progress("write", None)
                    save_image(dst, result, source_path=src)
                finally:
                    result.close()
            except MemoryError as exc:
                raise OSError("Not enough memory to process this image.") from exc
            finally:
                img.close()
    finally:
        reader.close()


def rotate_file(src: str, dst: str, quarter_turns: int, *, progress: Progress,
                cancelled: Callable[[], bool] = _never) -> None:
    """HI-6: write ``src`` rotated ``quarter_turns`` x 90° clockwise (and EXIF-upright) to ``dst``.

    Stages reported through ``progress(stage, fraction)``: ``"read"`` with a real fraction, then
    ``"rotate"`` and ``"write"`` with ``None`` (no honest percentage exists for those). ``dst`` may
    equal ``src``: the write is an atomic replace, so a failure or cancel leaves the original intact.
    Raises ``Cancelled`` or ``OSError``.
    """
    from image_classifier.imaging.saver import save_image

    _prepare(src)
    reader = _ProgressReader(src, lambda f: progress("read", f), cancelled)
    try:
        with _no_pixel_limit():
            img = Image.open(reader)
            ops = []
            exif_op = _orientation_op(img)
            if exif_op is not None:
                ops.append(exif_op)
            turn_op = _CLOCKWISE_OPS.get(int(quarter_turns) % 4)
            if turn_op is not None:
                ops.append(turn_op)
            try:
                img.load()
                reader.close()  # Windows cannot replace a file that is still open (overwrite case)
                for op in ops:
                    if cancelled():
                        raise Cancelled()
                    progress("rotate", None)
                    rotated = img.transpose(op)
                    img.close()  # free the previous full frame before the next step
                    img = rotated
                if cancelled():
                    raise Cancelled()
                progress("write", None)
                save_image(dst, img, source_path=src)
            except MemoryError as exc:
                raise OSError("Not enough memory to process this image.") from exc
            finally:
                img.close()
    finally:
        reader.close()
