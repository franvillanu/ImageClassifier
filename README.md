# 📸 Image Classifier

A desktop app for organizing photos and choosing favorites. Pick a folder, mark favorites ⭐ and compare candidates, then export or delete in bulk. Built with Python and PyQt6.

**Website:** [imageclassifier.neocities.org](https://imageclassifier.neocities.org/)

---

## ✨ Features

- **One-click favorites** – Mark best shots with a single tap
- **Compare set** – Separate “to compare” list alongside favorites
- **Smart filtering** – View All, Favorites, Compare, or Non-favorites
- **On-the-fly adjustments** – Brightness, rotation, zoom, crop, sharpness
- **Bulk export** – Export all favorites to a folder
- **Optional bulk delete** – Move non-favorites to recycle bin
- **Themes** – Black, Inkstone, Dark grey
- **Localized** – English and Spanish (EN/ES)
- **Keyboard shortcuts** – Full shortcut set; help dialog in-app

---

## 🛠 Development setup

### Requirements

- Python 3.10+
- Windows (Shell integration and installer are Windows-specific)

### Install dependencies

```bash
cd ImageClassifier
pip install -r requirements.txt
```

### Run the app

From the project root:

```bash
python run.py
```

Or:

```bash
python image-classifier.py
```

Or:

```bash
python -m image_classifier
```

### Run tests

```bash
pip install pytest
pytest tests/ -v
```

---

## 📁 Project layout

```
ImageClassifier/
├── image-classifier.py   # Main application (UI + PhotoViewer)
├── run.py                # Run the app (python run.py)
├── requirements.txt      # Dependencies
├── pyproject.toml        # Version & metadata
├── README.md             # This file
├── version.txt           # Version for EXE + installer
├── star.ico              # App icon
├── image_classifier/     # Package
│   ├── config.py         # Config path & defaults
│   ├── shell_win.py      # Windows Shell (open in Explorer)
│   ├── i18n/
│   │   └── translations.py   # EN/ES UI strings
│   ├── imaging/
│   │   ├── sharpen.py    # LAB unsharp (OpenCV)
│   │   └── loader.py     # Async image load + LRU cache
│   └── workers/
│       ├── export_worker.py
│       ├── delete_worker.py
│       └── sharpen_thread.py
├── tests/                # pytest
│   ├── test_config.py
│   ├── test_i18n.py
│   └── test_imaging.py
├── docs/
│   ├── BUILD.md          # How to build the EXE and installer
│   └── changelog.html    # Release notes (e.g. for website)
├── build-and-sign.bat    # Build signed EXE → installer/
├── Release.bat           # Full release: EXE + Inno Setup + sign
├── Image_Classifier.iss  # Inno Setup script
├── installer/            # Inputs for installer (README.txt + built EXE/cer)
├── ARCHITECTURE_REVIEW.md # Architecture and next steps
```

**Localization:** Edit `image_classifier/i18n/translations.py`. One dict per language (`"en"`, `"es"`); add a language by adding a key with the same keys as `"en"` and translated strings.

---

## 📦 Building the installer (Windows)

See **[docs/BUILD.md](docs/BUILD.md)** for prerequisites, steps, and where to put the signing cert. Summary: run `build-and-sign.bat` (produces `installer\Image Classifier.exe`), copy your `.cer` into `installer\`, then run `Release.bat` to create the signed setup in `Output\`.

---

## 🌐 Website & GitHub/Cloudflare Setup

The website files are in `docs/` (index.html, changelog.html). The release process automatically updates these files.

### GitHub Repository Setup

1. **Create the repository on GitHub:**
   ```bash
   # On GitHub, create a new repository named "ImageClassifier"
   # Then locally:
   git init
   git add .
   git commit -m "Initial commit"
   git branch -M main
   git remote add origin https://github.com/YOUR_USERNAME/ImageClassifier.git
   git push -u origin main
   ```

2. **The repository includes:**
   - Source code (`image_classifier/`, `image-classifier.py`, etc.)
   - Website files (`docs/index.html`, `docs/changelog.html`)
   - Build scripts (`Release.bat`, `build-and-sign.bat`)
   - GitHub Actions workflow (`.github/workflows/deploy-cloudflare.yml`)

### Cloudflare Pages Setup

1. **Get Cloudflare API credentials:**
   - Go to Cloudflare Dashboard → My Profile → API Tokens
   - Create a token with "Cloudflare Pages:Edit" permissions
   - Get your Account ID from the dashboard URL

2. **Add GitHub Secrets:**
   - Go to your GitHub repo → Settings → Secrets and variables → Actions
   - Add these secrets:
     - `CLOUDFLARE_API_TOKEN` - Your API token
     - `CLOUDFLARE_ACCOUNT_ID` - Your account ID

3. **Create Cloudflare Pages project:**
   - Go to Cloudflare Dashboard → Pages → Create a project
   - Connect your GitHub repository
   - Build settings:
     - **Framework preset:** None
     - **Build command:** (leave empty)
     - **Build output directory:** `docs`
     - **Root directory:** `/` (root)

4. **Deploy:**
   - The GitHub Actions workflow will automatically deploy on push to `main`
   - Or deploy manually: GitHub repo → Actions → "Deploy to Cloudflare Pages" → Run workflow

### Website Update Process

When you run `Release.bat`:
1. It prompts to update `changelog.html` (optional)
2. If updated, it automatically runs `update_website.py` to sync `index.html` with the latest version
3. After release, **create a branch** and commit website changes:
   ```bash
   git checkout -b release/v2.0
   git add docs/
   git commit -m "release: v2.0"
   git push -u origin release/v2.0
   ```
4. Create a Pull Request on GitHub to merge to `main`
5. After merging, Cloudflare Pages will automatically deploy the updated website

---

## 🔀 Git Workflow Protocol

**IMPORTANT:** This repository follows strict git protocols. **Never commit directly to `main`.**

### The Rule

1. **Always create a branch** before making changes:
   ```bash
   git checkout -b fix/description
   # or feature/, refactor/, docs/, chore/, release/
   ```

2. **Commit and push** all changes to your branch:
   ```bash
   git add .
   git commit -m "type: description"
   git push -u origin fix/description
   ```

3. **Create a Pull Request** on GitHub to merge to `main`

See **[docs/guides/GIT-PROTOCOL.md](docs/guides/GIT-PROTOCOL.md)** for the complete protocol.

**AI Assistants:** See `.cursor/rules/git-branch-gate.mdc` and `.cursor/rules/git-commit-push-gate.mdc` for mandatory rules.

---

## 📄 License and credits

© 2025 Francisco Villanueva. All rights reserved.

Inspired by the original concept from Martín Duhalde.
