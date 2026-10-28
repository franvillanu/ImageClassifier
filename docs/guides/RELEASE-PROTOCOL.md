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

1. **Bump the version** in `version.txt` with `py scripts/bump_version.py patch|minor|major` (or edit by hand)
2. **Add the customer-facing line** to `docs/release_notes.txt` (`version|EN|ES`)
3. **Run `Release.bat`**: syncs versions, updates changelog and website, builds, signs, creates `Output/ImageClassifierSetup_vX.Y.Z.exe`
4. **Merge with the PR task**: its last step publishes the release to `franvillanu/imageclassifier-releases` (see [GITHUB-RELEASE-SETUP.md](GITHUB-RELEASE-SETUP.md))
5. **Verify** the About dialog version and the website download link

## Testing Checklist

Before releasing, verify:
- [ ] About dialog shows correct version (English)
- [ ] About dialog shows correct version (Spanish - switch language)
- [ ] Version in `version.txt` matches About dialog
- [ ] An older install offers the update (`IMAGE_CLASSIFIER_FAKE_VERSION=<older>`), downloads with progress, and restarts
- [ ] Installer shows correct version
- [ ] Website shows correct version
