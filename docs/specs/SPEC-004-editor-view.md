# SPEC-004 — Editor view (compare with the original, zoom and pan)

Status: active, started · Code: `editor/editor_window.py` (`_set_compare`, `_build_tabs`, `_layout_overlays`), `editor/adjust_canvas.py`,
`editor/geometry.py` (`oriented_to_source`, `output_to_source`)
Tests: `tests/test_spec_editor_view.py`

## Requirements

| ID | Requirement | Why |
|---|---|---|
| ED-1 | While the compare button (or `\`) is held, the original is drawn at the same screen scale as the edit, and the source point shown at the centre of the edit's view stays at that same screen point. This holds on the Ajuste tab when zoomed and panned, with a crop, a straighten angle or a 90° turn / flip (the original is shown unturned), and on the Crop tab. Released, the edit comes back where it was. | User report (2026-11-10): comparing a zoomed, panned photo showed the original re-centred, so a different part of the photo appeared and the comparison was useless. Cause: the compare paint forced the view centre to (0.5, 0.5). |
| ED-2 | Clicking or dragging on the Ajuste canvas keeps its background colour and the space kept free for the floating controls. | Stray lines in `mouseReleaseEvent` reset the background to black and the insets to zero on every mouse release, so the photo jumped after the first pan and the background colour was lost. |
| ED-3 | The Recortar and Ajuste modes are labelled text tabs (icon + name) in the top-left corner; the active one carries the accent bar. There is no vertical icon rail on the left edge. | User (2026-11-10): the left rail and the top-right buttons were far from the toolbar and the photo, so the eye kept jumping between corners. Modes are chosen about once per photo, so a header-like spot is fine for them (layout "C" picked on the design canvas). |
| ED-4 | Deshacer, Rehacer, Restablecer and Comparar are in the bottom tool row on every tab (Recortar, Ajuste and the result after Listo); Deshacer/Rehacer start the row. | They are the most frequently used actions, so they sit next to the slider and the tools the hand is already on, not in the far-left rail. |
| ED-5 | On the Recortar tab Guardar is a plain (non-accent) button, so Listo is the only accent action on screen; on the other tabs Guardar is the accent button again. | With layout C, two identical blue buttons (Listo at the bottom, Guardar at the top) were on screen while cropping, and it was unclear which one finishes the crop. |
| ED-6 | Without the rail, the space kept free on the photo's left and right is the same and only the edge gap, so the photo is centred and can use the full width. | The rail's width was reserved on both sides, shrinking wide photos for no reason. |

## Evidence

- 2026-11-10 — `AdjustCanvas.paintEvent` used `center = (0.5, 0.5)` whenever a compare image was set, ignoring
  `_center`; `set_compare` only received the zoom. Screenshots from the user: edit zoomed on the lower half,
  compare showed the top (title) half at the same scale.
- 2026-11-10 — `AdjustCanvas.mouseReleaseEvent` contained a pasted copy of `__init__`/`set_insets` lines that
  set `_bg` to black and `_insets` to `(0, 0, 0, 0)`.
- 2026-11-10 — Proof of the fix: with only the old centring (and the old release reset) put back, the three
  compare tests and the ED-2 test fail; with the fix, all 8 tests in `test_spec_editor_view.py` pass.
- Real-app check: not run by the agent (GUI); the user verifies by relaunching from the branch.
- 2026-11-10 — ED-3..ED-6: the old layout put the modes and undo/redo/reset in a vertical rail at the far left
  (screenshot from the user) and reserved that rail's width (76 px) on both sides of the photo. Six layouts were
  mocked up on a Claude Design canvas; the user chose "C". Proof: the six new tests fail on the old layout
  (`rail` exists, history not in the bottom row, Guardar is Primary while cropping, insets 76/76) and pass
  with the change. Full suite: only `test_sx2_closing_on_the_starting_photo_leaves_the_classifier_untouched`
  fails, and it fails the same way on unmodified `main` in a full run (passes alone): unrelated.
- Real-app check of ED-3..ED-6: not run by the agent (GUI); the user verifies by relaunching from the branch.

## Decision log

- 2026-11-10 — Spec started. The anchor for compare is the view centre (not the cursor): it is defined on both
  tabs and does not depend on where the button is. With a straighten angle the original is drawn upright, so
  only the centre point lines up, not the whole frame.
- 2026-11-10 — Layout C over A (one dock): the mode tabs stay put while the bottom row changes with the mode,
  and Guardar stays where Windows users expect it. A's single primary slot was its advantage, so ED-5 takes it
  over: Guardar goes plain while cropping. Reset sits after Compare at the end of the row, not with undo/redo,
  so a destructive action is not next to the most-clicked buttons.
