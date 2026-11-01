"""Undo/redo over immutable edit states."""
from __future__ import annotations

from image_classifier.editor.state import EditState


class EditHistory:
    """Linear history. ``push`` records a new current state and clears redo."""

    def __init__(self, initial: EditState, limit: int = 200):
        self._states = [initial]
        self._index = 0
        self._limit = limit

    @property
    def current(self) -> EditState:
        return self._states[self._index]

    @property
    def initial(self) -> EditState:
        return self._states[0]

    def push(self, state: EditState) -> bool:
        """Record ``state``; returns False (no-op) if it equals the current state."""
        if state == self.current:
            return False
        del self._states[self._index + 1:]
        self._states.append(state)
        if len(self._states) > self._limit:
            # Keep the original state so "reset" and dirty checks stay meaningful.
            del self._states[1]
        self._index = len(self._states) - 1
        return True

    @property
    def index(self) -> int:
        return self._index

    def state_at(self, index: int) -> EditState:
        return self._states[max(0, min(index, len(self._states) - 1))]

    def squash_since(self, index: int) -> None:
        """Collapse every step after ``index`` into one: the current state.

        Used when a tool session is confirmed ("Done"), so a single undo reverts
        the whole session. Redo states are dropped.
        """
        index = max(0, min(index, len(self._states) - 1))
        current = self.current
        del self._states[index + 1:]
        if current != self._states[index]:
            self._states.append(current)
        self._index = len(self._states) - 1

    def can_undo(self) -> bool:
        return self._index > 0

    def can_redo(self) -> bool:
        return self._index < len(self._states) - 1

    def undo(self) -> EditState:
        if self.can_undo():
            self._index -= 1
        return self.current

    def redo(self) -> EditState:
        if self.can_redo():
            self._index += 1
        return self.current

    @property
    def is_dirty(self) -> bool:
        """Changed since the editor opened (drives the discard prompt)."""
        return self.current != self.initial
