"""Validated, backwards-compatible slideshow preferences."""
from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class SlideshowSettings:
    duration: float = 10
    strength: float = 100
    shuffle: bool = False
    repeat: bool = True
    fullscreen: bool = True
    maximized: bool = False

    def __post_init__(self):
        for key, lo, hi, default in (("duration", 3, 600, 10), ("strength", 0, 100, 100)):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
                object.__setattr__(self, key, default)
        for key, default in (("shuffle", False), ("repeat", True), ("fullscreen", True)):
            if not isinstance(getattr(self, key), bool):
                object.__setattr__(self, key, default)
        if not isinstance(self.maximized, bool) or self.fullscreen:
            object.__setattr__(self, "maximized", False)

    @classmethod
    def from_dict(cls, values):
        values = values if isinstance(values, dict) else {}
        return cls(**{k: values[k] for k in cls.__dataclass_fields__ if k in values})

    def to_dict(self):
        return asdict(self)
