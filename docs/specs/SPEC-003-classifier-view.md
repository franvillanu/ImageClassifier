# SPEC-003 — Classifier photo view (zoom and position)

Status: active · Code: `app.py` (`setup_shortcuts`, `backspace_toggle_fit`), `ui/image_viewer.py` (`adjustToFit`)
Tests: `tests/test_spec_classifier_view.py`

## Requirements

| ID | Requirement | Why |
|---|---|---|
| CV-1 | In the classifier, Backspace or 0 brings the photo back to its initial view: fitted to the window, centred, zoom reset. Help lists both keys (EN/ES). | User request: 0 snaps back in the slideshow (SPEC-002 SV-4) and should do the same in the classifier; Backspace already did it. |
| CV-2 | In the classifier `+` / `−` (main keyboard or numpad, with or without Ctrl; `=` counts as `+`) zoom in / out like ↑ / ↓, and Ctrl+0 fits like 0 and Backspace. ↑ / ↓ keep working. Help lists the keys (EN/ES). | Same keys as the slideshow (SPEC-002 SZ-6) and the editor. |
| CV-3 | In the classifier Ctrl+↑ / Ctrl+↓ zoom in / out like ↑ / ↓ (before, they scrolled the photo up / down). Shift+←/→/↑/↓ and Ctrl+←/→ keep moving the photo, and PageUp / PageDown keep scrolling it. Help shows Ctrl+⬆/⬇ with the zoom keys and no longer as a move alternative (EN/ES). | User decision: the same keys in the classifier and the slideshow (SPEC-002 SZ-7, SP-5): Ctrl+↑/↓ = zoom, Shift+arrows = move, one-handed. Measured before the change: Ctrl+↓ and Shift+↓ both scrolled the zoomed photo down, Ctrl+→ / Shift+→ right. |
| CV-4 | With reset zoom on next image disabled, repeated navigation between equal-sized photos preserves the zoom scale and position, regardless of cached previews or full-resolution frames. With reset enabled, each photo still fits the window. | Comparing detail must not progressively shrink the photos as previews are replaced by full-resolution images. |

## Decision log
- 2026-11-14 — Zoomed navigation uses the full-resolution cache or decodes the full source directly, retaining the previous photo until ready. Fit navigation keeps its preview-first path. This keeps comparison coordinates in source pixels instead of repeatedly applying the preview/full scale conversion.

- 2026-11-10 — Ctrl+↑/↓ changed from scrolling to zooming (CV-3) to match the slideshow. Vertical moving stays on Shift+↑/↓ and PageUp/PageDown.

- 2026-11-09 — Spec started with the first classifier view rule. Earlier zoom/pan behaviour (wheel, keyboard zoom, pan) is not specified yet; write it here before changing it.

## Evidence
- 2026-11-14 — CV-4 regression reproduced offscreen with 3200×2000 sources and 1024-pixel previews: one navigation reduced scale from 2.182188 to 0.698300 (×0.32). The regression covers six alternating visits with and without full frames cached, checks scale and centre, and verifies reset-to-fit still works. Real-app visual behaviour has not been verified.

### CV-4 root cause and prevention
- `setImage()` preferred a cached preview even when a full frame was cached. `onImageLoaded(reset_zoom=False)` retained the preceding full-frame transform but replaced its source with preview pixels, without converting the transform to preview coordinates.
- `_attach_full_resolution()` then applied its normal `preview.width / full.width` correction. That correction preserves a view established on a preview, but the inherited transform was already expressed in full-source pixels. Consequently every visit multiplied the inherited zoom by the reduction ratio again. Cache availability and decode completion determined when the shrink appeared.
- The missing contract was the coordinate system of a carried transform across navigation; previous tests did not cover alternating preview/full loads while preserving zoom. CV-4 now asserts the observable invariant over repeated visits, for cache hits and asynchronous full-frame completion, including the view centre. Zoomed navigation bypasses preview coordinates entirely; normal fit navigation retains progressive loading.
- Validation: classifier/traceability tests pass (25 tests), including both keyboard and wheel zoom flags. Both cache variants failed on the original navigation method with the same ×0.32 scale loss. Full-suite runs: 426 passed, one SX-2 slideshow-exit failure (scale 1.7 becomes 4.45). Replacing the navigation method with its original HEAD implementation and excluding CV-4 reproduces that same failure (424 passed, one failed); SX-2 passes alone. The full suite is therefore not green, and that existing suite-dependent issue remains unresolved.
