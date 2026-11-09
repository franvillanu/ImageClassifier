# SPEC-002 — Slideshow floating controls

Status: active · Code: `slideshow/player.py` (`reveal_controls`, `_hide_controls`, `_update_fullscreen_control`, `eventFilter`)
Tests: `tests/test_spec_slideshow_controls.py`

## Problem (observed)

In the slideshow, any interaction with the floating control bar caused complete repaints of the window.

## Requirements

| ID | Requirement | Why |
|---|---|---|
| SC-1 | Mouse movement while the controls are already visible does no widget work: no show, raise, icon or visibility change, so no control or window repaint. It only restarts the auto-hide timer. | `eventFilter` calls `reveal_controls()` on every `MouseMove`. Each call raised the bar and re-set the fullscreen icon, repainting the player window and every control on every mouse move, over a GL surface that recomposes the whole window. |
| SC-2 | The first movement after the controls were hidden shows them once (bar, close button in fullscreen, cursor) and starts the auto-hide timer. | The reveal itself is the one legitimate change. |
| SC-3 | The fullscreen/restore icon and the close button are only touched when the window mode actually changes. | `setIcon` and `raise_` repaint even when nothing changed. |
| SC-4 | After auto-hide, the next movement reveals again (SC-2 path is not skipped by the fast path of SC-1). | Guards the optimisation against leaving the controls stuck hidden. |

## Evidence (2026-11-09, real GL window, fullscreen, 2560×1440 @150%)

With playback paused and the bar visible, each `mouse-move` produced `PlayerWindow:Paint` 1,
`SlideSurface:Paint` 1, `QFrame:Paint` 2, `QPushButton:Paint` 5–6, `QLabel:Paint` 1: the whole control
cluster plus the window background. Isolating the operations inside `reveal_controls()`:
`controls.raise_()` and `_update_fullscreen_control()` each triggered the full cluster repaint
(`_update_fullscreen_control()` twice over); `_position_controls()`, `_set_idle_cursor()`,
`close.raise_()` and `hide_timer.start()` alone triggered none.
Diagnosis state: **direct causal evidence** (operation-level isolation). Windowed mode behaves the same;
fullscreen makes each repaint more visible. While playing, the GL canvas already repaints at ~60 fps, so
these extra repaints are pure overhead on top of it.

### Full control sweep (after the fix, real GL fullscreen window, widget paints / GL paints per action)

| Action | Widget paints | GL paints | Notes |
|---|---|---|---|
| Mouse move, bar visible (was 12) | 0 | 0 | SC-1 |
| Hover a bar button (was 12) | 5 | 0 | button highlight over a translucent bar needs its parents repainted |
| Previous / Next / Play / Pause click | 12 | 1 (30 while playing) | one repaint of the bar for the state change |
| Space (pause or resume) | 25 | 32 | two bar repaints: reveal plus play/pause icon and tooltip; **open item** |
| Up / Down (speed toast) | 13 | 1 | toast only |
| Fullscreen button / F11, either way | 19-22 | 1 | 2-3 resizes, 2 `Expose`; **open item**, same family as SPEC-001 FS-1/FS-2 |
| Settings dialog open | 67 (dialog's own first paint) | 1 | one `Expose`, player not repainted beyond that |
| Dialog: slider, switch, mode tile | 3-5 | 0 | confined to the dialog, nothing in the player repaints |
| Dialog Apply with window-mode change | 13 | 2 | 3 resizes, 4 `Expose`; **open item** |

## Decision log

- 2026-11-09 — Fast path in `reveal_controls()` instead of throttling mouse moves: with nothing to change,
  doing nothing is cheaper and has no timing side effects.

## Open items

- Space/pause repaints the bar twice; the mode change (button, F11, Apply) resizes 2-3 times. Specify and test before changing.
