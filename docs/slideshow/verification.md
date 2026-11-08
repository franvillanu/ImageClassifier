# Slideshow verification — 2026-11-08

The dedicated Windows player is implemented on `feature/slideshow-panzoom-v2`. All 30 foreground variants agree with measured rebuilt-Slideo output at the tested timestamps. There are no known motion mismatches in those comparisons. This is sampled visual/geometry parity, not pixel equality or a guarantee for every image, display or GPU.

## Reference and visual checks

- Rebuilt Slideo and the existing v2 probe build successfully on Windows. The probe reports all 30 actions wired and nine fitted, centered zoom-in starts.
- The original vendor executable was not run. Recovered source, BAML, DLLs, PNG reference captures and WPF instrumentation stay in the separate Slideo workspace.
- The named inventory is in [effects.md](effects.md). Five numeric CSV fixtures contain 2,580 observations across landscape, portrait, square and panorama inputs; 960 × 540 and 1920 × 1080 logical viewports; 96/144-DPI rendering; timing knots and fade boundaries.
- A native `ViewerHost` run completed 120 cases: all 30 effects × four shapes, with eight-second playback, black background, first/quarter/middle/three-quarter/final captures. Its 600 live-clock observations pass the one-logical-pixel bounds and 0.01 opacity tolerances. Both slide boundaries are black.
- Raster and native OpenGL composition comparisons each cover 360 intermediate frames (30 effects × four shapes × three progress points). Maximum per-frame mean absolute RGB error: **0.668/255 raster**, **0.341/255 OpenGL**. Reference controls are excluded from this metric. The contact sheets were inspected; image sampling differs slightly, with matching foreground placement.
- Native OpenGL comparison uses the application's OpenGL 3.3 core/sRGB configuration, at 150% desktop scaling. No unrelated crossfade is added.

Reference-only tooling: `SimplySlideshow_Codex_Workspace/tests/ReferenceCapture/`. It reads native animation output; it is not distributed in ImageClassifier. The rebuilt main window exposes an existing `ResetState()` null-reference failure if left without a viewer. Isolated startup playback and the controlled native-host harness avoid that reference-app failure without changing recovered application source.

## Regression and lifecycle checks

The full pytest suite passes (**274 tests**). New tests cover the measured motion, zero/partial strength, resize without clock reset, sequential/shuffled cycles, repeat boundaries, retained history/effects, pause/resume, decode latency, stale results, missing/corrupt/all-failed inputs, shared-loader preview/full delivery, configuration compatibility, preservation of unknown configuration fields, filtered playlist snapshots and classifier selection/zoom preservation.

Twelve repeated open/close cycles release player frames and cancel its requests. Unavailable OpenGL construction switches to the shared raster paint routine. Sleep prevention remains requested during active loading/playback and is released on pause/close. Shared caches retain their existing bounds.

The packaged app was launched in a separate QA configuration with three synthetic photos. Windows UI checks passed for Spanish settings/defaults, F5, Start, Space pause/resume, Left/Right navigation while paused, F11, double-click fullscreen, automatic control hiding and Escape back to the unchanged classifier selection. English/Spanish translation key parity passes. Settings cancellation and playback-settings pause restoration also pass automated integration tests.

The player UI was subsequently refined to a compact floating icon bar, a fullscreen corner close control and a consistent settings dialog. The refined UI was checked in a native Windows preview; all 274 regression tests still pass. The motion engine is unchanged.

## Performance on this machine

Windows 11 build 26300; Intel Core i7-10700K; NVIDIA GeForce RTX 3060 Ti, driver 32.0.16.1088; one display, 150% scaling. Measurements are intervals between completed QPainter paints, excluding loading and the first second of each slide. They are not display scanout/photodiode measurements.

| Run | Physical surface | Duration | Slides | p95 interval | Maximum | Errors |
|---|---|---:|---:|---:|---:|---:|
| OpenGL soak | 1920 × 1080 | 1800.56 s | 561 | 17.98 ms | 21.83 ms | 0 |
| OpenGL fullscreen | 3840 × 2160 | 60.62 s | 20 | 16.83 ms | 33.38 ms | 0 |
| Raster | 1920 × 1080 | 60.04 s | 14 | 17.37 ms | 36.59 ms | 0 |

The 30-minute session used six synthetic files spanning JPEG, PNG, WebP, BMP and TIFF, and visited every effect. It includes two focus/deactivation pauses followed by explicit resume; it is not a claim of 30 uninterrupted minutes of animation. Player resources were released at completion. Raw summaries are in [soak-1080p.json](soak-1080p.json), [performance-4k.json](performance-4k.json) and [performance-raster.json](performance-raster.json). Both OpenGL p95 values meet the 25 ms target on this machine; individual frames can exceed it.

## Packaging and limits

PyInstaller builds the app with the existing spec and discovers the new slideshow modules and Qt OpenGL dependencies. A packaged Windows smoke test opens the player successfully. The build reports existing optional PyOpenGL legacy-DLL warnings (`MSVCR90.dll`/`MSVCR71.dll`); this session does not certify installer signing or distribution. Version files are unchanged; bilingual notes are prepared for 2.0.16, the patch after published 2.0.15.

Physical migration between screens and different desktop scaling settings remains untested: only one 150% display is available. Geometry/DPI behavior is covered by controlled measurements and tests. A real GPU-driver initialization failure was not induced; the raster path was run on Windows, and initialization-failure switching is tested. Performance is specific to this hardware, the synthetic files and the existing 4096-pixel preview limit. No universal 4K claim or legal-clearance guarantee is made.

## Reproduction

```powershell
py -m pytest -q
py scripts/verify_slideshow_windows.py --seconds 1800 --width 1280 --height 720 --output soak.json
py scripts/verify_slideshow_windows.py --seconds 60 --fullscreen --output fullscreen.json
py scripts/verify_slideshow_windows.py --seconds 60 --width 1280 --height 720 --raster --output raster.json
py scripts/compare_slideshow_reference.py ../SimplySlideshow_Codex_Workspace/reference-captures comparison-raster
py scripts/compare_slideshow_reference.py ../SimplySlideshow_Codex_Workspace/reference-captures-hidpi comparison-gl --opengl
```

The fullscreen command uses the available screen's resolution. Verify `physical_size` in its JSON before interpreting it as a 4K result. Keep the benchmark window active; deactivation intentionally pauses playback and reactivation alone does not resume it.
