"""Monotonic playback, reproducible selection, history and loading coordination."""
from dataclasses import dataclass, replace
import random
import time
from PyQt6.QtCore import QObject, pyqtSignal
from .motion import EFFECTS


@dataclass(frozen=True)
class SlideEntry:
    path: str
    effect_id: str
    cycle: int = 0


class SlideshowController(QObject):
    stateChanged = pyqtSignal(str)
    presented = pyqtSignal(object, object)
    frameUpdated = pyqtSignal(object)
    error = pyqtSignal(str)
    skipped = pyqtSignal(str)
    updated = pyqtSignal()

    def __init__(self, playlist, starting_image, settings, loader, *, clock=time.monotonic, rng=None, parent=None):
        super().__init__(parent)
        self.playlist = tuple(dict.fromkeys(str(p) for p in playlist))
        self.starting_image = str(starting_image)
        self.settings = settings
        self.active_settings = settings
        self.loader = loader
        self.clock = clock
        self.rng = rng or random.Random()
        self.history = []
        self.index = -1
        self.entry = None
        self.state = "stopped"
        self.playing = False
        self._elapsed = 0.0
        self._origin = None
        self._cycle = []
        self._cycle_id = -1
        self._furthest = -1
        self._failed = set()
        self._token = 0
        self._waiting = False
        self._closed = False
        loader.ready.connect(self._ready)
        loader.failed.connect(self._load_failed)

    @property
    def elapsed(self):
        return self._elapsed + (self.clock()-self._origin if self._origin is not None else 0)

    @property
    def progress(self):
        return min(1.0, self.elapsed/self.active_settings.duration)

    def _state(self, state):
        self.state = state
        self.stateChanged.emit(state)
        self.updated.emit()

    def _new_cycle(self, first=False):
        candidates = [p for p in self.playlist if p not in self._failed]
        if not candidates:
            return []
        if self.settings.shuffle:
            self.rng.shuffle(candidates)
            if first and self.starting_image in candidates:
                candidates.remove(self.starting_image)
                candidates.insert(0, self.starting_image)
            elif self.history and len(candidates)>1 and candidates[0]==self.history[-1].path:
                candidates[0], candidates[1] = candidates[1], candidates[0]
        elif first and self.starting_image in candidates:
            candidates = candidates[candidates.index(self.starting_image):]
        return candidates

    def _extend(self, count):
        while len(self.history) <= self.index+count:
            if not self._cycle:
                if self.history and not self.settings.repeat:
                    break
                self._cycle = self._new_cycle(first=not self.history)
                if not self._cycle:
                    break
                self._cycle_id += 1
            path = self._cycle.pop(0)
            if path not in self._failed:
                self.history.append(SlideEntry(path, self.rng.choice(tuple(EFFECTS)), self._cycle_id))

    def set_duration(self, duration):
        """Change seconds per photo live, keeping the current photo's pan/zoom position."""
        duration = float(max(3, min(600, duration)))
        old = self.active_settings.duration
        if duration == old:
            return duration
        scaled = self.elapsed * duration / old
        self._elapsed = scaled
        if self._origin is not None:
            self._origin = self.clock()
        self.settings = replace(self.settings, duration=duration)
        self.active_settings = replace(self.active_settings, duration=duration)
        self.updated.emit()
        return duration

    def set_settings(self, settings):
        """Keep visited history; reschedule unvisited entries for new preferences."""
        old = self.settings
        self.settings = settings
        if self._furthest < 0 or (old.shuffle == settings.shuffle and old.repeat == settings.repeat):
            return
        self.history = self.history[:self._furthest+1]
        self._cycle_id = self.history[-1].cycle
        visited = {e.path for e in self.history if e.cycle == self._cycle_id}
        self._cycle = [p for p in self.playlist if p not in visited and p not in self._failed]
        if settings.shuffle:
            self.rng.shuffle(self._cycle)
        if not self._waiting:
            self.loader.cancel_pending()
            self._preload()

    def start(self):
        if self._closed or self.index >= 0:
            return
        self.playing = True
        self._extend(1)
        if not self.history:
            self.playing = False
            self._state("stopped")
            self.error.emit("empty")
            return
        self._navigate(0)

    def pause(self):
        if self._closed or self.state == "stopped":
            return
        self._elapsed = self.elapsed
        self._origin = None
        self.playing = False
        self._state("paused")

    def resume(self):
        if self._closed or self.state == "stopped" or self.playing:
            return
        self.playing = True
        if not self._waiting:
            self._origin = self.clock()
        self._state("loading" if self._waiting else "playing")

    def _navigate(self, index):
        self.loader.cancel_pending()
        self._token += 1
        if index <= self._furthest and getattr(self.settings, "new_motion_on_revisit", False):
            self._new_motion(index)  # SPEC-002 SV-2
        self.index = index
        self._furthest = max(self._furthest, index)
        self.entry = self.history[index]
        self.active_settings = self.settings
        self._elapsed = 0
        self._origin = None
        self._waiting = True
        self._state("loading" if self.playing else "paused")
        self.loader.request(self.entry.path, self._token)

    def _new_motion(self, index):
        """Revisit with a different motion effect; same photo, same place in the order (SV-2)."""
        entry = self.history[index]
        choices = tuple(e for e in EFFECTS if e != entry.effect_id) or tuple(EFFECTS)
        self.history[index] = replace(entry, effect_id=self.rng.choice(choices))

    def next(self):
        if self._closed or self.index < 0:
            return
        self._extend(1)
        index = self.index+1
        while index < len(self.history) and self.history[index].path in self._failed:
            index += 1
        if index < len(self.history):
            self._navigate(index)
        else:
            self._elapsed = self.active_settings.duration
            self._origin = None
            self.playing = False
            self._state("paused")

    def previous(self):
        if not self._closed and self.index >= 0:
            index = max(0, self.index-1)
            while index > 0 and self.history[index].path in self._failed:
                index -= 1
            self._navigate(index)

    def _ready(self, token, frame):
        if self._closed or token != self._token:
            return
        if not self._waiting:
            self.frameUpdated.emit(frame)
            return
        self._waiting = False
        self._elapsed = 0
        self._origin = self.clock() if self.playing else None
        self.presented.emit(self.entry, frame)
        self._state("playing" if self.playing else "paused")
        self._preload()

    def _preload(self):
        self._extend(2)
        for offset in (1,2):
            if self.index+offset < len(self.history):
                entry = self.history[self.index+offset]
                self.loader.request(entry.path, -self._token*3-offset, current=False)

    def refresh_image(self):
        """Upgrade a resized viewport without changing the slide's clock/effect."""
        if not self._closed and self.entry is not None and not self._waiting:
            self.loader.request(self.entry.path, self._token)

    def _load_failed(self, token, path):
        if self._closed or token != self._token:
            return
        self._failed.add(path)
        self.skipped.emit(path)
        if len(self._failed) >= len(self.playlist):
            self.stop()
            self.error.emit("all_failed")
            return
        self._cycle = [p for p in self._cycle if p not in self._failed]
        # Scheduling may already contain failed paths from preloads/history.
        # Extend until a remaining candidate is found, or finish at the last
        # drawable slide without leaving a failed request in 'loading'.
        while True:
            self._extend(1)
            index = self.index+1
            if index >= len(self.history):
                self._waiting = False
                self._elapsed = self.active_settings.duration
                self._origin = None
                self.playing = False
                self._state("paused")
                return
            if self.history[index].path not in self._failed:
                self._navigate(index)
                return
            self.index = index

    def tick(self):
        if self.playing and not self._waiting:
            if self.progress >= 1:
                self.next()
            self.updated.emit()

    def stop(self):
        self._elapsed = self.elapsed
        self._origin = None
        self.playing = False
        self._waiting = False
        self._token += 1
        self.loader.cancel_pending()
        self._state("stopped")

    def close(self):
        self.stop()
        self._closed = True
        self.loader.close()
