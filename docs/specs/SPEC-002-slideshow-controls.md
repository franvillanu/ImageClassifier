# SPEC-002 — Slideshow floating controls

Status: active · Code: `slideshow/settings_dialog.py`, `slideshow/player.py` (`reveal_controls`, `_hide_controls`, `_update_fullscreen_control`, `eventFilter`, `rotate_current`), `slideshow/surface.py`
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

| SR-1 | Pressing R during the slideshow rotates the photo on screen 90° clockwise (to the right); each press adds 90° (0, 90, 180, 270, back to 0). Playback state and the photo's progress are unchanged. | User request: fix sideways photos while watching without stopping the show. |
| SR-2 | The rotation is temporary: it belongs to that photo for the current slideshow only (it comes back rotated if the photo is shown again in the same run) and is never written to the file, to the classifier's per-photo rotation or to the config. A new slideshow starts unrotated. | "Temporarily": watching must never modify the user's photos. |
| SR-3 | A rotated photo is fitted with its rotated proportions (a landscape photo turned 90° is fitted as portrait), and the rotation survives the switch from preview to full-resolution frame. | Otherwise the pan/zoom would fit the unrotated size and crop or letterbox wrongly, or the rotation would be lost when the sharper frame arrives. |
| SR-4 | R appears in the slideshow settings shortcut sheet and in the Help shortcut list, in English and Spanish. | A shortcut nobody can discover does not exist for the user. |
| SV-1 | A slideshow setting "New zoom and pan when going back to a photo" (off by default, saved with the other slideshow settings, older configs load with it off) controls revisits. | User request: see the same photo with different zooms and panning when going back and forth. Off by default keeps the existing behaviour. |
| SV-2 | With the setting on, going back or forward to a photo already shown in this slideshow plays it with a different motion effect than last time; the photo itself, its rotation (SR-2) and the order are unchanged. | A revisit that repeats the same effect would not show anything new. |
| SV-3 | With the setting off, a revisited photo replays the motion it had (previous behaviour). | No change for users who do not opt in. |
| SX-1 | Closing the slideshow (Esc, the close button, the window's close) on a photo other than the one it started on selects and shows that photo in the classifier. | User request: exit on photo X lands on X, not on the photo the slideshow was launched from. Replaces the earlier rule "Escape returns to the unchanged classifier selection". |
| SX-2 | Closing on the same photo it started on, or before any photo was shown, leaves the classifier exactly as it was (selection, zoom, pan). | Nothing to move to; reloading would throw away the user's zoom. |
| SP-1 | During the slideshow Ctrl+←/→/↑/↓ pans the photo on screen by a tenth of the window per press (repeating while held), like scrolling: Ctrl+→ shows more of the right side (the photo moves left), Ctrl+↓ more of the bottom. Playback and the motion effect keep running on top of the pan. | User request: look around a photo while it plays. |
| SP-2 | The pan never moves the photo more than half its displayed size away from where the motion puts it, so at least half of it stays on screen. | Unlimited panning would push the photo off screen and leave a black window. |
| SP-3 | The pan is temporary: it resets when the next photo (or the same photo again) is presented, survives the full-resolution frame and R rotation, and is never saved. | Each slide starts framed by its motion; a pan is a momentary look. |
| SP-4 | Ctrl+arrows appear in the slideshow settings shortcut sheet and in the Help list, in English and Spanish. | Discoverability, as SR-4. |
| SX-3 | When the slideshow closes on photo X, the classifier already shows X at the moment the slideshow window disappears: the slideshow hands over the frame it is showing (unrotated), which the classifier displays at once; the full resolution follows as usual. No frame of the previous photo is shown. | User report: on exit the old photo was visible first and then changed to X. The switch happened after the window closed and X still had to be decoded. |
| SD-1 | In the slideshow settings dialog the keyboard shortcut sheet is collapsed by default behind a single "Keyboard shortcuts" row with a chevron, so the dialog is shorter. | User request: the dialog was too tall. |
| SD-2 | Expanding or collapsing animates the sheet's height (about 180 ms, ease-out) and the dialog's height follows it; the chevron turns with it. Collapsing ends hidden, expanding ends at the sheet's natural height. | Smooth, minimal: no jump in size. |
| SD-3 | The toggle works from the keyboard (focusable, Space toggles) and has an accessible name. | Same reach as the rest of the dialog. |

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

- 2026-11-09 — Exit lands on the photo being watched (SX-1). The previous verification note "Escape back to the unchanged classifier selection" is superseded by user request; the classifier state is still untouched when the slideshow ends on its starting photo (SX-2).

- 2026-11-09 — Fast path in `reveal_controls()` instead of throttling mouse moves: with nothing to change,
  doing nothing is cheaper and has no timing side effects.

## Open items

- Space/pause repaints the bar twice; the mode change (button, F11, Apply) resizes 2-3 times. Specify and test before changing.
