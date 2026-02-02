# Building Image Classifier (Windows)

How to build the signed EXE and the Inno Setup installer from this repo.

## One script to click (same as before)

1. **Edit version** – Open `version.txt` and change `filevers=(1, 9, 0, 0)` and the `'1.9.0.0'` strings to your new version (e.g. 1.10.0). Or run `py scripts/bump_version.py patch` to bump automatically.
2. **Password once** – Create `installer/.pfx_password` with one line = your PFX password (gitignored; never commit).
3. **Double-click `release.bat`** – That’s it. It builds the EXE, signs it, builds the installer, signs the installer.

Optional: from a command prompt you can pass a bump: `release.bat patch` or `release.bat 1.10.0` to bump version then build. Double-click with no args = use current version in `version.txt`.

When you run it, the script will:

1. **Build** the EXE with PyInstaller (from `image-classifier.py`)
2. **Sign** the EXE with your `.pfx`
3. **Build** the Inno Setup installer
4. **Sign** the installer EXE

(If you ran `release.bat patch` or similar, it bumps version in `version.txt` first.)

**Options:**

| Command | Effect |
|---------|--------|
| `release.bat patch` | Bump patch (1.9.0 → 1.9.1), then build + sign everything |
| `release.bat minor` | Bump minor (1.9.0 → 1.10.0), then build + sign |
| `release.bat major` | Bump major (1.9.0 → 2.0.0), then build + sign |
| `release.bat 2.0.0` | Set version to 2.0.0, then build + sign |
| `release.bat` or `release.bat nobump` | No version change; just build + sign (uses current `version.txt`) |

**Prerequisites:** Same as below (Python, PyInstaller, Inno Setup 6, Windows SDK, `.pfx` in repo root, `installer\imageclassifier_cert.cer`). Version bump only needs Python.

---

## Prerequisites

- **Python 3.10+** with dependencies: `pip install -r requirements.txt`
- **PyInstaller**: `pip install pyinstaller`
- **Inno Setup 6** (x64): [jrsoftware.org/isinfo.php](https://jrsoftware.org/isinfo.php)
- **Windows SDK** (for `signtool.exe`), or Visual Studio with “Windows SDK” workload
- **Signing certificate**: a `.pfx` file (e.g. from your cert backup). Do **not** commit `.pfx` or passwords to the repo.

## 1. Build and sign the EXE

From the repo root:

```batch
build-and-sign.bat
```

This script:

- Runs PyInstaller on `image-classifier.py` → produces `installer\Image Classifier.exe`
- Signs that EXE with `signtool` using your `.pfx`

**Required before running:**

- `imageclassifier_cert.pfx` in the repo root (or adjust the path in `build-and-sign.bat`)
- **PFX password:** set the environment variable `IMAGE_CLASSIFIER_PFX_PASSWORD` (never commit it). Example, in the same command window:
  ```batch
  set IMAGE_CLASSIFIER_PFX_PASSWORD=YourPasswordHere
  build-and-sign.bat
  ```
  Or set it once in System/User environment variables.

## 2. Prepare the installer inputs

Inno Setup expects these files under `installer\`:

| File | Source |
|------|--------|
| `Image Classifier.exe` | Output of `build-and-sign.bat` |
| `imageclassifier_cert.cer` | Export from your signing cert (public part only); copy into `installer\` |
| `README.txt` | User-facing readme; already in `installer\` |

So after step 1, copy your `.cer` (same cert as the `.pfx`) into `installer\imageclassifier_cert.cer`.

## 3. Build the installer

From the repo root:

```batch
Release.bat
```

This script:

- Runs `build-and-sign.bat` (build + sign EXE)
- Compiles `Image_Classifier.iss` with Inno Setup → `Output\ImageClassifierSetup_vX.X.exe`
- Signs the setup EXE with the same `.pfx`

Version is read from `version.txt` (e.g. `filevers=(1, 9, 0, 0)` → v1.9).

## Secrets (do not commit)

- **PFX file**: keep `imageclassifier_cert.pfx` only on your machine. It is listed in `.gitignore`.
- **PFX password**: the scripts require `IMAGE_CLASSIFIER_PFX_PASSWORD` to be set in the environment. They will not run with a hardcoded password. Set it in your session or in Windows environment variables; never commit it.

## Repo layout for building

```
ImageClassifier/
├── image-classifier.py      # App entry (PyInstaller target)
├── run.py                   # Dev run (optional)
├── version.txt              # Version for EXE + installer
├── star.ico                 # App + setup icon
├── release.bat              # One-command release (bump + build + sign)
├── build-and-sign.bat       # Build EXE → installer\ + sign
├── Release.bat              # Full release (build + Inno + sign setup)
├── Image_Classifier.iss    # Inno Setup script
├── scripts/
│   └── bump_version.py     # Bump/set version in version.txt + pyproject.toml
├── installer/
│   ├── README.txt           # Shipped with app (commit this)
│   ├── Image Classifier.exe # Created by build-and-sign.bat
│   └── imageclassifier_cert.cer  # You copy here (do not commit if sensitive)
└── Output/
    └── ImageClassifierSetup_v1.9.exe  # Final installer
```

`.gitignore` already excludes `installer/*.exe`, `installer/*.cer`, `Output/*.exe`, and `*.pfx`, so the repo stays clean and safe.
