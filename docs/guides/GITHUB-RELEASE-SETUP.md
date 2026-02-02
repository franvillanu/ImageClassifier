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

**Option A: Environment Variable (Recommended for Windows)**

**Windows 10/11 (GUI Method):**
1. Press `Win + X` and select "System"
2. Click "Advanced system settings" (or search for it)
3. Click "Environment Variables"
4. Under "User variables", click "New"
5. Variable name: `GITHUB_TOKEN`
6. Variable value: `your_token_here` (paste your token)
7. Click OK on all dialogs

**Windows (Command Line Method):**
```powershell
# For current session only (temporary)
$env:GITHUB_TOKEN = "your_token_here"

# For permanent (user-level, persists after restart)
[System.Environment]::SetEnvironmentVariable("GITHUB_TOKEN", "your_token_here", "User")
```

**Option B: Local File (Easier, but less secure)**
- Create a file named `.github_token` in the repository root (`C:\Users\Fran\Documents\repos\ImageClassifier\.github_token`)
- Put your token as a single line (no quotes, no spaces)
- Example content:
  ```
  ghp_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
  ```
- This file is gitignored and won't be committed

**Which option to choose?**
- **Environment Variable**: More secure, works system-wide, persists across terminal sessions
- **Local File**: Easier to set up, but file could be accidentally deleted or accessed

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
- **After setting environment variable**: Close and reopen your terminal/PowerShell window

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

### Testing Your Token Setup

To verify your token is set correctly, open a **new** PowerShell window and run:

```powershell
echo $env:GITHUB_TOKEN
```

If it shows your token (or at least something), it's working. If it's empty, the environment variable wasn't set correctly.

## Security Notes

- **Never commit** `.github_token` file (it's gitignored)
- **Never share** your GitHub token
- Tokens with `repo` scope have full access to your repositories
- You can revoke tokens at any time from GitHub settings
- Environment variables are more secure than files

## Integration with Website

The website (`docs/index.html`) automatically uses the GitHub Release download URL:
```
https://github.com/franvillanu/ImageClassifier/releases/download/v{VERSION}/ImageClassifierSetup_v{VERSION}.exe
```

This is updated automatically when you run `scripts/update_website.py` (which runs during release).

**Note:** Cloudflare is only for hosting your website. The GitHub token is set **locally on your Windows machine** where you run `Release.bat`.
