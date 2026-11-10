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
| FS-8 | While fullscreen, the 1-pixel frame of FS-7 is painted in the window's background colour (viewer theme colour for the main window, black for the slideshow), on paint and on every activation change, so fullscreen looks edge to edge. | Windows paints that frame in its classic grey (`#646464`, measured on all four edges), which made fullscreen look like a maximized window on top of everything. The Windows 11 border colour attribute has no effect on this frame (measured). |
| FS-9 | Leaving fullscreen for maximized (X button, F11, Esc) never shows a smaller window on the way: every intermediate size is at least the work area minus the window frame, and afterwards un-maximizing still returns to the user's own normal size. | Qt passes through the window's normal placement when going from fullscreen to maximized (measured: fullscreen, then 1024x768 at (100, 100), then maximized), so the app shrank and grew back. While still maximized the normal placement is set to the work area (invisible) and restored once the window is maximized again. |
| OV-1 | The Settings overlay appears complete in one step: panel positioned before the overlay is shown, and no `processEvents()` during opening. | Showing the dim layer first, pumping events, then showing the panel produced two recompositions of the GL window. |
| OV-2 | Overlays and tooltips are child widgets of the main window, never top-level windows. | A top-level window deactivates the main window, which exits fullscreen (`WindowDeactivate` handler) and recomposes the desktop. |
| OV-3 | Closing the Settings overlay removes it and re-enables the floating menu and shortcuts. | Prevents a dead UI after a modal closes. |
| OV-4 | (revised 2026-11-10) The Options panel is a drawer: it fills the full height of the window, is flush against the window's right edge, and is `PANEL_WIDTH` (scaled) wide, never wider than the window. It is not draggable. | User choice of mockup I (side drawer): the old centred 360 px card was hard to read and scrolled. Replaces "vertically centred beside the settings button" (2026-11-09), which the user asked for before the redesign. |
| OV-5 | The drawer starts with a search field. Typing filters the settings case-insensitively by row label or section title; sections with no match are hidden, a "no results" line shows when nothing matches, and clearing the field shows everything again. | User choice: "Side drawer with search". The list is long; finding a setting should not need scrolling. |
| OV-6 | Each section is a title with a thin line after it, followed by its rows directly: no cards, no dividers between rows, no row icons. | User request: "only the title line for each section, that's all". |
| OV-7 | Readability: row labels are at least 16 px, section titles at least 14 px and brighter than the old grey, the switch and controls at least 44 px tall. | User report: the old panel (15 px labels, 12 px grey titles) was hardly readable. |
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

### FS-8 verification (2026-11-09)

Edge pixels of an isolated GL window in fullscreen: default `#646464` on all edges; with `DwmSetWindowAttribute(DWMWA_BORDER_COLOR)` none or black, still `#646464`; with the frame painted on `WM_NCPAINT` / `WM_NCACTIVATE`, `#000000` on all edges and the corner, also after losing and regaining focus, style still bordered (`0x96880000`). Maximized windows are untouched.

### FS-9 verification (2026-11-09)

Real app, X button from fullscreen, every native resize logged. Before: `2545x1403` -> **`1024x768` at (100, 100)** -> `2560x1369`. After: `2545x1403` -> `2545x1355` -> `2560x1369`, no intermediate size smaller than the work area; un-maximizing afterwards gives `1024x768` at (100, 100) again. First attempt restored the normal size right after `showMaximized()` and failed (un-maximize gave the work area): Qt reports the maximized state about 90 ms later, so the restore now runs from `changeEvent`.

## Decision log

- 2026-11-10 — Options panel redesigned as a right-edge drawer with search (OV-4..OV-7). Eight mockups were compared on a design canvas (readable column, two-pane, tabs, card grid, drawer, command palette, light, tiles); the user chose the drawer and then asked for just a title + line per section. Always the right edge (the floating menu is on the left by default and the drawer must not cover it); not verified against a menu undocked to the right. Not verified in the real app: the offscreen tests prove geometry, filtering and text sizes, not how it looks.

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
