# SPEC-008 — Rotate and align (advanced rotation)

Status: active, started · Code: `editor/align.py` (geometry), `editor/align_screen.py` (screen),
`app.py` (`rotate_action`, `open_align`, setting), reuses `imaging/huge.edit_file` and `ui/huge_job.py`
Tests: `tests/test_spec_rotate_and_align.py`

By default R and the rotate button turn the photo 90° (unchanged). With the setting **Advanced rotation** on, they open
a small screen to rotate by any angle and straighten, **without cropping**: the canvas grows to hold the whole photo and
the empty corners are black. It works for every photo size; on maps it is the way to straighten without the crop box.
(Cropping and straightening with trimmed corners stays in Edit; see SPEC-007 for huge images.)

## Requirements

| ID | Requirement | Why |
|---|---|---|
| RA-1 | Settings > Viewing has "Advanced rotation", off by default, saved in the config (`advanced_rotation`). With it off, R and the rotate button behave exactly as before. | User: by default the rotation is just the 90° angles; the advanced one is optional. |
| RA-2 | With it on, R and the rotate button open the rotate-and-align screen, except while "Rotate applies to all images" is on (that keeps the immediate 90° turn). | That option rotates the whole folder at once; a per-photo screen does not fit it. |
| RA-3 | The screen shows the whole photo rotated by the chosen angle on a black canvas that is as large as the result: width = W·\|cos a\| + H·\|sin a\|, height = W·\|sin a\| + H·\|cos a\|. It offers the straighten ruler (-45° to 45°, 0.1° steps), turn 90° left/right, auto-straighten, the size of the result, and Save (copy or replace) and Cancel (Esc). Cancel changes nothing. | User: rotate and align in one screen, like the crop screen but without cropping. |
| RA-4 | Save renders the result from the file, whatever its size: EXIF upright, 90° turns, the angle, in one resampling; nothing is cropped (the whole photo is inside the result), corners are black (transparent only when the file already has alpha). The output has exactly the canvas size of RA-3. A progress dialog shows a real percentage and can cancel; cancel or failure leaves the original untouched. | The same job as SPEC-007 HI-10, so a 900 MP map and a phone photo take one path. |
| RA-5 | Save is not offered when nothing changed (angle 0 and no 90° turns). | Avoid rewriting a photo for nothing. |
| RA-6 | The screen does not open while the photo has unsaved changes in the viewer (rotation by R is not one; sharpen/crop/brightness are): it says to save or undo them first. | The save works on the file, so it would silently drop them. |

## Evidence

- 2026-11-21: the file render of the expanded frame (reusing `huge.edit_file`) on a 640 x 400 image at 20, -12.5 and 44 degrees:
  output equals the formula size, both corner markers fully inside (red/blue pixel counts within 20% of the original
  1600), corner pixels < 12 (black), centre unchanged; quarter turns alone are bit-exact (`np.rot90`). `py -m pytest -q`: 516 passed.

## Decision log

- 2026-11-21: a separate small screen, not a mode of the crop canvas: the crop canvas is built around keeping its frame
  inside the photo (`fit_to_angle`, `clamp_center`), so letting it grow past the photo would change its core rules.
- 2026-11-21: user chose black corners (not transparent, not trimmed) and "setting makes R open the screen".
- Unverified offscreen: how the screen looks and feels.
