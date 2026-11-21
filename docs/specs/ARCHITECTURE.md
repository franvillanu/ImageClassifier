# Architecture (as built)

Verified against the code on 2026-11-09 (v2.0.16). `ARCHITECTURE_REVIEW.md` at the repo root is an older
review (Feb 2025, single-file era); this document supersedes it for structure.

## 1. Shape

Windows desktop app, Python 3.13 + PyQt6 (Qt 6.10). Entry: `run.py` → `image_classifier.run()` →
`app.main()` → `PhotoViewer` (a `QMainWindow`).

| Package | Responsibility | Qt? |
|---|---|---|
| `app.py` (~4.3k lines) | `PhotoViewer`: all app state (files, index, favorites, compare, filters, config), shortcuts, overlays, fullscreen, orchestration | yes |
| `ui/` | Viewer widget (`image_viewer`, `viewport`), floating menu, overlays/tooltips/dialogs, settings/help/whats-new panels, scaling | yes |
| `imaging/` | `loader` (progressive decode + caches), `saver` (metadata-preserving), `sharpen` | loader yes |
| `editor/` | Non-destructive photo editor: immutable `EditState`, pure geometry/adjust/render, latest-wins preview worker | core Qt-free |
| `slideshow/` | Separate player window, deterministic motion engine, controller, GL/raster surface | yes |
| `updates/` | Check / download / verify / install from the public releases repo | check/download Qt-free |
| `workers/` | Export, delete, sharpen, update background jobs | yes |
| `i18n/` | `translations["en"|"es"]`; keys must stay in parity | no |
| `config.py` | Config dir and defaults (`QStandardPaths.AppLocalDataLocation`) | minimal |

Layering rule: Qt-free modules (`config`, `updates/check|download`, `editor` core, `slideshow/motion|settings`)
must not import widgets. New logic goes there first because it is unit-testable.

## 2. Rendering model (explains most visual bugs)

```
PhotoViewer (QMainWindow, native top-level window)
 ├─ AdvancedGraphicsImageViewer (QGraphicsView)
 │    └─ viewport = NearestViewport (QOpenGLWidget, GL 3.3 core, sRGB, no MSAA)
 ├─ FloatingMenu, float_* buttons, filename label, update banner   (child widgets, translucent)
 └─ Overlays: Settings / Help / About / Filter / Brightness / Message / Progress / CustomTooltip
      (child widgets with translucent backgrounds, raised above the viewer)
```

Consequences (measured, see SPEC-001 Evidence):
- A window containing a `QOpenGLWidget` is composited through the GPU. Any change to any child above it
  (tooltip, overlay, menu) causes a whole-window recomposition. One recomposition costs ~16 ms windowed or
  fullscreen, so **the number of recompositions per interaction is what the user sees**.
- Anything that forces extra recompositions shows as flicker: staged show (dim first, panel later),
  nested `processEvents()`, helper top-level windows appearing/disappearing, a state change followed by a
  second geometry change, delayed "kick" updates.
- Overlays and tooltips are **children**, never top-level windows. A top-level window would deactivate the
  main window, and `PhotoViewer.event()` leaves fullscreen on `WindowDeactivate`.

## 3. Image pipeline

`show_image()` → `AdvancedGraphicsImageViewer.setImage()` → in-memory preview/full cache hit (instant) or
`ImageLoaderRunnable` (QThreadPool, priorities current > preload > full-resolution). Screen-sized preview
first, including manual zoom; full-resolution detail is displayed after a 250 ms dwell or explicit zoom.
At fit, attaching the full source does not re-render the displayed frame. Neighbours (next 2 in
travel direction, previous 1) are preloaded and cancelled when out of the window. Held arrow keys are
throttled by `_nav_step_allowed()`. Caches: bounded in-memory LRU plus optional disk preview cache.

