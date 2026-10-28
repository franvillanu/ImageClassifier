# Release Protocol

This document outlines the complete checklist for releasing a new version of Image Classifier.

## Version Update Checklist

`version.txt` (`filevers=(X, Y, Z, W)` and the `'X.Y.Z.W'` strings) is the single source of truth. Everything else is synced from it:

- `image_classifier/__init__.py`, `pyproject.toml`, `package.json` - synced by `scripts/sync_version.py` (runs in `Release.bat`)
- `Image_Classifier.iss` - synced by `scripts/update_iss_version.py` (runs in `Release.bat`)
- About dialog - built from `__version__` (the `app_version_label` translations contain a `{version}` placeholder; do not hard-code a number)
- `docs/index.html` - updated by `scripts/update_website.py` (runs in `Release.bat`)
- `docs/changelog.html` - updated via `docs/release_notes.txt` and `scripts/auto_update_changelog.py`

⚠️ The in-app updater compares `image_classifier.__version__` with the latest release in
`franvillanu/imageclassifier-releases`. If `__version__` lags behind `version.txt`, the app offers the same update forever.
`scripts/create_github_release.py` refuses to publish when they differ, and `tests/test_version_sync.py` checks it.

## Release Process

One task does everything: **run the VS Code task "PR: create + merge (squash) + update main + delete branch"** (Ctrl+Shift+5).

1. **Add the customer-facing line** for the new version at the top of `docs/release_notes.txt` (`version|EN|ES`). That line is the trigger: the newest version in that file is the version being released. Commit your code changes as usual.
2. **Run the task.** If that version is not published yet in `franvillanu/imageclassifier-releases`, it automatically:
   - sets `version.txt` (and syncs `__init__.py`, `pyproject.toml`, `package.json`) to that version (`scripts/auto_bump_version.py`),
   - runs `Release.bat` to update changelog and website, build and sign the app and installer,
   - commits the release files (`release: prepare vX.Y.Z`), creates and squash-merges the PR,
   - publishes the release (installer, notes, hidden bilingual notes for the in-app updater) to the releases repo.
3. **Verify** the About dialog version and the website download link.

With no unpublished version in `release_notes.txt` (a plain bug-fix PR), the task just creates and merges the PR.
If the published installer for a version differs from the local one, the task warns instead of skipping silently.
`Release.bat` can still be run alone: if the current version is already published it bumps the patch number.

## Testing Checklist

Before releasing, verify:
- [ ] About dialog shows correct version (English)
- [ ] About dialog shows correct version (Spanish - switch language)
- [ ] Version in `version.txt` matches About dialog
- [ ] An older install offers the update (`IMAGE_CLASSIFIER_FAKE_VERSION=<older>`), downloads with progress, and restarts
- [ ] Installer shows correct version
- [ ] Website shows correct version
