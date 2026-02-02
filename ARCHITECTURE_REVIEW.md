# Image Classifier — Full Architecture Review

**Review date:** February 2025  
**Reviewer:** Architecture review (assisted)  
**Scope:** Application, build, installer, and technology choices

---

## 1. Executive Summary

Image Classifier is a **well-featured desktop photo culling and favorites app** built with Python and PyQt6. The installer and release process are thoughtful (Inno Setup, code signing, Defender handling, bilingual). The main pain points are **maintainability** (single ~8.4k-line file, duplicated classes, no tests, no dependency list) and **security** (hardcoded signing password). **Python + PyQt6 is a sound choice** for this kind of app; the recommendation is to **improve structure and tooling** rather than to swap the entire stack.

---

## 2. Application Overview

| Aspect | Details |
|--------|---------|
| **Main file** | `image-classifier.py` (~8,392 lines) |
| **UI** | PyQt6 (QMainWindow, QGraphicsView, custom OpenGL viewport) |
| **Image I/O** | Qt `QImageReader` + `QPixmap`; PIL and OpenCV for processing |
| **Platform** | Windows (Shell32 via ctypes, COM, Defender, certutil) |
| **Config** | JSON in `%LocalAppData%` + per-folder `Favorites.json` |

### 2.1 Feature Set (Strengths)

- **Favorites & compare:** Star favorites, “compare” set, filter by All / Favorites / Compare / Non-favorites.
- **Navigation:** Prev/next, loop, Home/End, keyboard shortcuts.
- **View:** Zoom/pan, fit-to-view, reset zoom on new image, fullscreen with clean exit.
- **Adjustments:** Brightness (GPU-backed), rotation (per-image and “rotate all”), sharpness (LAB unsharp via OpenCV), crop (with aspect ratios).
- **Export:** Bulk export of favorites to a folder; optional “delete non-favorites” (send2trash).
- **UX:** Themes (Black, Inkstone, Dark Grey), EN/ES, floating menu, tooltips, help dialog, drag-and-drop folder.
- **Persistence:** Last folder, last index, sort option/order, theme, language, favorites/compare per folder.

---

## 3. Technical Architecture

### 3.1 Tech Stack

| Layer | Technology | Notes |
|-------|-------------|--------|
| **Language** | Python 3 | No `requirements.txt` or `pyproject.toml` in repo |
| **GUI** | PyQt6 | Widgets, Graphics View, OpenGL widget |
| **Images** | Qt (QImageReader, QPixmap, QImage), PIL (Image, ImageQt, ImageFilter), OpenCV (cv2), NumPy | Decode via Qt; processing via PIL/OpenCV |
| **Rendering** | OpenGL 3.3 Core, 4× MSAA | Custom `NearestViewport` (QOpenGLWidget) for pixel-accurate zoom |
| **Concurrency** | QThreadPool + QRunnable (image load), QThread (sharpen) | Loader is cache-aware and cancelable |
| **Persistence** | JSON (config + Favorites.json per folder) | `QStandardPaths.AppLocalDataLocation` |
| **OS integration** | ctypes (Shell32), send2trash | “Open in Explorer”, recycle bin |

### 3.2 Image Pipeline

1. **Load:** Path → `ImageLoaderRunnable` (or cache hit). `QImageReader` with `setAutoTransform(True)` and 512 MiB allocation limit → `QImage` → `QPixmap` → stored in shared LRU cache (max 10,000 entries).
2. **Display:** `AdvancedGraphicsImageViewer` (QGraphicsView + custom OpenGL viewport) shows pixmap; rotation and brightness can be applied on GPU.
3. **Processing:** Sharpen via `sharpen_cv2()` (LAB unsharp); crop in `CropOverlayContent` (PIL/QPixmap); export = file copy.

### 3.3 Key Classes (Conceptual)

