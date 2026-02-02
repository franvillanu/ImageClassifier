# Release Protocol

This document outlines the complete checklist for releasing a new version of Image Classifier.

## Version Update Checklist

When releasing a new version, you **MUST** update the version number in ALL of the following locations:

### 1. Core Version Files
- ✅ `version.txt` - Update `filevers=(X, Y, Z, W)` and all `'X.Y.Z.W'` strings
- ✅ `pyproject.toml` - Update `version = "X.Y"`
- ✅ `package.json` - Update `"version": "X.Y.Z"` (if applicable)

### 2. Application Code
- ✅ `image_classifier/__init__.py` - Update `__version__ = "X.Y"`
- ✅ `image_classifier/i18n/translations.py` - Update **BOTH**:
  - English: `"app_version_label": "Image Classifier - Version X.Y"`
  - Spanish: `"app_version_label": "Clasificador de Imágenes - Versión X.Y"`

### 3. Installer & Build Files
- ✅ `Image_Classifier.iss` - Updated automatically by `scripts/update_iss_version.py` (runs during release)

### 4. Website Files
- ✅ `docs/index.html` - Updated automatically by `scripts/update_website.py` (runs during release)
- ✅ `docs/changelog.html` - Updated manually or via `scripts/update_changelog.py`

## Quick Version Bump

Use the automated script to bump version in most files:

```bash
py scripts/bump_version.py [patch|minor|major|X.Y.Z]
```

**However**, you **MUST manually update**:
- `image_classifier/i18n/translations.py` - Both English and Spanish `app_version_label` entries
- `image_classifier/__init__.py` - `__version__` string

## Release Process

1. **Update version** using `bump_version.py` or manually
2. **Manually update About dialog versions** in `translations.py` (English + Spanish)
3. **Update changelog** in `docs/changelog.html`
4. **Run release script**: `release.bat` or `release.bat patch/minor/major`
5. **Verify About dialog** shows correct version in the app

## Critical: About Dialog Version

⚠️ **DO NOT FORGET**: The About dialog version is displayed from `translations.py`:
- English: `"app_version_label": "Image Classifier - Version X.Y"`
- Spanish: `"app_version_label": "Clasificador de Imágenes - Versión X.Y"`

This is **NOT** automatically updated by `bump_version.py` and must be updated manually for every release.

## Testing Checklist

Before releasing, verify:
- [ ] About dialog shows correct version (English)
- [ ] About dialog shows correct version (Spanish - switch language)
- [ ] Version in `version.txt` matches About dialog
- [ ] Installer shows correct version
- [ ] Website shows correct version
