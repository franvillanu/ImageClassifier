"""Validated, backwards-compatible slideshow preferences."""
from dataclasses import asdict, dataclass
import math


@dataclass(frozen=True)
class SlideshowSettings:
    duration: float = 35
    strength: float = 100
    shuffle: bool = True
    repeat: bool = True
    fullscreen: bool = True

    def __post_init__(self):
        for key, lo, hi, default in (("duration", 3, 600, 35), ("strength", 0, 100, 100)):
            value = getattr(self, key)
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not lo <= value <= hi:
                object.__setattr__(self, key, default)
        for key in ("shuffle", "repeat", "fullscreen"):
            if not isinstance(getattr(self, key), bool):
                object.__setattr__(self, key, True)

    @classmethod
    def from_dict(cls, values):
        values = values if isinstance(values, dict) else {}
        return cls(**{k: values[k] for k in cls.__dataclass_fields__ if k in values})

    def to_dict(self):
        return asdict(self)