- **PhotoViewer** — Main window: state (index, filter, favorites, compare, config), UI setup, shortcuts, dialogs.
- **AdvancedGraphicsImageViewer** — Image display, zoom/pan, rotation/brightness, compare split-view.
- **ImageLoaderRunnable** — Thread-pool image load + shared LRU cache.
- **FloatingMenu** — Main toolbar (folder, export, rotate, filter, brightness, settings, etc.).
- **Overlays:** Settings, brightness, filter, crop, sharpness, help, progress (export/delete).
- **Workers:** ExportWorker, DeleteNonFavoritesWorker, SharpenThread.

---

## 4. Build & Installer

### 4.1 Build Flow

1. **build-and-sign.bat**  
   - PyInstaller: onefile, windowed, icon, version file → `installer\Image Classifier.exe`.  
   - Sign with signtool (PFX).  
   - **Issue:** PFX password is hardcoded in the script.

2. **Release.bat**  
   - Reads version from `version.txt` → runs build-and-sign → compiles Inno Setup → signs the installer.  
   - Same hardcoded PFX password.

3. **PyInstaller spec** (`build\Image Classifier.spec`)  
   - **Issue:** `version` and `icon` use absolute paths (e.g. `C:\Users\Fran\Documents\...`). Builds are not portable.

### 4.2 Installer (Inno Setup)

- **Image_Classifier.iss** — Modern wizard, EN/ES, x64 only.
- **Custom “Installation Options” page:**  
  - If third-party AV detected → warning to add exclusion manually.  
  - If Windows Defender enabled and path not excluded → checkbox to add exclusion via PowerShell.  
  - Optional desktop shortcut.
- **Post-install:** Optional install of self-signed cert (Trusted Root) so Windows trusts the app.
- **Uninstall:** Removes desktop shortcut, `%LocalAppData%\Image Classifier`, and Defender exclusion.

This is **above average** for a small desktop app: cert, Defender, cleanup, and i18n are well considered.

---

## 5. Strengths

1. **Feature completeness** — Favorites, compare, filters, brightness, crop, sharpen, export, themes, i18n, shortcuts.
2. **Image loading** — Async, cache, cancelation, and cache-first path to avoid redundant decode.
3. **Display** — OpenGL viewport with MSAA and controlled scaling (e.g. nearest-neighbor where intended).
4. **Installer** — Certificate, Defender exclusion, clean uninstall, bilingual.
5. **Config and persistence** — Single config file + per-folder favorites/compare; survives restarts.
6. **Error handling** — Global exception hook writing crash logs and showing a message.

---

## 6. Issues & Risks

### 6.1 Maintainability

| Issue | Severity | Description |
|-------|----------|-------------|
| Single ~8.4k-line file | High | Hard to navigate, review, and refactor; all logic in one module. |
| Duplicate class names | Medium | `WorkerSignals` (lines 1076, 2803), `OverlayProgressDialog` (2697, 3755), `DraggableContainer` (2917 + nested at 4583). Later definitions shadow earlier ones; confusing and fragile. |
| No dependency list | Medium | No `requirements.txt` or `pyproject.toml`; reproducible installs and CI are harder. |
| No tests | Medium | Regressions and refactors are risky. |
| Inline/nested classes | Low | e.g. `DraggableContainer` defined inside `open_settings_overlay`; duplicates module-level class. |

### 6.2 Security & Reproducibility

| Issue | Severity | Description |
|-------|----------|-------------|
| Hardcoded PFX password | High | In `build-and-sign.bat` and `Release.bat`; anyone with repo access can sign as you. |
| Absolute paths in .spec | Medium | Spec references `C:\Users\Fran\...`; breaks on other machines or CI. |

### 6.3 Platform & Performance

| Issue | Severity | Description |
|-------|----------|-------------|
| Windows-only code | Low | ctypes Shell32, COM, certutil, Defender; fine if the product is Windows-only. |
| Cache size | Low | 10,000 full-res pixmaps can use a lot of RAM on huge folders; consider size-based or lower count. |

### 6.4 Minor

- README version (e.g. 1.7) can drift from `version.txt` (1.9).
- `save_config()` has a bug: it never sets `self.theme` in the fallback block when `load_config` fails (line 6319).

---

## 7. Is Python the Right Choice for Images?

