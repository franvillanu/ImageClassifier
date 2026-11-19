# SPEC-006 — Open in Explorer

Status: active, started · Code: `shell_win.py` (`open_folder_and_select_item`), `app.py` (`open_image_in_path`)
Tests: `tests/test_spec_open_in_explorer.py`

The context menu's "Open in Explorer" opens a File Explorer window on the photo's folder with the photo selected.

## Requirements

| ID | Requirement | Why |
|---|---|---|
| EX-1 | Opening in Explorer first asks the Shell (`SHOpenFolderAndSelectItems`) to open the folder with the file selected, and tries it a second time if it fails. | It reuses an Explorer window already on that folder and selects the file. |
| EX-2 | If the Shell still fails, the app runs `explorer.exe /select,"<path>"`, which also opens the folder with the file selected; the user sees an error only if that cannot start either. | User (2026-11-19, screenshot): "SHOpenFolderAndSelectItems failed (0x80004005)". The Shell call fails now and then for the same path that worked a moment earlier (see Evidence), and the app used to show that as an error with no other way to open the folder. |
| EX-3 | The item ID list the Shell returns for the path is always freed, whether the call works or not. | It is memory allocated by the Shell for us (`CoTaskMemFree`); it used to leak on every use. |

## Evidence

- 2026-11-19: the code had not changed since the initial commit. Calling `open_folder_and_select_item` six times in a
  row from a script, 0.3 s apart, on the same path: five returned S_OK and the sixth returned E_FAIL (0x80004005).
  Another script run failed on its first call. So the failure is intermittent in the Shell, not caused by the path.

## Decision log

- 2026-11-19: keep the Shell call as the first choice (it reuses an open window) but never show its failure directly;
  retry once, then fall back to `explorer.exe /select`. Explorer reveal in the real app is unverified offscreen: the
  fallback path is proven by tests that make the Shell call fail.
