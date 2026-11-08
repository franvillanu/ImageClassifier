# Pan & Zoom v2 foreground inventory

Measured on Windows on 2026-11-08 using the rebuilt Slideo assembly. No vendor executable was run. Reference tooling, recovered code and image captures remain in `SimplySlideshow_Codex_Workspace`. This repository contains independently authored Python and numeric observations only.

## Coordinate and timing convention

The measured WPF viewport is 960 × 540 logical pixels. Four synthetic grids are 1200 × 800, 800 × 1200, 1000 × 1000 and 2400 × 600. Fit the EXIF-oriented image uniformly, centered; use the center (0.5, 0.5) as transform origin. The WPF transform group is scale → skew → rotation → translation, with skew and rotation observed as identity. Scale first, then translate in logical pixels. At the measured points, transformed bounds agree with that rule. Translations remain identical across these four image proportions; unused viewport area is black. Large sweeps intentionally expose black areas.

All 30 natural timelines last 25 timeline seconds. Playback scales the timeline to the chosen slide duration. Each measured channel is piecewise linear; dense measurements for landscape cover every 0.01 timeline seconds. Effects 1–10 fade from opacity 0 to 1 over timeline seconds 0–3; effects 11–30 do so over 0–2. All hold 1 until second 22 and fade to 0 at second 25. Both boundaries therefore show black; no crossfade is added.

Tuples below are `(scale, translation X, translation Y)` and use logical pixels. All zoom-in starts are fitted and centered. The nine are 1–6, 20, 29 and 30. Effects 3–5 have identical measured foreground geometry; their identifiers remain separate.

| ID | Name | Start | End |
|---|---|---|---|
| v2-01 | Gentle zoom with return | (1, 0, 0) | (1.2, 0, 0) |
| v2-02 | Gentle zoom right up | (1, 0, 0) | (1.1, 9.8, -1.4) |
| v2-03 | Gentle zoom left down A | (1, 0, 0) | (1.1, -7.2, 7.6) |
| v2-04 | Gentle zoom left down B | (1, 0, 0) | (1.1, -7.2, 7.6) |
| v2-05 | Gentle zoom left down C | (1, 0, 0) | (1.1, -7.2, 7.6) |
| v2-06 | Zoom left up | (1, 0, 0) | (1.3, -36, -23) |
| v2-07 | Sweep right | (1, -720, 0) | (1, 699, -1) |
| v2-08 | Sweep right down | (1, -636, -394) | (1, 629, 388) |
| v2-09 | Sweep down | (1, 1, -461) | (1, -1, 462) |
| v2-10 | Gentle retreat with excursion | (1.1, 0, 0) | (1, 0, 0) |
| v2-11 | Centered retreat | (1.5, 0, 0) | (1, 0, 0) |
| v2-12 | Retreat from upper left | (2, -53, -39) | (1.2, 0, 0) |
| v2-13 | Retreat from upper right | (2, 55, -51) | (1.2, 0, 0) |
| v2-14 | Retreat from lower right | (2, 51, 47) | (1.2, 0, 0) |
| v2-15 | Retreat from lower left | (2, -44, 38) | (1.2, 0, 0) |
| v2-16 | Sweep up | (1, 1, 243) | (1, 2, -322) |
| v2-17 | Sweep left | (1, 617, 0) | (1, -611, 1) |
| v2-18 | Sweep left up | (1, 435, 274) | (1, -467, -242) |
| v2-19 | Sweep right up | (1, -488, 257) | (1, 469, -257) |
| v2-20 | Centered approach | (1, 0, 0) | (1.5, -1, 2) |
| v2-21 | Deep centered retreat | (2, 0, 0) | (1, 0, 0) |
| v2-22 | Magnified pan left | (1.5, 377, 0) | (1.5, -377, 0) |
| v2-23 | Deep pan left up | (2, 377, 300) | (2, -377, -300) |
| v2-24 | Magnified pan down | (1.5, 0, -300) | (1.5, 0, 300) |
| v2-25 | Deep pan right up | (2, -377, 300) | (2, 377, -300) |
| v2-26 | Retreat down | (2, 0, -300) | (1, 0, 300) |
| v2-27 | Retreat right | (2, -377, 0) | (1, 377, 0) |
| v2-28 | Retreat left down | (2, 377, -300) | (1, -377, 300) |
| v2-29 | Approach right | (1, 0, 0) | (1.5, 377, 0) |
| v2-30 | Approach down | (1, 0, 0) | (1.5, 0, 300) |

## Intermediate motion

Effect 1 reaches `(1.1, -7.2, 7.6)` at second 22 and then reaches its final tuple at second 25. Effect 10 scales linearly throughout, while its translation reaches `(55, -40.143)` at second 8.75, returns to `(0, 0)` at second 22 and stays there. All remaining scale and translation channels interpolate linearly between their endpoints.

## Reproduction and evidence limits

The reference workspace's `tests/ReferenceCapture/ReferenceCapture.csproj` builds a black-box WPF capture tool. It begins each v2 action, seeks the native controllable clock to normalized timestamps and records the actual transform, opacity and transformed bounds. It captures PNGs at 0%, 25%, 50%, 75%, 100% for every effect and shape; `reference-captures/observations.csv` records the measurements. A separate native-host run plays all 30 actions across the four shapes, with an explicit 8-second duration and background disabled; it captures both black boundaries and three intermediate live-clock positions for each of 120 cases. The host content viewport measured 942.667 × 500 logical pixels.

The five CSV fixtures in `tests/fixtures/slideshow/` contain 2,580 numeric observations: 600 at each of three viewport/DPI configurations, 180 at intermediate knots/fade boundaries and 600 from live clocks in the native ViewerHost. The automated comparison checks geometry to one logical pixel and opacity to 0.01. Easing classification is based on observed slopes, not on copying storyboard resources.

The rebuilt main window was launched directly with isolated APPDATA/LOCALAPPDATA and three synthetic inputs. Leaving it without a viewer exposed a pre-existing NullReferenceException in MainViewModel.ResetState. A reference-only launcher setting startup playback allowed the unchanged recovered application to play those three files, with v2 selected and background disabled. A native viewer displaying the synthetic grids was observed. Reference-only startup tooling is not part of ImageClassifier.

All 120 native-host cases completed. The Qt implementation agrees with their measured bounds within one logical pixel and opacity within 0.01. Reference viewports also include 960 × 540 at 150% DPI and 1920 × 1080 at 150% DPI. Native OpenGL and raster comparison tools each compared 360 intermediate compositions across all 30 effects and four image proportions. Sampling differences remain; pixel equality is not claimed. Physical screen-to-screen migration remains untested because this machine exposes one screen. See verification.md for hardware, performance results and remaining limits.
