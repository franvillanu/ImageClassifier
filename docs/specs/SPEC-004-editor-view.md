# SPEC-004 — Editor view (compare with the original, zoom and pan)

Status: active, started · Code: `editor/editor_window.py` (`_set_compare`), `editor/adjust_canvas.py`,
`editor/geometry.py` (`oriented_to_source`, `output_to_source`)
Tests: `tests/test_spec_editor_view.py`

## Requirements

| ID | Requirement | Why |
|---|---|---|
| ED-1 | While the compare button (or `\`) is held, the original is drawn at the same screen scale as the edit, and the source point shown at the centre of the edit's view stays at that same screen point. This holds on the Ajuste tab when zoomed and panned, with a crop, a straighten angle or a 90° turn / flip (the original is shown unturned), and on the Crop tab. Released, the edit comes back where it was. | User report (2026-11-10): comparing a zoomed, panned photo showed the original re-centred, so a different part of the photo appeared and the comparison was useless. Cause: the compare paint forced the view centre to (0.5, 0.5). |
| ED-2 | Clicking or dragging on the Ajuste canvas keeps its background colour and the space kept free for the floating controls. | Stray lines in `mouseReleaseEvent` reset the background to black and the insets to zero on every mouse release, so the photo jumped after the first pan and the background colour was lost. |

## Evidence

- 2026-11-10 — `AdjustCanvas.paintEvent` used `center = (0.5, 0.5)` whenever a compare image was set, ignoring
  `_center`; `set_compare` only received the zoom. Screenshots from the user: edit zoomed on the lower half,
  compare showed the top (title) half at the same scale.
- 2026-11-10 — `AdjustCanvas.mouseReleaseEvent` contained a pasted copy of `__init__`/`set_insets` lines that
  set `_bg` to black and `_insets` to `(0, 0, 0, 0)`.
- 2026-11-10 — Proof of the fix: with only the old centring (and the old release reset) put back, the three
  compare tests and the ED-2 test fail; with the fix, all 8 tests in `test_spec_editor_view.py` pass.
- Real-app check: not run by the agent (GUI); the user verifies by relaunching from the branch.

## Decision log

- 2026-11-10 — Spec started. The anchor for compare is the view centre (not the cursor): it is defined on both
  tabs and does not depend on where the button is. With a straighten angle the original is drawn upright, so
  only the centre point lines up, not the whole frame.
