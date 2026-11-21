"""Rotate and align without cropping (SPEC-008): the edit state whose frame holds the whole rotated photo.

Qt-free. The frame is the bounding box of the photo rotated by ``angle``; it is an ordinary editor
``EditState`` (orientation + one ``CropGeometry``), so ``imaging.huge.edit_file`` renders it like any edit.
"""
from __future__ import annotations

import math

from image_classifier.editor.state import CropGeometry, EditState, Orientation, oriented_size


def canvas_size(source_size: tuple[int, int], rot90: int, angle: float) -> tuple[int, int]:
    """RA-3: W|cos a| + H|sin a| by W|sin a| + H|cos a|, after ``rot90`` quarter turns."""
    width, height = oriented_size(source_size, Orientation(rot90=rot90))
    a = math.radians(angle)
    c, s = abs(math.cos(a)), abs(math.sin(a))
    return max(1, round(width * c + height * s)), max(1, round(width * s + height * c))


def align_state(source_size: tuple[int, int], rot90: int, angle: float) -> EditState:
    """RA-4: ``rot90`` quarter turns clockwise, then ``angle`` degrees clockwise, nothing cropped."""
    base = EditState(source_size=source_size, orientation=Orientation(rot90=rot90))
    width, height = base.oriented_size
    out_w, out_h = canvas_size(source_size, rot90, angle)
    return base.with_crop(CropGeometry(width / 2.0, height / 2.0, float(out_w), float(out_h), float(angle)))
