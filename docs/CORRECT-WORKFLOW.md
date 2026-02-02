# Correct Release Workflow

## Your Expected Flow ✅

1. **Work on branch** - Make changes, update version.txt
2. **Run Release.bat** - Builds installer, updates website/changelog locally
3. **Commit changes** - Website files ready
4. **Run PR script** - Merges to main
5. **Website deploys** - Cloudflare automatically deploys
6. **Download works** - Users can download latest version

## What Happens When

### Step 1: You Run Release.bat (On Your Branch)

**What it does:**
- ✅ Checks version.txt is updated
- ✅ Updates changelog from git commits
- ✅ Updates website files (index.html) with new version
- ✅ Updates download link (points to GitHub Releases URL)
- ✅ Builds installer (Output/ImageClassifierSetup_vX.X.X.X.exe)
- ❌ **Does NOT create GitHub Release yet** (happens after merge)

**Result:**
- Installer built ✅
- Website files updated locally ✅
- Ready to commit ✅

### Step 2: You Commit and Run PR Script

**What PR script does:**
1. Detects version change
2. Runs Release.bat (if needed - builds installer)
3. Commits website/changelog updates
4. Creates PR
5. Merges PR to main
6. **After merge:** Creates GitHub Release
7. **After merge:** Cloudflare deploys website automatically

**Result:**
- Code merged to main ✅
- GitHub Release created ✅
- Website deploying ✅
- Download link will work once deployment completes ✅

## Why This Order?

**GitHub Release AFTER merge:**
- Release points to code that's actually in main
- Website and release are in sync
- Download link works immediately after deployment

**Website deploys automatically:**
- Cloudflare workflow triggers on push to main
- Runs `update_website.py` to ensure latest
- Deploys `docs/` folder

## Example Flow

```bash
# 1. You're on feature branch
git checkout -b feature/new-feature

# 2. Make changes, update version
# Edit version.txt: 2.0.0.0 → 2.1.0.0
# Edit code...

# 3. Run Release.bat
Release.bat
# → Builds installer
# → Updates changelog
# → Updates website files locally
# → NO GitHub Release yet

# 4. Commit everything
git add .
git commit -m "feat: new feature"
git push

# 5. Run PR script
.vscode/pr_create_merge_update.ps1
# → Detects version change
# → Commits website updates
# → Creates PR
# → Merges to main
# → Creates GitHub Release (AFTER merge)
# → Cloudflare deploys website

# 6. Done! Users can download from website
```

## What If You Run Release.bat Now?

**Current state:** You're on `fix/fullscreen-color-consistency` branch

**If you run Release.bat:**
1. ✅ Checks version.txt
2. ✅ Updates changelog (from commits since last release)
3. ✅ Updates website files locally
4. ✅ Builds installer
5. ❌ **Does NOT create GitHub Release** (removed from Release.bat)
6. ✅ Files ready to commit

**Then when you run PR script:**
1. Detects version change
2. Commits website/changelog updates
3. Merges to main
4. **After merge:** Creates GitHub Release
5. **After merge:** Website deploys

## Summary

- **Release.bat** = Build + prepare files (local only)
- **PR script** = Merge + create release + deploy
- **Cloudflare** = Auto-deploys on push to main
- **Download link** = Works after deployment completes

This matches your expectation! 🎯