Huge images (2026-11-21, SPEC-007): above 100 MP (`imaging/huge.is_huge`) the viewer never decodes the full
frame (≈ 3.6 GB per copy at 896 MP; Qt's 512 MB allocation limit and Pillow's bomb limit both refuse it).
`request_full_resolution()` asks for a **detail frame** instead (`workers/huge_worker.HugeDetailRunnable`, Pillow
reduced decode, long side 8192, cached like a preview) and `full_resolution_ready` stays false. Progress is the
fraction of the file's bytes read (`huge._ProgressReader`); the viewer emits `detailStatus` and the window shows a
status line. Rotating and saving runs on the file in `HugeRotateWorker` (read → transpose → atomic write), never
through the viewer. Pixel editors say "too large" via `PhotoViewer._full_resolution_gate()`. Any worker exception
now reaches the viewer as an error signal (HI-2).

Classifier camera contract (2026-11-14, SPEC-003 CV-4..CV-8):
- `imaging/camera.py` owns the immutable camera record: explicit FIT/MANUAL mode, scale and centre in
  EXIF-oriented source-pixel coordinates (quarter-turns rotate the scene and the viewed point together).
  Keyboard and wheel use one zoom transition. The Qt view transform is derived from this record;
  scroll-bar deltas update its centre without feeding rounding error back on frame replacements.
- `ImageFrame.source_size` and cached preview metadata carry the source dimensions through reduced
  decodes, memory caching, disk caching and slideshow handover. A pixmap-item transform maps decoded
  pixels into that source scene. Preview/full replacement never rescales the camera.
- `auto_fit`, `zoom_factor`, and `fit_zoom_factor` are compatibility properties, not independent state.
  Only explicit fit actions select FIT; delayed layout callbacks cannot override a manual camera.
- Edited/snapshotted pixels go through `replace_image()`, which invalidates pending load IDs, cancels
  queued work and renders once. `app.py` reads the source but cannot assign `original_pixmap` directly.
- Cached full sources remain available for saving/editing while navigation displays a preview. The
  existing dwell timer uploads full detail only when browsing settles; explicit zoom requests it now.

## 4. Window / mode management

- Main window starts maximized. `toggle_fullscreen()` is the only entry/exit (F11, button; Esc via
  `exit_fullscreen`). It remembers whether the window was maximized and restores that state.
- Click-away (`WindowDeactivate` in fullscreen) exits fullscreen.
- Slideshow: `PlayerWindow` is a modal `QDialog`, its own window; its settings dialog is also a top-level
  `QDialog`. It pauses on deactivation unless `_editing_settings` / `_fullscreen_change` guards are set.

## 5. Concurrency

UI thread owns all widgets. `QThreadPool` for decode; `QThread` workers for export/delete/sharpen/update.
Results return by signals; stale results are dropped by `load_id` / token checks. Avoid `processEvents()`
in UI code: it re-enters handlers and splits one visual change into several paints.

## 6. Persistence

`viewer_config.json` in `%LocalAppData%\Image Classifier` (unknown keys preserved), per-folder marked
images file. Tests must call `QStandardPaths.setTestModeEnabled(True)` or monkeypatch `get_config_file`.

## 7. Build and release

PyInstaller + Inno Setup, signed. `version.txt` is the single source of truth; the merge task bumps the
patch and requires a hand-written bilingual line in `docs/release_notes.txt`. See
`docs/guides/RELEASE-PROTOCOL.md`.

## 8. Testing layers

| Layer | Where | Notes |
|---|---|---|
| Pure logic | `tests/test_editor_*`, `test_imaging`, `test_config`, `test_update_*` | fast, no widgets |
| Qt offscreen | `tests/conftest.py` sets `QT_QPA_PLATFORM=offscreen`, `PYOPENGL_ERROR_CHECKING=0` | no GL compositor: cannot show flicker |
| Spec-linked | `tests/test_spec_*.py` + `test_spec_traceability.py` | one test per requirement ID |
| Real-app probes | scratch scripts (event counts, screen grabs) | evidence recorded in specs |

## 9. Known structural debt (do not worsen)

- `PhotoViewer` is a god object (state + UI + overlays). New overlays should be separate classes in `ui/`.
- Overlay creation code in `app.py` is duplicated per overlay (Settings, Help, About, Filter, Brightness).
- `QApplication.processEvents()` calls remain in several overlay builders (Filter, Brightness, Export).
