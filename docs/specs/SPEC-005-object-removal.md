# SPEC-005 — Object removal (Eliminar tab in the photo editor)

Status: active, started · Code: `editor/removal.py` (fill), `editor/state.py` (`Removal`, `EditState.removals`),
`editor/render.py` (`render`, `clean_source`), `editor/adjust_canvas.py` (brush mode), `editor/editor_window.py` (tab)
Tests: `tests/test_spec_object_removal.py`

The user paints over something they want gone (a passer-by, a sign, a bin); the editor fills the painted area
from the rest of the photo. It is exemplar-based (Criminisi-style) inpainting with OpenCV and numpy: it copies
real texture and edges from elsewhere in the photo instead of blurring. It is not generative AI, so large
objects over complex scenes can show repeated patterns; the user can undo and repaint a smaller part.

## Requirements

| ID | Requirement | Why |
|---|---|---|
| RM-1 | `EditState` carries `removals`, a tuple of strokes (`Removal`: polyline of points in source pixels + brush radius in source pixels). A state with removals is not an identity (Guardar enables), `EditState.initial` and Restablecer have none, and each removal is one undo step. | The editor is non-destructive: edits are values in the history, pixels are rendered from the source. |
| RM-2 | Filling a stroke changes only pixels under the painted area (plus a few pixels of blending at its edge); everything further away is bit-identical. | A removal must not touch the rest of the photo. |
| RM-3 | The painted area is filled with content taken from elsewhere in the photo, not a blur: filling a stroke on a textured photo gives a result whose local detail (standard deviation of the high-pass) inside the area is at least 60 % of the surrounding photo's, and a stripe pattern crossing the area continues through it. | A plain OpenCV inpaint turned a person into a grey smear (measured on the user's photo, 2026-11-14). |
| RM-4 | The fill is the same at preview and at full resolution: rendering a proxy and the full source gives the same region filled (the fill plan is computed once per stroke in a working size independent of the image's resolution and reused at any scale). | What the user sees while editing is what is saved. |
| RM-5 | Removals live in source coordinates, so they stay on the same spot when the photo is then cropped, straightened, rotated or flipped, and a crop that excludes the area leaves the output untouched by it. | Edits must be freely combinable and reorderable by the user. |
| RM-6 | On the Eliminar tab, dragging on the photo paints; everything painted in one go (strokes that follow each other within a short pause, or until Enter) is ONE removal and one undo step, however many strokes it has and however they overlap; the brush size is set in the row and the cursor shows it; the mouse wheel still zooms and the middle or right button pans. Ctrl+Z while strokes are waiting discards them. | A brush is how people select an object; zoom and pan are needed to be precise. User (2026-11-14): painting stroke after stroke to cover a person made one slow fill per stroke; it must be one selection and one fill. |
| RM-7 | Eliminar is the third tab at the start of the bottom row, with its own icon; its row shows the brush size and the same Comparar / Deshacer / Rehacer / Restablecer / Guardar as the other tabs; the row still fits windows of 1280 px (SPEC-004 ED-7). | One toolbar for every mode. |
| RM-8 | Comparar shows the original without the removals, and the crop tab and Auto adjust see the photo with the removals applied. | Compare must show what changed; the other tools must work on the current photo. |

| RM-9 | The painted area is shown as one flat tint: where strokes overlap it is exactly as dark as where one stroke passes. | User (2026-11-14): overlapping translucent strokes got darker ("intensities"), so people kept painting to make it uniform. |
| RM-10 | From the moment strokes are handed over until the filled photo is shown, the painted area pulses and a card with a spinner and "Eliminando…" is drawn over the photo near it; nothing of this remains afterwards. | User (2026-11-14): the fill takes a while and the small message at the top went unnoticed, so it looked like nothing happened. |

## Evidence

- 2026-11-14 — Request: "can we add a removal? to get rid of a guy like that" (a man walking away on paved ground in
  front of a stone wall). Probe on that photo (549x700) with a mask over the whole figure:
  `cv2.inpaint` (Telea) = a grey/yellow smear with radial streaks; translation-and-blend fill found no valid
  offset (the figure is too big); Criminisi-style exemplar fill at 300 px working size (now 200) (9x9 patches, masked
  SSD in Lab via `cv2.matchTemplate`) removed the figure with believable pavement and wall. Cost ~13 ms per
  patch (350 patches, 4.6 s) at 300 px, dominated by the masked template search, so it runs on the render
  worker and small objects (cropped region, native resolution) are near-instant.
- 2026-11-14 — Through the real pipeline (`apply_removals`, three brush strokes covering the whole figure, 549x700):
  the figure disappears and the pavement continues convincingly; where the figure crossed the stone wall and the
  yellow bench the fill leaves visible blocky fragments of wall/bench. Cost: ~16 s for the three strokes in total
  (about 5 s each) at proxy size; the same plans then render a 3x larger copy in 0.7 s. Adding a preference for
  nearby source patches (`NEAR`) cut some of the far-away scenery but did not remove the blocks. Known limit:
  large objects across several different backgrounds need several smaller strokes (undo and repaint).
- 2026-11-14 — ED-7 with the third tab: the Ajuste row overflowed 1280 px by 25 px; fixed by letting the Auto button
  drop its label with the tabs. The crop row looked 195 px too wide at 1920 px because a stale layout hint was
  read after leaving the result tab; the layouts are now activated before measuring.
- 2026-11-14 — User: "it worked but it is super slow". Profile (cProfile, 3294x4200 photo, proxy 1647x2100, one big
  stroke): 6.6 s, of which 5.1 s (77 %) is `cv2.matchTemplate` (307 calls x 16 ms, the masked patch search over the
  whole working copy); applying the plan 0.49 s, Poisson blend 0.23 s. So the cost is the search, and it grows with
  the working size squared times the number of patches. Variants on the three-stroke figure (549x700 photo):
  300 px work / 3 channels 19.9 s; 300 px / lightness only 6.6 s; **200 px / 3 channels 2.7 s**; 300 px / lightness
  only / 13 px patches 4.0 s; 220 px / lightness only 1.95 s. The fills of all variants look alike (same blocky
  limit at the wall/bench), so `WORK` went from 300 to 200 and colour matching was kept.
- 2026-11-14 — User: the brush "has intensities" (overlapping translucent strokes got darker, so they kept painting
  to even it out), each stroke was its own slow fill, and the wait was not noticeable (the only sign was a small
  toast at the top). Cause in code: `_paint_brush` drew each stroke segment in translucent red on top of the
  last, and every mouse release created a `Removal`. Fix: one flat fill of the union of all strokes
  (`QPainterPath.united`), strokes collected until a 900 ms pause or Enter and handed over as one `Removal` with
  `extra` strokes (one fill, one undo step), and a pulsing area plus a card with a spinner until the picture
  arrives. Offscreen screenshot of four overlapping passes over the figure: uniform tint, card centred on the
  area (offscreen has no fonts, so the text shows as boxes there).
- Real-app check: not run by the agent (GUI); the user verifies by relaunching from the branch.

## Decision log

- 2026-11-14 — No AI model (LaMa/ONNX): it would add ~200 MB and a runtime to the installer. Exemplar fill needs only
  OpenCV and numpy, which are already shipped. If the quality is not enough for big objects, a model can replace
  `removal.fill_plan` without changing the state, history or UI.
- 2026-11-14 — The fill is stored as a *plan* (offset map at working size: for each hole pixel, where in the photo its
  pixel comes from), not as pixels, so the same removal renders sharply at full resolution by copying full-resolution
  source pixels, then Poisson-blends the seam.
