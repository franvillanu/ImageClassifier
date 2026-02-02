# GitHub Pull Request Settings

## Recommended: Require Squash and Merge

For this repository, we recommend setting **"Squash and merge"** as the default (or required) merge method. This keeps the `main` branch history clean and makes releases easier.

## Why Squash and Merge?

1. **Clean History**: Each PR becomes a single commit on `main`, making it easy to see what changed
2. **Easier Releases**: When you create a release, you can see exactly which PRs are included
3. **Better for Small Projects**: For a single-maintainer project like this, linear history is easier to manage
4. **Release Tags**: When you tag `v2.0`, you know exactly what's in that release

## How to Configure

### Option 1: GitHub Web UI (Recommended)

1. Go to your repository: https://github.com/franvillanu/ImageClassifier
2. Click **Settings** (top right)
3. Scroll down to **Pull Requests** section
4. Under **"Allow merge commits"**, you can:
   - **Uncheck "Allow merge commits"** (forces squash/rebase only)
   - **Uncheck "Allow rebase merging"** (forces squash only)
   - Or leave both checked but **prefer squash** (users can still choose)

5. Under **"Default to pull request title and description"**, check:
   - ✅ **"Default to pull request title and description"** (uses PR title as commit message)

### Option 2: GitHub CLI (if you have it)

```bash
gh api repos/franvillanu/ImageClassifier --method PATCH \
  -f allow_merge_commit=false \
  -f allow_rebase_merge=false \
  -f allow_squash_merge=true
```

## Current Workflow Impact

With squash and merge enabled:

1. **You create a branch**: `fix/description`
2. **You make commits**: Multiple commits on your branch (fine!)
3. **You create PR**: On GitHub
4. **You merge**: GitHub squashes all commits into one on `main`
5. **Result**: Clean, linear history on `main`

## Release Process

When you run `Release.bat`:

1. Creates `release/v2.0` branch
2. Builds installer
3. Updates website files
4. Commits changes
5. Creates PR
6. **When you merge the PR** (squash and merge):
   - All release changes become one commit: `"release: v2.0"`
   - Clean history
   - Easy to see what's in each release

## Best Practice

- **Keep both options enabled** but **prefer squash** for regular PRs
- **Use squash** for feature/fix PRs (most common)
- **Use merge commit** only if you specifically need to preserve branch history (rare)

## Verification

After setting this up, when you create a PR:
- The merge button will default to "Squash and merge"
- The commit message will use the PR title
- `main` will have a clean, linear history
