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
first, full resolution attached after a 250 ms dwell without re-render when at fit. Neighbours (next 2 in
travel direction, previous 1) are preloaded and cancelled when out of the window. Held arrow keys are
throttled by `_nav_step_allowed()`. Caches: bounded in-memory LRU plus optional disk preview cache.

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
