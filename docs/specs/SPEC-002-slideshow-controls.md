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
| SP-1 | During the slideshow Ctrl+←/→/↑/↓ pans the photo smoothly, like scrolling (Ctrl+→ shows more of the right side, so the photo moves left; Ctrl+↓ more of the bottom): a tap glides it by 5% of the window, holding moves it continuously at about half the window per second, and it eases to a stop on release (also when Ctrl is released first). Movement is updated every frame, never in jumps; key auto-repeat is ignored. Playback and the motion effect keep running. | User request: look around a photo while it plays; first version moved in 10% jumps per key repeat, which the user found jerky. |
| SP-2 | The pan never moves the photo more than half its displayed size away from where the motion puts it, so at least half of it stays on screen. | Unlimited panning would push the photo off screen and leave a black window. |
| SP-3 | The pan is temporary: it resets when the next photo (or the same photo again) is presented, survives the full-resolution frame and R rotation, and is never saved. | Each slide starts framed by its motion; a pan is a momentary look. |
| SP-4 | Ctrl+arrows appear in the slideshow settings shortcut sheet and in the Help list, in English and Spanish. | Discoverability, as SR-4. |
| SP-5 | Shift+←/→/↑/↓ pans exactly like Ctrl+arrows (same speed, glide, limit, reset and release rules), and the shortcut sheet and Help show both modifiers. | User request: Shift as an alternative to Ctrl. |
| SZ-1 | During the slideshow the mouse wheel zooms the photo in and out smoothly (Ctrl+wheel does the same): one notch changes the zoom by ×1.25, trackpads proportionally, eased over several frames, between 1× (the normal framing) and 5×. Playback and the motion effect keep running. | User request. Plain wheel like the classifier and common photo viewers; the wheel has no other job in the slideshow and an accidental zoom is temporary (SZ-3). Ctrl+wheel accepted because users try it. |
| SZ-2 | Zooming keeps the point under the mouse pointer under the pointer (within the pan limit). | Zooming into what you are looking at, not into the middle of the screen. |
| SZ-3 | The zoom is temporary: it resets to 1× when the next photo (or the same photo again) is presented, survives R rotation and the full-resolution frame, and is never saved. | Same lifetime as the pan (SP-3). |
| SZ-4 | Zoom and Ctrl/Shift+arrow panning combine; the pan limit grows with the zoom (half the zoomed size), so a zoomed photo can be explored edge to edge. | At 5× the old half-window limit would hide most of the photo. |
| SZ-5 | The mouse wheel zoom appears in the slideshow shortcut sheet and in Help, in English and Spanish. | Discoverability, as SR-4/SP-4. |
| SM-1 | Pressing the left mouse button on the photo and dragging moves it 1:1 with the pointer (closed-hand cursor while dragging), within the pan limit (SZ-4); it combines with wheel zoom and Ctrl/Shift+arrows. Playback continues. | User request: move freely with the mouse. |
| SM-2 | A click without movement changes nothing, double-click still toggles fullscreen, and dragging only starts on the photo (the control bar's buttons work as before). | The mouse already has meanings in the slideshow; none may break. |
| SM-3 | Moving the photo by dragging follows the same lifetime as the other view changes: reset on the next photo, never saved (SP-3). | Consistency with the keys and the wheel. |
| SM-4 | Dragging appears in the slideshow shortcut sheet and in Help, in English and Spanish. | Discoverability. |
| SV-4 | Backspace (or 0) brings the photo back to its normal framing: zoom 1× and no pan, gliding there over a few frames, without pausing; it also ends a drag or a held pan key. It is listed in the shortcut sheet and Help (EN/ES). | User request: a way back to the initial zoom. Backspace already means "fit" in the classifier; 0 is the common reset-zoom key in viewers. |
| SZ-6 | `+` / `−` (main keyboard or numpad, with or without Ctrl; `=` counts as `+`) zoom in / out by ×1.25 per press toward the centre of the screen, smoothly, within 1×–5×; holding repeats. Ctrl+0 resets like 0 and Backspace (SV-4). Ctrl+arrows and Shift+arrows both keep panning. Listed in the shortcut sheet and Help (EN/ES). | User request for keyboard zoom. Standard: Ctrl+`+`/`−` and Ctrl+0 (browsers, Windows Photos, Office, the app's own editor); plain `+`/`−` in photo viewers. Arrows stay for moving. |
| SX-3 | When the slideshow closes on photo X, the classifier already shows X at the moment the slideshow window disappears: the slideshow hands over the frame it is showing (unrotated), which the classifier displays and *renders* before the slideshow window hides; the full resolution follows as usual. No frame of the previous photo is shown. | User report: on exit the old photo was visible first and then changed to X. The switch happened after the window closed and X still had to be decoded. |
| SD-1 | In the slideshow settings dialog the keyboard shortcuts are hidden by default behind a single "Keyboard shortcuts" row with a chevron, so the dialog opens at its compact size. | User request: the dialog was too tall. |
| SD-2 | (revised 2026-11-09) Opening the row reveals a side panel to the right of the settings; closing hides it. The width animates (about 180 ms, ease-out) and the dialog's width follows it; the settings column keeps its width and the dialog's height does not change; the chevron turns half a turn (points left while open). Closing ends with the panel hidden and the dialog at its compact size, opening ends at the panel's natural width. | User request: the in-dialog accordion "was not working" (cause not diagnosed) and made the dialog taller; a panel beside the settings keeps both visible. Replaces the accordion that grew the dialog downwards. |
| SD-5 | The side panel lists every shortcut in one column, grouped under two headings (Viewer: pause, previous/next, speed, full screen, close, show controls; Photo: rotate, zoom, move, normal view), each row with the action on the left and its keycaps on the right, in English and Spanish. The headings carry the same colour dots as the Help categories and the keycaps are dark with padding. | User choice of alternative A (side panel). One column reads faster than the old three-column sheet. |
| SD-6 | The panel opens to the right of the settings, which stay where they are; if that would leave the screen, the dialog is shifted left only as far as needed to stay fully on screen, and returns to its original position when the panel closes. | A window that grows off-screen hides the panel the user just asked for. |
| SD-7 | The panel has its own close button (accessible name "Close panel" / "Cerrar panel") that does the same as the row, and Esc still closes the dialog, not only the panel. | A panel that can only be closed from the row it covers feels trapped; Esc keeps its existing meaning. |
| SD-3 | The toggle works from the keyboard (focusable, Space toggles) and has an accessible name. | Same reach as the rest of the dialog. |
| SD-4 | The settings dialog opened during playback has no "Changes apply to the next slide" note. | User request: the note was unnecessary and added height. |
| SE-1 | A slide's fade in and out applies only while the slideshow is playing. Whenever it is not playing (paused, or finished), the photo on screen is drawn fully visible. A slide that is not playing and sits at its very start or very end (just navigated to, or the show finished) is drawn at its neutral framing, fitted and centred; one paused part-way keeps its motion position. | User report: with Repeat off the show ended on a black screen that stayed black even going backwards. Every motion has opacity 0 at progress 0 and 1, so a slide frozen at either end was invisible; and sweep motions also start and end with the photo (almost) off screen, so full opacity alone still left a black screen (found by a test that failed for some random effects). |
| SE-2 | With Repeat off, when the last photo's time runs out the show stops on that photo, visible at its final position, and Previous / ← shows the earlier photo (visible, paused). | Same report: the end of the show must leave the last photo to look at, and going back must work. |
| SE-3 | While playing, the fade in and out is unchanged (opacity 0 at the very start of a slide). | The fix must not remove the transition between photos. |

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

### SX-3 correction (2026-11-09)

User saw the old photo for ~500 ms after closing. Real-app timeline: frame handed over and cache hit at 11 ms, classifier switched at 12 ms, slideshow hid at 22 ms, but the classifier's GL view first painted at 48 ms: Windows showed the window's last presented frame (the old photo) until then. Fix: the classifier repaints synchronously before the slideshow hides. After: paint at 30 ms, hide at 84 ms. The test now requires a paint of the new photo before the hide, not just loading it.

### Wheel zoom performance (2026-11-09, real GL fullscreen 2560x1440 @150%, 6000x4000 photos)

Frame intervals while playing: 1x median 16.7 ms / p95 16.8 / max 20.5; while zooming 16.7 / 16.8 / 17.7; held at 5x 16.7 / 16.8 / 17.1. No measurable cost: the zoom only changes the rectangle the motion already draws.

### Black screen at the end of the show (2026-11-10)

User report: Repeat off, the slideshow ends on black and stays black, also after going back. Measured `MotionEffect.evaluate(...).opacity` at progress 0 / 0.05 / 0.5 / 0.95 / 1: 0.0 / 0.42 / 1.0 / 0.42 / 0.0. Code path: `controller.next()` at the end sets `_elapsed = duration` (progress 1) and `playing = False`; `previous()` → `_navigate()` restarts the slide at progress 0 paused. `paint_slide` always applied the motion's opacity, so both frozen states drew an invisible photo.
Diagnosis state: **direct causal evidence** for the mechanism (measured opacity, code path); the report itself was not reproduced in the GUI. The new test shows the old code paints black.

## Decision log

- 2026-11-10 — First version of SE-1 only removed the fade; the SE-2 test then failed for about 1 run in 4 (random effect: for the sweep motions the photo is off screen at progress 0 and 1, e.g. `v2-07` ends 699 px right). Neutral framing at the two ends fixed that; the test now forces a sweep effect so it fails every time without the rule.
- 2026-11-10 — Fade only while playing (SE-1). Alternatives: hold the last frame only at the end (leaves paused-then-Previous black), or start paused slides at a mid-motion progress (changes the clock, the pan and the history tests). Cost accepted: pausing during a fade makes the photo jump to full brightness.

- 2026-11-09 — Exit lands on the photo being watched (SX-1). The previous verification note "Escape back to the unchanged classifier selection" is superseded by user request; the classifier state is still untouched when the slideshow ends on its starting photo (SX-2).

- 2026-11-09 — Fast path in `reveal_controls()` instead of throttling mouse moves: with nothing to change,
  doing nothing is cheaper and has no timing side effects.

- 2026-11-09 — Shortcuts moved from an accordion to a side panel (SD-2, SD-5..SD-7). Three alternatives were mocked (side panel, popover on the button, inner view with back arrow); the user chose the side panel. Not verified in the real app yet: the offscreen test screen is 800x600, so the on-screen clamp (SD-6) is proven there but the look and the animation feel need the user's eyes.

## Open items

- Space/pause repaints the bar twice; the mode change (button, F11, Apply) resizes 2-3 times. Specify and test before changing.
