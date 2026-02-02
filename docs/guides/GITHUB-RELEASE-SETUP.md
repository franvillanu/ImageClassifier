# GitHub Release Automation Setup

This guide explains how to set up automated GitHub Releases for Image Classifier.

## Overview

After building the installer with `Release.bat`, you can automatically:
1. Create a GitHub Release with the version tag (e.g., `v2.0`)
2. Upload the installer `.exe` file as a release asset
3. Generate release notes from `changelog.html`

The download link on your website will automatically point to the GitHub Release.

## Setup Steps

### 1. Install Required Python Package

The script requires the `requests` library:

```bash
py -m pip install requests
```

### 2. Create GitHub Personal Access Token

1. Go to https://github.com/settings/tokens
2. Click "Generate new token" → "Generate new token (classic)"
3. Give it a name like "Image Classifier Release"
4. Select scope: **`repo`** (full control of private repositories)
5. Click "Generate token"
6. **Copy the token immediately** (you won't see it again!)

### 3. Store the Token

You have two options:

**Option A: Environment Variable (Recommended)**
- Set `GITHUB_TOKEN` environment variable with your token value
- This works system-wide and is more secure

**Option B: Local File**
- Create a file named `.github_token` in the repository root
- Put your token as a single line (no quotes, no spaces)
- This file is gitignored and won't be committed

## Usage

### Automatic (Recommended)

When you run `Release.bat`, it will prompt you:

```
Create GitHub Release? (y/N):
```

Type `y` and press Enter. The script will:
- Create a release with tag `v{VERSION}` (e.g., `v2.0`)
- Upload the installer file
- Generate release notes from changelog.html

### Manual

You can also run the script directly:

```bash
py scripts/create_github_release.py
```

## How It Works

1. **Reads version** from `version.txt`
2. **Extracts release notes** from the latest entry in `changelog.html`
3. **Creates GitHub Release** with tag `v{VERSION_SHORT}` (e.g., `v2.0`)
4. **Uploads installer** from `Output/ImageClassifierSetup_v{VERSION_FULL}.exe`

## Troubleshooting

### "GitHub token required"
- Make sure you've set `GITHUB_TOKEN` environment variable or created `.github_token` file
- Verify the token has `repo` scope

### "requests library not installed"
```bash
py -m pip install requests
```

### "Installer file not found"
- Make sure `Release.bat` completed successfully
- Check that `Output/ImageClassifierSetup_v*.exe` exists

### "Release already exists"
- The script will update the existing release if it already exists
- Or manually delete the release on GitHub and try again

### "Asset already exists"
- If you run the script twice, the asset upload will be skipped (warning only)
- The release will still be updated with new notes if changelog changed

## Security Notes

- **Never commit** `.github_token` file (it's gitignored)
- **Never share** your GitHub token
- Tokens with `repo` scope have full access to your repositories
- You can revoke tokens at any time from GitHub settings

## Integration with Website

The website (`docs/index.html`) automatically uses the GitHub Release download URL:
```
https://github.com/franvillanu/ImageClassifier/releases/download/v{VERSION}/ImageClassifierSetup_v{VERSION}.exe
```

This is updated automatically when you run `scripts/update_website.py` (which runs during release).
