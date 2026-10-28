# GitHub Release Setup

Image Classifier installers are published to a **separate public repo that holds only releases**:
[`franvillanu/imageclassifier-releases`](https://github.com/franvillanu/imageclassifier-releases).
The source repo can stay private. The website download button and the in-app updater both read from the releases repo, and neither needs a token.

## One-time setup

1. Install the GitHub CLI and log in: `gh auth login` (account `franvillanu`, with permission to create releases in the releases repo).
2. Create the releases repo (done once):
   ```powershell
   gh repo create franvillanu/imageclassifier-releases --public --add-readme --description "Image Classifier installers (releases only)"
   ```
3. Copy the historical releases (v2.0 to v2.0.7), oldest first. Safe to re-run:
   ```powershell
   pwsh -File scripts/migrate_releases.ps1 -DryRun   # preview
   pwsh -File scripts/migrate_releases.ps1
   ```

There is no token file, no `GITHUB_TOKEN` and no `requests` dependency any more. `.github_token` is no longer used.

## Releasing

Commit your changes and run the VS Code task **PR: create + merge (squash) + update main + delete branch**. It decides by itself whether a release is needed (app files changed since the last release, or a newer version in `docs/release_notes.txt`), then bumps the version, writes the notes if missing, builds, merges, publishes to the releases repo and verifies the result. See [RELEASE-PROTOCOL.md](RELEASE-PROTOCOL.md) for the details.

To publish by hand: `py scripts/create_github_release.py`.

## What the publish script does

1. Reads the version from `version.txt` and stops if `image_classifier.__version__` differs. (The app compares `__version__` with the latest release, so a mismatch would offer the same update forever.)
2. Requires exactly `Output/ImageClassifierSetup_v{VERSION}.exe`. It never falls back to another installer.
3. Builds the release body from `docs/changelog.html` plus `docs/releases/installer.md`.
4. If tag `v{VERSION}` exists in the releases repo, it edits the notes and re-uploads the installer with `--clobber`. Otherwise it creates the release and marks it **Latest**.

## How the app updates itself

- On startup (if "Check for updates at startup" is on) and from **About → Check for updates**, the app reads `api.github.com/repos/franvillanu/imageclassifier-releases/releases/latest`. If GitHub rate-limits that, it reads the tag from the `releases/latest` redirect instead.
- **Update** downloads the installer inside the app with a progress bar and verifies the size and the SHA-256 digest GitHub reports.
- **Restart to update** runs the installer silently (`/SILENT /UPDATE=1`). Windows shows a UAC prompt because the installer needs admin rights. The app closes, the installer upgrades it, and the app reopens. If UAC is declined, the app stays open.
- Asset names must stay `ImageClassifierSetup_v{M.m.b}.exe`. The updater only accepts that pattern from the releases repo.
- Testing: `IMAGE_CLASSIFIER_FAKE_VERSION=2.0.0` pretends to be an older version, `IMAGE_CLASSIFIER_FORCE_UPDATE_CHECK=1` enables the startup check when running from source, and `IMAGE_CLASSIFIER_UPDATES_OFFLINE=1` disables network checks.

## Website

`docs/index.html` links to
`https://github.com/franvillanu/imageclassifier-releases/releases/download/v{VERSION}/ImageClassifierSetup_v{VERSION}.exe`.
`scripts/update_website.py` keeps it current during `Release.bat`.

## Troubleshooting

- **`gh` not found / not logged in:** install the GitHub CLI and run `gh auth login`.
- **"Installer not found":** run `Release.bat` first; check `Output/`.
- **"__version__ ... but version.txt is ...":** run `py scripts/sync_version.py`.
- **Release exists but the asset is missing or wrong:** run the publish script again; it re-uploads with `--clobber`.
