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

1. **Add the customer-facing line** for the next version to `docs/release_notes.txt` (`version|EN|ES`). The app shows it after the update, and the release carries it for the update pill.
2. **Run `Release.bat`**: if the current version is already published, it bumps the patch version automatically (`scripts/auto_bump_version.py`; use `py scripts/bump_version.py minor|major` first for a bigger bump). Then it syncs versions, updates changelog and website, builds, signs, creates `Output/ImageClassifierSetup_vX.Y.Z.exe`
3. **Run the PR task**: it commits the files Release.bat changed (`release: prepare vX.Y.Z`), merges, then publishes the release to `franvillanu/imageclassifier-releases` (see [GITHUB-RELEASE-SETUP.md](GITHUB-RELEASE-SETUP.md)). If the published installer differs from the local one it warns instead of skipping silently.
5. **Verify** the About dialog version and the website download link

## Testing Checklist

Before releasing, verify:
- [ ] About dialog shows correct version (English)
- [ ] About dialog shows correct version (Spanish - switch language)
- [ ] Version in `version.txt` matches About dialog
- [ ] An older install offers the update (`IMAGE_CLASSIFIER_FAKE_VERSION=<older>`), downloads with progress, and restarts
- [ ] Installer shows correct version
- [ ] Website shows correct version
