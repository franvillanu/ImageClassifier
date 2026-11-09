# SPEC-001 — Fullscreen transitions and modal surfaces

Status: active · Code: `app.py` (`toggle_fullscreen`, `open_settings_overlay`), `ui/dialogs.py`, `ui/widgets.py`
Tests: `tests/test_spec_fullscreen_modals.py`

## Problem (observed)

In fullscreen, interacting with menus and options repainted the window several times per action, visible
as flicker; entering and leaving fullscreen flashed. It is more noticeable now that the slideshow is used.

## Requirements

| ID | Requirement | Why |
|---|---|---|
| FS-1 | Changing fullscreen state creates no helper top-level window (no screenshot cover). | The cover was an always-on-top window; hiding it exposed the main window and forced another full repaint. |
| FS-2 | Leaving fullscreen returns to the state it was entered from: maximized stays maximized; a normal window gets its exact previous geometry. A single state change, not `showNormal()` followed by `setGeometry()`. | The old code restored "normal" then resized to the maximized rectangle: two resizes ~500 ms apart and a window that was no longer maximized. |
| FS-3 | The exit button is visible only in fullscreen; `exit_fullscreen()` (Esc, button, click-away) leaves fullscreen and hides it. | Keeps the exit affordance consistent with the state. |
| FS-4 | The repaint freeze used during the state change is always lifted, even if a step raises. | A leaked `setUpdatesEnabled(False)` leaves a frozen window. |
| OV-1 | The Settings overlay appears complete in one step: panel positioned before the overlay is shown, and no `processEvents()` during opening. | Showing the dim layer first, pumping events, then showing the panel produced two recompositions of the GL window. |
| OV-2 | Overlays and tooltips are child widgets of the main window, never top-level windows. | A top-level window deactivates the main window, which exits fullscreen (`WindowDeactivate` handler) and recomposes the desktop. |
| OV-3 | Closing the Settings overlay removes it and re-enables the floating menu and shortcuts. | Prevents a dead UI after a modal closes. |

## Evidence (2026-11-09, 2560×1440 @150%, real-window event-count probes)

Repaint waves per action (before → after):

| Action | Before | After |
|---|---|---|
| Open Settings (windowed and fullscreen) | 2 | 1 |
| Enter fullscreen | 5 (3 `PhotoViewer` paints, 4 `Expose`, 1 window re-show) | 3 |
| Leave fullscreen | 7 (4 `Expose`, 4 resizes, ~500 ms gap between resizes) | 2 |

- One full-window repaint costs ~16 ms windowed and fullscreen: fullscreen is not slower per paint, it only
  makes each extra repaint more visible. Menu actions produced identical Qt repaint counts in both modes.
- Screen sampling caught fully black frames during the old enter and exit transitions.
- Diagnosis state: **direct causal evidence** for the transition flashes and the staged Settings open;
  **working hypothesis** for the remaining Help overlay cost (3 waves) and the cost of translucent
  children over the GL viewport. Not yet confirmed by the user on the real display.
- Regression check: run against the pre-fix `app.py`, the spec tests hung (cover window plus nested
  event processing), i.e. they detect the old behaviour.

## Decision log

- 2026-11-09 — Removed the cover window instead of tuning it: fewer windows beats masking. Kept the
  `make_cover` parameter, ignored, so existing callers keep working.
- 2026-11-09 — Overlays stay child widgets (OV-2). The slideshow-style top-level `QDialog` is a possible
  later step if child overlays still flicker; it needs a guard so `WindowDeactivate` does not exit
  fullscreen (like the slideshow's `_editing_settings`).

## Open items (specify and test before changing)

- Help, About, Filter, Brightness overlays still use staged show or `processEvents()` (architecture debt §9).
- Tooltip creation per hover (new widget + fade) could be a single reused widget.
