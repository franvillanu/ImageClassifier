# Fully Automated Release Workflow

## Overview

**Goal:** Focus only on making app changes. Everything else is automated:
- ✅ Website updates automatically
- ✅ Changelog updates automatically (from git commits)
- ✅ Download link updates automatically
- ✅ GitHub Release created automatically
- ✅ Installer built automatically

## How It Works

### 1. You Make Changes
```bash
# Edit your code, update version.txt
git add .
git commit -m "feat: add new feature"
git push
```

### 2. Run PR Script (One Command)
```powershell
.vscode/pr_create_merge_update.ps1
```

### 3. Everything Happens Automatically

**If version changed:**
1. ✅ Detects version change in `version.txt`
2. ✅ Runs `Release.bat` automatically:
   - Builds installer
   - Updates changelog from git commits
   - Updates website with new version
   - Updates download link to GitHub Releases
   - Creates GitHub Release
   - Uploads installer
3. ✅ Commits website/changelog updates
4. ✅ Creates PR
5. ✅ Merges PR automatically

**If version NOT changed:**
- Just creates PR and merges (normal workflow)

## What Gets Automated

### Changelog (`docs/changelog.html`)
- **Source:** Git commit messages since last release
- **Process:** Extracts commits, formats them, adds to changelog
- **When:** Automatically during `Release.bat`

### Website (`docs/index.html`)
- **Updates:** Version number, download link, "What's New" section
- **Download Link:** Points to GitHub Releases automatically
- **When:** Automatically during `Release.bat`

### GitHub Release
- **Created:** Automatically if `.github_token` exists
- **Contains:** Installer file, release notes from changelog
- **When:** Automatically during `Release.bat`

## Requirements

### One-Time Setup

1. **GitHub Token** (for auto-creating releases):
   - Create `.github_token` file in repo root
   - Put your GitHub Personal Access Token (with `repo` scope) in it
   - File is gitignored, stays local

2. **Python Package**:
   ```bash
   py -m pip install requests
   ```

## Workflow Examples

### Example 1: Bug Fix (No Version Change)
```bash
# 1. Fix bug
git checkout -b fix/bug-description
# ... edit code ...
git add .
git commit -m "fix: resolve crash issue"
git push

# 2. Run PR script
.vscode/pr_create_merge_update.ps1

# Result: PR created and merged, no release
```

### Example 2: New Feature (Version Change)
```bash
# 1. Update version
# Edit version.txt: 2.0.0.0 → 2.1.0.0

# 2. Add feature
git checkout -b feature/new-feature
# ... edit code ...
git add .
git commit -m "feat: add dark mode toggle"
git push

# 3. Run PR script
.vscode/pr_create_merge_update.ps1

# Result:
# ✅ Installer built
# ✅ Changelog updated (from commits)
# ✅ Website updated
# ✅ GitHub Release created
# ✅ Download link updated
# ✅ PR created and merged
```

## File Changes Summary

| File | Purpose | When Updated |
|------|---------|--------------|
| `version.txt` | Version number | **You edit manually** |
| `docs/changelog.html` | Release notes | **Auto** (from git commits) |
| `docs/index.html` | Website | **Auto** (version + download link) |
| `Output/*.exe` | Installer | **Auto** (built by Release.bat) |
| GitHub Release | Release page | **Auto** (created by script) |

## What You Need to Do

1. **Edit code** - Make your changes
2. **Update version** - Edit `version.txt` when releasing
3. **Commit** - Normal git workflow
4. **Run PR script** - `.vscode/pr_create_merge_update.ps1`

That's it! Everything else is automated.

## Troubleshooting

### "GitHub Release not created"
- Check `.github_token` file exists and has valid token
- Token needs `repo` scope

### "Changelog empty"
- Make sure you have commits since last release
- Commits should have meaningful messages (they become changelog entries)

### "Website not updated"
- Check `scripts/update_website.py` runs successfully
- Check `docs/index.html` is writable

### "Installer not built"
- Check `Release.bat` completes successfully
- Check PyInstaller and signing tools are installed

## Summary

**Before:** Manual steps for changelog, website, GitHub releases, download links

**Now:** 
1. Edit code
2. Update version (if releasing)
3. Run PR script
4. Done! 🎉

Everything else is fully automated.
