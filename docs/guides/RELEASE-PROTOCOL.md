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

One task does everything: **run the VS Code task "PR: create + merge (squash) + update main + delete branch"** (Ctrl+Shift+5). Commit your changes first; there is nothing to remember to bump or write.

The task decides by itself whether a release is needed (`scripts/auto_bump_version.py`). A release is pending when:
- app files changed since the last `release: prepare vX.Y.Z` commit on `main` (`image_classifier/`, `image-classifier.py`, `star.ico`, `requirements.txt`, `Image_Classifier.iss`), or
- the newest version in `docs/release_notes.txt` is not published yet (use this to choose a bigger version, e.g. add `2.1.0|EN|ES` at the top).

Docs-, test- and script-only PRs do not trigger a release: the task just creates and merges the PR.

When a release is pending, the task automatically:
1. bumps the patch version (or uses the notes' version) and syncs `version.txt`, `__init__.py`, `pyproject.toml`, `package.json`,
2. writes the release-notes line from your `feat:`/`fix:`/`perf:`/`refactor:` commit subjects if the version has none (the Spanish text is a copy of the English one; edit `docs/release_notes.txt` in the next PR to polish it, or add your own line before running to control the wording),
3. runs `Release.bat` (changelog, website, build, sign),
4. commits the release files (`release: prepare vX.Y.Z`), pushes, creates and squash-merges the PR,
5. publishes the release to `franvillanu/imageclassifier-releases`,
6. **verifies it** (`scripts/verify_release.py`): version, the published installer's checksum against the local build, and the in-app notes. It ends with `Release verificado ✅`, or a red `RELEASE NO VERIFICADO ❌` and a failing exit code.

Then check the About dialog version and the website download link.
`Release.bat` can still be run alone: if the current version is already published it bumps the patch number.

## Testing Checklist

Before releasing, verify:
- [ ] About dialog shows correct version (English)
- [ ] About dialog shows correct version (Spanish - switch language)
- [ ] Version in `version.txt` matches About dialog
- [ ] An older install offers the update (`IMAGE_CLASSIFIER_FAKE_VERSION=<older>`), downloads with progress, and restarts
- [ ] Installer shows correct version
- [ ] Website shows correct version
