"""Deterministic motion authored from measured WPF output, in logical pixels.

See docs/slideshow/effects.md for the observation protocol and reference limits.
No WPF code or resources are loaded by this module.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MotionFrame:
    scale: float
    x: float
    y: float
    opacity: float
    bounds: tuple[float, float, float, float]


def interpolate(points, time):
    for (a, va), (b, vb) in zip(points, points[1:]):
        if time <= b:
            return va + (vb - va) * max(0, (time - a) / (b - a))
    return points[-1][1]


@dataclass(frozen=True)
class MotionEffect:
    identifier: str
    name: str
    start: tuple[float, float, float]
    end: tuple[float, float, float]
    number: int

    @property
    def maximum_zoom(self):
        return max(self.start[0], self.end[0])

    def evaluate(self, progress, image_size, viewport_size, strength=100):
        p = max(0.0, min(1.0, progress))
        t = p * 25
        values = tuple(a + (b-a)*p for a, b in zip(self.start, self.end))
        if self.number == 1:
            values = (interpolate(((0, 1), (22, 1.1), (25, 1.2)), t),
                      interpolate(((0, 0), (22, -7.2), (25, 0)), t),
                      interpolate(((0, 0), (22, 7.6), (25, 0)), t))
        elif self.number == 10:
            values = (values[0], interpolate(((0, 0), (8.75, 55), (22, 0), (25, 0)), t),
                      interpolate(((0, 0), (8.75, -40.143), (22, 0), (25, 0)), t))
        blend = max(0, min(100, strength)) / 100
        scale, x, y = 1 + (values[0]-1)*blend, values[1]*blend, values[2]*blend
        fade_in = 3 if self.number <= 10 else 2
        opacity = min(1.0, t/fade_in, (25-t)/3)
        iw, ih = image_size
        vw, vh = viewport_size
        fit = min(vw/max(1, iw), vh/max(1, ih))
        w, h = iw*fit*scale, ih*fit*scale
        return MotionFrame(scale, x, y, opacity, ((vw-w)/2+x, (vh-h)/2+y, w, h))


# Observed endpoints, not generated directions: small offsets and duplicate
# motions are intentional. Translation remains in DIPs when the viewport changes.
_OBSERVATIONS = (
    ("Gentle zoom with return", (1,0,0), (1.2,0,0)),
    ("Gentle zoom right up", (1,0,0), (1.1,9.8,-1.4)),
    ("Gentle zoom left down A", (1,0,0), (1.1,-7.2,7.6)),
    ("Gentle zoom left down B", (1,0,0), (1.1,-7.2,7.6)),
    ("Gentle zoom left down C", (1,0,0), (1.1,-7.2,7.6)),
    ("Zoom left up", (1,0,0), (1.3,-36,-23)),
    ("Sweep right", (1,-720,0), (1,699,-1)),
    ("Sweep right down", (1,-636,-394), (1,629,388)),
    ("Sweep down", (1,1,-461), (1,-1,462)),
    ("Gentle retreat with excursion", (1.1,0,0), (1,0,0)),
    ("Centered retreat", (1.5,0,0), (1,0,0)),
    ("Retreat from upper left", (2,-53,-39), (1.2,0,0)),
    ("Retreat from upper right", (2,55,-51), (1.2,0,0)),
    ("Retreat from lower right", (2,51,47), (1.2,0,0)),
    ("Retreat from lower left", (2,-44,38), (1.2,0,0)),
    ("Sweep up", (1,1,243), (1,2,-322)),
    ("Sweep left", (1,617,0), (1,-611,1)),
    ("Sweep left up", (1,435,274), (1,-467,-242)),
    ("Sweep right up", (1,-488,257), (1,469,-257)),
    ("Centered approach", (1,0,0), (1.5,-1,2)),
    ("Deep centered retreat", (2,0,0), (1,0,0)),
    ("Magnified pan left", (1.5,377,0), (1.5,-377,0)),
    ("Deep pan left up", (2,377,300), (2,-377,-300)),
    ("Magnified pan down", (1.5,0,-300), (1.5,0,300)),
    ("Deep pan right up", (2,-377,300), (2,377,-300)),
    ("Retreat down", (2,0,-300), (1,0,300)),
    ("Retreat right", (2,-377,0), (1,377,0)),
    ("Retreat left down", (2,377,-300), (1,-377,300)),
    ("Approach right", (1,0,0), (1.5,377,0)),
    ("Approach down", (1,0,0), (1.5,0,300)),
)
EFFECTS = {f"v2-{i:02}": MotionEffect(f"v2-{i:02}", name, start, end, i)
           for i, (name, start, end) in enumerate(_OBSERVATIONS, 1)}
