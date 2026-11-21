# SPEC-007 — Huge images (maps, orthomosaics)

Status: active, started · Code: `imaging/huge.py`, `workers/huge_worker.py`, `ui/image_viewer.py`
(`request_full_resolution`, detail tier), `app.py` (`saveModifiedImage`, `_full_resolution_gate`, `open_editor`),
`editor/editor_window.py` (basic mode), `ui/huge_job.py`
Tests: `tests/test_spec_huge_images.py`

A *huge* image has more than 100 million pixels (e.g. TagLab orthomosaics, ~32,000 × 28,000 px = 896 MP, 30–120 MB
as JPEG, 3.6 GB as an uncompressed QImage). It is never decoded whole into the viewer: the viewer shows a
screen-sized preview, then a larger **detail** frame (long side 8192 px), and anything that needs every pixel
(rotating and saving) works on the file in a background job.

## Requirements

| ID | Requirement | Why |
|---|---|---|
| HI-1 | An image is huge when width × height is above 100 MP. Below that nothing changes. | Qt's 512 MB allocation limit refuses a full decode from ~134 MP; 100 MP (400 MB as RGB32) is the safe ceiling the viewer already handles. |
| HI-2 | A decode that fails for any reason (including Pillow's decompression-bomb error and out-of-memory) reports an error to the viewer; a worker never ends without a result. | Measured: a 224 MP JPEG raised `DecompressionBombError`, which the loader did not catch, so no signal was ever sent and "Full-resolution image is still loading" never went away (user: not loaded after 10 minutes). |
| HI-3 | For a huge image the viewer never requests a full-resolution decode; it requests the detail frame instead and `full_resolution_ready` stays false. | A full decode needs ≈ 3.6 GB per copy (several copies while converting): it cannot finish on most machines. |
| HI-4 | The detail frame is decoded with Pillow reduced decoding (long side ≤ 8192 px), keeps the true source size, and replaces the displayed pixels without moving the camera (same rule as CV-8). | Zooming a map needs more than the 4096 px preview; the camera is in source pixels so a frame swap must not move it. |
| HI-5 | While the detail frame loads, a status line shows what is loaded and how far the load is, as a percentage of the file read (real, from the bytes consumed), e.g. "Large image 32000 × 28000 (896 MP) · preview shown · detail 8192 px 42 %". It says "detail ready" when done and disappears a few seconds later. | User: the user has no clue what is being loaded or how far it is from complete. |
| HI-6 | Saving a rotated huge image (as a copy or overwriting) runs in a background job on the file: read, rotate by the viewer's quarter turns (plus the EXIF orientation), write with the source's EXIF/ICC, atomic replace. The UI stays responsive and a progress dialog shows the stage and a real percentage while reading, and an animated bar (no invented percentage) while writing. It can be cancelled and then leaves the original untouched. | The Qt path would need ≈ 15 GB for 896 MP; Pillow needs ≈ 2 images (5.4 GB). The user must see how far it is. |
| HI-7 | Actions that need the pixels in memory (the old crop overlay, brightness, sharpness) on a huge image say that the image is too large and point to Edit, instead of "still loading". Brightness on a huge image is not saved with a rotation or an edit: the save is refused with a message. | The old message was false forever for these files. Silently dropping the brightness would lose the user's edit. |
| HI-8 | Rotating a huge image on screen (R) is instant: it uses the frame in memory. | User: "I need to rotate them". |
| HI-9 | Edit on a huge image opens the editor in basic mode: only the Crop tab (turn, flip, straighten, aspect, crop) with its Done and Save; the Ajuste and Remove tabs, Auto and copy-to-clipboard are not offered. It works on the frame in memory (detail or preview) while the edit state is in true source pixels. | User: the rotation/alignment screen is what is needed for maps; the full editor needs every pixel in memory. The editor already shows a reduced proxy and only uses the full pixels on save. |
| HI-10 | Saving from basic mode (copy or replace) renders the edit from the file in a background job, in strips: EXIF upright, turn/flip, straighten and crop in one resampling. The result has exactly the crop's size. A progress dialog shows a real percentage (strips done) with Cancel; cancelling or a failure leaves the original untouched and the editor open. | Same limits as HI-6; one resampling keeps quality; the user must see how far it is. |
| HI-11 | The file render gives the same pixels as the editor's own render for the same state (turn, straighten, crop), within resampling tolerance. | The user sees the proxy; the saved file must be what they framed. |

## Evidence

- 2026-11-21: 16000 × 14000 JPEG (224 MP, proxy for the 896 MP files; machine had 2.2 GB free RAM of 32 GB).
  `QImageReader.read()` with `setAllocationLimit(512)` → null, "Unable to read image data"; `_read_with_pillow` →
  `DecompressionBombError` (limit 178,956,970 px), which is not among the exceptions the loader catches.
  Result: the loader thread ended silently; `full_resolution_ready` stayed false.
- 2026-11-21: Pillow with a file wrapper that counts bytes read reports 0/25/50/75/100 % monotonically while decoding,
  so a real progress value is available for the read stage. Full decode 1.5 s, transpose 0.5 s, JPEG q95 encode 2.2 s
  on the proxy (low-entropy test image: real maps will be several times slower).

- 2026-11-21 (after the change): same 224 MP file with the real 100 MP threshold: detail frame 8192 × 7168 with the
  true source size (16000, 14000); rotate-and-save 5.1 s, stages read → rotate → write, output 14000 × 16000. The
  overwrite test found a Windows-only bug (the progress reader still held the source open, so the atomic replace was
  denied); the reader is now closed once the image is decoded. `py -m pytest -q`: 490 passed.
- 2026-11-21 (basic editor): the editor already shows only a reduced proxy and uses the full pixels once, in `_run_final`;
  its state (crop, angle, orientation) is in true source pixels. `huge.edit_file` reuses `output_to_source_matrix` with one
  Pillow AFFINE resampling per strip. Against the editor's own `render()` on a 640 x 400 image: exact (max diff 0) for
  unrotated crops in all orientations/flips; straightened crops mean diff < 2 (bicubic vs Lanczos). 224 MP JPEG, turn +
  2.5 deg + crop to 11200 x 12800: 70 s, 25 progress steps, exact output size. So ~4 x that, several minutes, for 896 MP.

## Decision log

- 2026-11-21: tiles/pyramid viewing (true 1:1 pixels at any zoom) is out of scope: the detail frame is 8192 px of a
  32,000 px map (≈ 1/4). Pixel-exact zoom needs a tiled viewer; not done.
- 2026-11-21: non-JPEG huge files (PNG/TIFF) cannot be decoded reduced by Qt; they now fail with a message
  instead of hanging.
- Unverified offscreen: the status line and progress dialog appearance, and timing on the real 896 MP files.
