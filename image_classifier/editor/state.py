"""Immutable edit state for the photo editor.

The editor never mutates pixels while you work; it only produces new
``EditState`` values. Rendering turns a state plus the source image into
pixels (see ``render.py``), so undo/redo is just a list of states.

Coordinate spaces
-----------------
S   source pixels (EXIF orientation already applied), size ``source_size``.
O   oriented space: S rotated ``rot90`` quarter turns clockwise, then mirrored
    horizontally if ``flip``. Size ``EditState.oriented_size``.
The crop lives in O: an axis-aligned frame on screen, which in O is a
rectangle of size ``w x h`` centered at ``(cx, cy)`` and rotated by
``-angle`` (``angle`` is the image's on-screen rotation, Qt convention:
positive = clockwise).
"""
from __future__ import annotations

from dataclasses import dataclass, field, fields, replace

ADJUST_MIN = -100
ADJUST_MAX = 100
ANGLE_LIMIT = 45.0


@dataclass(frozen=True)
class Orientation:
    """Canonical dihedral orientation: rotate ``rot90`` x 90 deg clockwise, then mirror if ``flip``."""

    rot90: int = 0
    flip: bool = False

    def __post_init__(self):
        object.__setattr__(self, "rot90", int(self.rot90) % 4)

    @property
    def is_identity(self) -> bool:
        return self.rot90 == 0 and not self.flip

    @property
    def swaps_axes(self) -> bool:
        return self.rot90 % 2 == 1


@dataclass(frozen=True)
class CropGeometry:
    """Crop rectangle in O space (float pixels). ``angle`` in degrees."""

    cx: float
    cy: float
    w: float
    h: float
    angle: float = 0.0


@dataclass(frozen=True)
class Adjustments:
    """Ajuste sliders, each an int in [-100, 100]; 0 means untouched."""

    brightness: int = 0
    exposure: int = 0
    contrast: int = 0
    highlights: int = 0
    shadows: int = 0
    vignette: int = 0
    saturation: int = 0
    warmth: int = 0
    tint: int = 0
    sharpness: int = 0

    def __post_init__(self):
        for f in fields(self):
            v = int(round(getattr(self, f.name)))
            object.__setattr__(self, f.name, max(ADJUST_MIN, min(ADJUST_MAX, v)))

    @property
    def is_identity(self) -> bool:
        return all(getattr(self, f.name) == 0 for f in fields(self))

    @classmethod
    def names(cls) -> tuple[str, ...]:
        return tuple(f.name for f in fields(cls))


def oriented_size(source_size: tuple[int, int], orientation: Orientation) -> tuple[int, int]:
    w, h = source_size
    return (h, w) if orientation.swaps_axes else (w, h)


def full_crop(size: tuple[int, int]) -> CropGeometry:
    w, h = size
    return CropGeometry(w / 2.0, h / 2.0, float(w), float(h), 0.0)


@dataclass(frozen=True)
class EditState:
    source_size: tuple[int, int]
    orientation: Orientation = field(default_factory=Orientation)
    crop: CropGeometry | None = None
    adjust: Adjustments = field(default_factory=Adjustments)
    aspect: float | None = None  # locked w/h ratio of the crop frame; None = free

    def __post_init__(self):
        w, h = self.source_size
        object.__setattr__(self, "source_size", (int(w), int(h)))
        if self.crop is None:
            object.__setattr__(self, "crop", full_crop(self.oriented_size))

    @classmethod
    def initial(cls, source_size: tuple[int, int], rot90: int = 0) -> "EditState":
        return cls(source_size=source_size, orientation=Orientation(rot90=rot90))

    @property
    def oriented_size(self) -> tuple[int, int]:
        return oriented_size(self.source_size, self.orientation)

    @property
    def output_size(self) -> tuple[int, int]:
        return max(1, int(round(self.crop.w))), max(1, int(round(self.crop.h)))

    @property
    def is_crop_identity(self) -> bool:
        w, h = self.oriented_size
        c = self.crop
        eps = 1e-6
        return (
            abs(c.angle) < eps
            and abs(c.cx - w / 2.0) < eps
            and abs(c.cy - h / 2.0) < eps
            and abs(c.w - w) < eps
            and abs(c.h - h) < eps
        )

    @property
    def is_geometry_identity(self) -> bool:
        return self.orientation.is_identity and self.is_crop_identity

    @property
    def is_identity(self) -> bool:
        return self.is_geometry_identity and self.adjust.is_identity

    def with_crop(self, crop: CropGeometry) -> "EditState":
        return replace(self, crop=crop)

    def with_adjust(self, **values) -> "EditState":
        return replace(self, adjust=replace(self.adjust, **values))
