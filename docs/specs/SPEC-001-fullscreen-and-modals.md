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
| FS-5 | Fullscreen is left by click-away only when the application loses focus to another application. Opening our own dialog, the slideshow (settings dialog and player), the editor or a message never leaves fullscreen, and fullscreen is still on when they close. | The click-away rule fired on any `WindowDeactivate`, so pressing F5 in fullscreen dropped the main window out of fullscreen before the player even opened (measured: `main fs=False max=True` right after launch). |
| FS-6 | (retired 2026-11-09) Child cover showing the last frame during the change. | Falsified by user testing: the black wall stayed. The cause was not an empty framebuffer but Windows switching the window into direct fullscreen presentation (FS-7). |
| FS-7 | Every fullscreen window that renders with OpenGL (main viewer, slideshow player) carries a 1-pixel `WS_BORDER` while fullscreen, applied before its first frame at fullscreen size, so Windows keeps compositing it instead of switching it to direct fullscreen presentation. | A borderless popup covering the whole monitor with an OpenGL surface is switched by Windows/DWM into direct (independent flip / exclusive-like) presentation. Each switch in or out blacks the screen and redraws everything: the "black wall" on entering fullscreen, and one flash each time another window (slideshow settings dialog, player) appears over or replaces it. Measured style while fullscreen: `0x96080000` (`WS_POPUP`, no `WS_BORDER`). Qt handles it with its `HasBorderInFullScreen` flag; PyQt6 has no setter, but Qt's Windows plugin reads the window property `_q_has_border_in_fullscreen` when the native window is created, so `ui/fullscreen_border.py` sets it and recreates the native window before the first show. Setting `WS_BORDER` by hand was tried and rejected: Qt then reported the window as not fullscreen. |
| OV-1 | The Settings overlay appears complete in one step: panel positioned before the overlay is shown, and no `processEvents()` during opening. | Showing the dim layer first, pumping events, then showing the panel produced two recompositions of the GL window. |
| OV-2 | Overlays and tooltips are child widgets of the main window, never top-level windows. | A top-level window deactivates the main window, which exits fullscreen (`WindowDeactivate` handler) and recomposes the desktop. |
| OV-3 | Closing the Settings overlay removes it and re-enables the floating menu and shortcuts. | Prevents a dead UI after a modal closes. |
| EP-1 | A transient message ("Loop on", "Compare added", ...) costs at most two window repaints: one when it appears, one when it disappears. No frame-by-frame fade or position animation. | Every message faded in and out over 500 ms each plus 300 ms position animations, and each animation frame recomposited the whole GL window: 11-17 repaint waves per toggle, at 27 call sites. |
| EP-2 | The message widget is only as large as its text, is a child of the main window and lets mouse events through. | It was a window-sized translucent overlay with an opacity effect, rendered to a pixmap every frame. |
| EP-3 | Several simultaneous messages are stacked centred without overlapping, newest on top, repositioned instantly when one goes away. | Preserves the old stacking behaviour without animation. |
| EP-4 | After its duration a message is removed and deleted, and the stack list holds no stale entries. | Prevents leaked widgets and ghost gaps in the stack. |

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

### Fullscreen interaction sweep (2026-11-09, real GL fullscreen window, 900 ms window per action, before EP fix)

Repaint waves per action: arrows/Home/End 0-3; Up/Down zoom 0; favorite 1; option toggles L, N, D, Z, Ctrl+Z, Ctrl+C and compare (C, Shift+C) **11-17**; arrow buttons 11-17; M 1 (plus 1 nested `processEvents`); Filter overlay 1 (2 nested `processEvents`); Export 3 (1); Help 3; Settings 1; About 1; Delete dialog 4. Opening the slideshow settings, the folder dialog or the editor from fullscreen leaves fullscreen (click-away rule) with 3-6 resizes and 3-4 `Expose`. Cause of the 11-17: the message popup (EP-1).

### 2026-11-09 correction after user testing

Removing the cover window (FS-1) made maximized to fullscreen flash black, and pressing F5 in fullscreen lost fullscreen. Both were visible in my own sweep (`fs-kept: LOST` rows for the slideshow settings and folder dialogs) and I filed them as open items instead of fixing them. FS-5 and FS-6 close them. Pixel-level confirmation of FS-6 was not possible here: the screen sampler runs at about 10 Hz, too slow to see a 1-3 frame flash, so FS-6 rests on the mechanism and on user verification.

### Sweep after EP-1, FS-5, FS-6 (same method, window forced to foreground)

All 49 actions keep fullscreen except the explicit F11/fullscreen button. Option toggles (L, N, D, Z, C, Ctrl+Z, Ctrl+C) and arrow buttons: 1-2 repaint waves (were 11-17). Remaining highest: Export 3, Help 3, Shift+C 3, Filter 2 (+2 nested `processEvents`), slideshow settings dialog 3 resizes (the dialog's own window). F5 from fullscreen: main stays fullscreen through settings dialog, player and the player's own settings (was `fs=False` right after launch).

### FS-7 verification (real app, 2026-11-09)

Isolated GL window: without the flag fullscreen style `0x96080000` (no border); with it `0x96880000` (border), `isFullScreen()` true, GL renders, stable over repeated toggles. Full app flow, window in the foreground: main fullscreen bordered; F5 opens the player fullscreen and bordered while the main window stays fullscreen; Space and the pause button pause and resume; player settings pause on open and resume on cancel, fullscreen kept; Esc closes the player, main still fullscreen. What these numbers cannot show is the monitor itself: screen grabs read the composed image, so the absence of the black wall still needs the user's eyes.

## Decision log

- 2026-11-09 — Removed the cover window instead of tuning it: fewer windows beats masking. Kept the
  `make_cover` parameter, ignored, so existing callers keep working.
- 2026-11-09 — Overlays stay child widgets (OV-2). The slideshow-style top-level `QDialog` is a possible
  later step if child overlays still flicker; it needs a guard so `WindowDeactivate` does not exit
  fullscreen (like the slideshow's `_editing_settings`).

- 2026-11-09 — Messages no longer fade: with a GL window every animation frame is a full recomposition, so the fade cost more than the message. Appear and disappear instantly.

## Open items (specify and test before changing)

- FS-7 rests on Qt's documented Windows behaviour and the measured window style; the presentation-mode switch itself cannot be captured with screen grabs (they read the composed image). Needs the user's eyes.

- Help, About, Filter, Brightness overlays still use staged show or `processEvents()` (architecture debt §9).
- Tooltip creation per hover (new widget + fade) could be a single reused widget.