**Short answer: Yes, for this product.**

- **Qt/PyQt** — Mature desktop UI, good image widgets and OpenGL integration; you already use them well.
- **QImageReader / QPixmap** — Solid for decode and display; allocation limit and auto-transform are used correctly.
- **OpenCV (cv2) + NumPy** — Standard for filters (e.g. LAB unsharp); performance is sufficient for single-image ops.
- **PIL** — Convenient for crop and similar; fits the current workflow.

**Alternatives considered:**

| Option | Pros | Cons |
|--------|------|------|
| **Electron + native/Node image libs** | Web tech, big ecosystem | Heavier install, more RAM; image tooling less natural than Qt/OpenCV. |
| **Tauri + Rust** | Small binary, fast | Full rewrite; you’d reimplement a lot of what you already have. |
| **Native C++/Qt** | Max performance, single binary | Much higher effort; your Python version is already responsive. |

**Recommendation:** Stay on **Python + PyQt6**. Focus on **structure, dependencies, tests, and security** rather than a stack change.

---

## 8. Recommended Next Steps

### Phase 1 — Quick wins (1–2 days)

1. **Security**  
   - Remove hardcoded PFX password from batch files.  
   - Use an environment variable (e.g. `IMAGE_CLASSIFIER_PFX_PASSWORD`) or a secure store; document in a short “Release” or “Build” readme.

2. **Build reproducibility**  
   - In the PyInstaller spec, use paths relative to the project root (e.g. `version.txt`, `star.ico`) so the same spec works on any machine and in CI.

3. **Dependencies**  
   - Add `requirements.txt` (or `pyproject.toml`) with pinned versions for: PyQt6, opencv-python, numpy, Pillow, send2trash, PyOpenGL (and any other direct deps).  
   - Optionally add a one-line “Development setup” to README.

4. **Version consistency**  
   - Single source of version (e.g. read from `version.txt` or `pyproject.toml`) and reuse in README/installer/UI where possible.

### Phase 2 — Structure and maintainability (1–2 weeks)

5. **Split the monolith**  
   - Move logically grouped code into modules, e.g.:  
     - `ui/` (main window, floating menu, overlays, help),  
     - `viewer/` (AdvancedGraphicsImageViewer, viewport),  
     - `workers/` (load, export, delete, sharpen),  
     - `config/` (load/save config and favorites),  
     - `i18n/` (translations),  
     - `imaging/` (sharpen_cv2, crop helpers if any).  
   - Keep `image-classifier.py` as a thin entry point that imports and runs the app.

6. **Deduplicate classes**  
   - Keep a single `WorkerSignals`, single `OverlayProgressDialog`, single `DraggableContainer`; remove duplicates and fix references (including the nested `DraggableContainer` in settings overlay).

7. **Fix config bug**  
   - In `load_config` exception path, set `self.theme` (and any other missing defaults) so `save_config` and UI stay in sync.

### Phase 3 — Quality and future-proofing (ongoing)

8. **Tests**  
   - Add a small test suite (e.g. pytest): config load/save, favorites JSON round-trip, path normalization, and any pure functions (e.g. sharpen input/output shapes).  
   - Optional: minimal GUI smoke test (e.g. start main window, load a folder) with a test image set.

9. **Cache tuning**  
   - Consider a max memory or max count lower than 10,000, or simple size-based eviction, to avoid OOM on very large folders.

10. **Documentation**  
    - Short “Architecture” or “Code layout” section in README or this file: main modules, where config/favorites live, and how to build/sign/release (without secrets in repo).

---

## 9. Conclusion

Image Classifier is a **strong desktop app** with a **thoughtful installer** and a **sensible tech stack**. The main improvements are **maintainability** (split file, deduplicate classes, add deps and tests) and **security/reproducibility** (no hardcoded password, portable spec). **Sticking with Python and PyQt6** and applying the steps above will make the project easier to evolve and more robust without a full rewrite.

If you tell me your priority (e.g. “Phase 1 only” or “split the monolith first”), I can outline concrete file-by-file steps or patches next.
