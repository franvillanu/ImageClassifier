# SPEC-003 — Classifier photo view (zoom and position)

Status: active · Code: `app.py` (`setup_shortcuts`, `backspace_toggle_fit`), `ui/image_viewer.py` (`adjustToFit`)
Tests: `tests/test_spec_classifier_view.py`

## Requirements

| ID | Requirement | Why |
|---|---|---|
| CV-1 | In the classifier, Backspace or 0 brings the photo back to its initial view: fitted to the window, centred, zoom reset. Help lists both keys (EN/ES). | User request: 0 snaps back in the slideshow (SPEC-002 SV-4) and should do the same in the classifier; Backspace already did it. |
| CV-2 | In the classifier `+` / `−` (main keyboard or numpad, with or without Ctrl; `=` counts as `+`) zoom in / out like ↑ / ↓, and Ctrl+0 fits like 0 and Backspace. ↑ / ↓ keep working. Help lists the keys (EN/ES). | Same keys as the slideshow (SPEC-002 SZ-6) and the editor. |

## Decision log

- 2026-11-09 — Spec started with the first classifier view rule. Earlier zoom/pan behaviour (wheel, keyboard zoom, pan) is not specified yet; write it here before changing it.
