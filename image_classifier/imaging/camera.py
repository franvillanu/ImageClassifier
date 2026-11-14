"""Classifier camera in oriented source pixels, independent of decode resolution.

Qt scroll bars quantise the rendered centre. The viewer records user pan deltas;
frame replacements reuse this immutable record without accumulating that rounding.
"""
from dataclasses import dataclass, replace
from enum import Enum


class ViewMode(Enum):
    FIT = "fit"
    MANUAL = "manual"


@dataclass(frozen=True)
class Camera:
    mode: ViewMode = ViewMode.FIT
    scale: float = 1.0
    centre: tuple[float, float] = (0.0, 0.0)

    def fit(self, width, height, viewport_width, viewport_height):
        scale = min(max(1, viewport_width - 4) / width,
                    max(1, viewport_height - 4) / height)
        return Camera(ViewMode.FIT, scale, (width / 2, height / 2))

    def zoom(self, factor):
        return replace(self, mode=ViewMode.MANUAL,
                       scale=max(0.1, min(3.0, self.scale * factor)))

    def rotate_clockwise(self, height):
        x, y = self.centre
        return replace(self, centre=(height - y, x))
