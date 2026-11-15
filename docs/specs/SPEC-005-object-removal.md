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
| RM-11 | Painting and moving the brush stay light: a mouse move repaints only a small area around the brush (its ring and the new piece of stroke), never the whole canvas; what was already painted is drawn once into a cached layer, so a repaint does not rebuild it (its cost does not grow with the number of strokes); the busy pulse repaints only the painted area and its card. | User (2026-11-14): "when the user paints or moves the mouse with the removal dot it lags". Every move called `update()` on the whole canvas and every repaint rebuilt the union of all strokes (3.9 of 6.2 ms with 12 strokes), and in the app every repaint recomposes the whole window (ARCHITECTURE.md section 2). |
| RM-12 | The fill comes from the neighbourhood of the painted area: every filled pixel is copied from a place within a bounded distance of itself (0.6 of the painted area's size, at least three patches), and neighbouring filled pixels mostly come from the same offset (coherent chunks, not scattered scraps). | User (2026-11-14, screenshots): "it brings results that are far from the drawn area" - pieces of bench and wall appeared on the pavement and hillside. Cause: patches in the middle of a hole have few known pixels to compare, so almost any place scores as well as any other and the search picked arbitrary far-away ones. |
| RM-13 | The patch search only looks inside the window where copying is allowed (RM-12), and gives exactly the same fill as searching the whole working region would: the offsets are identical, with a fraction of the pixels searched. | The masked template search is 77 % of the time (RM-4 evidence) and its cost grew with the whole region although RM-12 already excludes everything outside the window; the saving pays for a larger working size, i.e. a finer fill, at no extra time. |
| RM-14 | (retired 2026-11-15) Blending the nearby sources around the seams. | Tried and withdrawn: on the user's photo the vote softened the block seams but smeared the whole fill into a soft grid, and cost +65 % time on a 12 MP photo (see Evidence). Replaced by RM-15, which attacks the cause of the visible seams (tone steps between patches). |

| RM-15 | (retired 2026-11-15) Colour-matching every copied patch to the known pixels around it. | Tried and withdrawn: on the user's photo it changed nothing visible and the jump across the seams went from 3.50 to 4.11 grey levels (worse): the visible blocks are copied structure, not tone (the Poisson blend already levels the tone). |
| RM-16 | Applying a fill only works on the box of the painted area (plus a small margin), not on the whole region around it: the pixels processed are at most 40 % of that region's for a small stroke, and the result outside the painted area is unchanged. | Budget set by the user: better quality without being slower. The apply step took 2.9 of 5.4 s on a 12 MP photo, mostly on pixels that are not painted. |

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
- 2026-11-14 — User: "when the user paints or moves the mouse with the removal dot it lags". Measured offscreen
  (2100x1650 photo in a 1920x1080 canvas, 12 strokes / 912 points): a repaint cost 1.3 ms with nothing painted and
  6.2 ms with the selection, 3.9 ms of it rebuilding the union path of all strokes (`QPainterPath.united`) on
  every repaint, growing with the points painted. Worse, every mouse move (even a bare hover) called `update()`
  on the whole canvas: the RM-11 test records 1,260,000 px (the full 1400x900 canvas) per move on the old code
  and fails there. In the app each repaint also recomposes the whole window (ARCHITECTURE.md section 2), so the
  number and size of repaints is what is felt. Fix: the painted area is drawn once into a cached layer (a segment
  at a time while painting, redrawn only when the view changes), shown with one flat opacity, and moves update
  only the brush ring (old and new, as two small rects: a first version used the box around both, ~100,000 px
  after a jump) and the new piece of stroke; the pulse updates only the painted area and its card. After: a move
  repaints ~4,100 px (0.3 % of the canvas), independent of how much is painted, and no layer is rebuilt
  while painting. The real feel is still to be checked in the app.
- 2026-11-14 — User: the performance work "made the final result less ok" and "it brings results far from the drawn
  area". Checked on the 549x700 photo and on a 3294x4200 version (6x) with one removal over the whole figure. Two
  things were true: (1) far-away scraps (bench and wall pieces on the pavement and hillside), because the
  patch search could copy from anywhere in the working region and interior patches have few known pixels to
  tell candidates apart; (2) the working size is not the culprit: at 6x, 300 px gave a wall chunk on the pavement
  and 200 px a cleaner fill, so `WORK` stays 200. Fix, measured on the same photos: copy only from within
  `RADIUS` (0.6) hole-sizes of the patch, prefer the offset of the neighbours already filled (`COH_W`, so chunks
  continue instead of scattering), and compare the average colour of the surroundings (`CTX_W`). The weights
  were chosen from a five-variant sheet; more surroundings weight (150) was worse (tan bits on the pavement).
  Left: stepped edges on the bench (offsets are quantised at the working size and enlarged), and the bench
  where it meets the hillside.
- 2026-11-15 — "Improve what we have as much as possible without AI, without hurting performance, without a heavier
  installer or more dependencies." Budget measured first, old (last commit) against new, alternated, best of 3, same
  machine: 549x700 photo 1.21 s, 3294x4200 photo 3.15 s. Findings: (1) searching only the allowed window (RM-13)
  gives identical offsets and cuts the searched pixels by ~30 % on this big hole (much more on small ones);
  the saving is too small to afford a larger working size (300 px costs 4x: 17.5 against 3.8 Mpx searched, 400 px
  14x); (2) the first version of the seam vote (RM-14) made the 12 MP case 3.15 -> 5.3 s (+69 %): profile 2.9 s in
  the copy with votes, 1.1 s in `seamlessClone`, search only 0.66 s; almost the whole hole counts as "near a
  seam" because the coherent chunks are only a few patches wide. Side by side on the bench and wall the vote
  softens the seams but smears the fill into a grid, so it was withdrawn. (3) the apply step works on the whole
  region around the hole (hole + 0.9 of its size on every side, about 7x the hole's area) although only the hole
  changes: RM-16.
- 2026-11-15 — Result of the round, fair comparison old (last commit) vs new, alternated, best of 3: 549x700 photo
  1.24 -> 0.95 s, 3294x4200 photo 4.21 -> 3.26 s (-23 % in both), same fill. What made it faster is RM-13 (search only
  the allowed window) and RM-16 (apply only on the painted box). Two quality ideas were tried and **withdrawn** with
  numbers: seam voting (RM-14) and per-patch colour matching (RM-15). So the limit of the current fill is the
  structure it copies, not seams or tone; next candidates are listed in the decision log.
  A third cheap try, the weight of the structure term in the order patches are filled (0.001, 0.01, 0.05, 0.3
  on the same photo): all four fills look alike and 0.3 makes the wall's step worse, so nothing was changed.
- Real-app check: not run by the agent (GUI); the user verifies by relaunching from the branch.

## Decision log

- 2026-11-15 — Ideas not done, in the order I would try them: (1) a second pass that re-searches each patch once the
  hole is full (so interior patches are matched with their whole content, not the few known pixels they had when
  first placed); (2) refining the offsets at a finer working size only along the seams with the known photo;
  (3) a neural model (opt B in the chat), the only thing that can invent what is not in the photo.

- 2026-11-14 — No AI model (LaMa/ONNX): it would add ~200 MB and a runtime to the installer. Exemplar fill needs only
  OpenCV and numpy, which are already shipped. If the quality is not enough for big objects, a model can replace
  `removal.fill_plan` without changing the state, history or UI.
- 2026-11-14 — The fill is stored as a *plan* (offset map at working size: for each hole pixel, where in the photo its
  pixel comes from), not as pixels, so the same removal renders sharply at full resolution by copying full-resolution
  source pixels, then Poisson-blends the seam.
