#!/usr/bin/env python3
"""
One-command release: read PFX password from a local file, then run full release
(build + sign EXE + Inno Setup + sign installer). Optional: bump version first.

Setup once: create installer/.pfx_password with one line = your PFX password.
  (This file is gitignored; never commit it.)

Then: double-click Release.bat (or run "py scripts/release.py").
  Optionally pass patch/minor/major/1.10.0 or nobump to bump (or not) before building.
"""
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PASSWORD_FILE = REPO_ROOT / "installer" / ".pfx_password"
BUILD_AND_SIGN_BAT = REPO_ROOT / "build-and-sign.bat"
BUMP_SCRIPT = REPO_ROOT / "scripts" / "bump_version.py"
ISS_FILE = REPO_ROOT / "Image_Classifier.iss"
OUTPUT_DIR = REPO_ROOT / "Output"
WINDOWS_KITS_BIN = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")
INNO_SETUP_PATHS = [
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
]


def _find_signtool() -> Path | None:
    if not WINDOWS_KITS_BIN.exists():
        return None
    versions = sorted(
        (p for p in WINDOWS_KITS_BIN.iterdir() if p.is_dir()),
        key=lambda p: p.name,
        reverse=True,
    )
    for ver in versions:
        exe = ver / "x64" / "signtool.exe"
        if exe.exists():
            return exe
    return None


def _find_iscc() -> Path | None:
    for p in INNO_SETUP_PATHS:
        if p.exists():
            return p
    iscc = shutil.which("ISCC.exe") or shutil.which("iscc")
    return Path(iscc) if iscc else None


def main() -> int:
    # 1) Get password: env var or file
    password = os.environ.get("IMAGE_CLASSIFIER_PFX_PASSWORD")
    if not password and PASSWORD_FILE.exists():
        password = PASSWORD_FILE.read_text(encoding="utf-8").strip()
    if not password:
        print(
            "[ERROR] PFX password required for signing.\n"
            "  Create installer\\.pfx_password with one line = your password (gitignored).\n"
            "  Or set IMAGE_CLASSIFIER_PFX_PASSWORD in your environment.",
            file=sys.stderr,
        )
        return 1

    os.environ["IMAGE_CLASSIFIER_PFX_PASSWORD"] = password
    os.environ["IMAGE_CLASSIFIER_PYTHON"] = sys.executable

    # Require PyInstaller for the Python we're using (build-and-sign.bat uses it)
    r = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--help"],
        cwd=str(REPO_ROOT),
        capture_output=True,
    )
    if r.returncode != 0:
        print(
            "[ERROR] PyInstaller is not installed for this Python.\n"
            f"  Python: {sys.executable}\n"
            "  Install it with:  py -m pip install pyinstaller",
            file=sys.stderr,
        )
        return 1

    # 2) Optional version bump: patch | minor | major | 1.10.0
    if len(sys.argv) > 1:
        bump_arg = sys.argv[1].strip().lower()
        if bump_arg not in ("nobump", ""):
            print("\n[0/4] Bumping version:", bump_arg)
            r = subprocess.run(
                [sys.executable, str(BUMP_SCRIPT), bump_arg],
                cwd=str(REPO_ROOT),
                env=os.environ,
            )
            if r.returncode != 0:
                return r.returncode

    # 3) Build and sign EXE
    if not BUILD_AND_SIGN_BAT.exists():
        print("[ERROR] build-and-sign.bat not found.", file=sys.stderr)
        return 1
    print("\n[1/4] Building and signing EXE...")
    r = subprocess.run(
        [str(BUILD_AND_SIGN_BAT)],
        cwd=str(REPO_ROOT),
        shell=True,
        env=os.environ,
    )
    if r.returncode != 0:
        return r.returncode

    # 4) Compile Inno Setup installer
    iscc = _find_iscc()
    if not iscc:
        print("[ERROR] Inno Setup 6 (ISCC.exe) not found.", file=sys.stderr)
        return 1
    if not ISS_FILE.exists():
        print("[ERROR] Image_Classifier.iss not found.", file=sys.stderr)
        return 1
    print("\n[2/4] Compiling installer (Inno Setup)...")
    r = subprocess.run(
        [str(iscc), str(ISS_FILE)],
        cwd=str(REPO_ROOT),
        env=os.environ,
    )
    if r.returncode != 0:
        return r.returncode

    # 5) Sign the setup EXE
    signtool = _find_signtool()
    if not signtool:
        print("[ERROR] signtool.exe not found (Windows SDK).", file=sys.stderr)
        return 1
    pfx = REPO_ROOT / "imageclassifier_cert.pfx"
    if not pfx.exists():
        print("[ERROR] imageclassifier_cert.pfx not found.", file=sys.stderr)
        return 1
    setups = list(OUTPUT_DIR.glob("ImageClassifierSetup_v*.exe"))
    if not setups:
        print("[ERROR] No ImageClassifierSetup_v*.exe in Output.", file=sys.stderr)
        return 1
    setup_exe = max(setups, key=lambda p: p.stat().st_mtime)
    print("\n[3/4] Signing installer:", setup_exe.name)
    r = subprocess.run(
        [
            str(signtool),
            "sign",
            "/a",
            "/fd", "SHA256",
            "/f", str(pfx),
            "/p", password,
            "/tr", "http://timestamp.digicert.com",
            "/td", "SHA256",
            str(setup_exe),
        ],
        cwd=str(REPO_ROOT),
    )
    if r.returncode != 0:
        return r.returncode
    print("\n[4/4] Release complete. Output:", setup_exe)
    return 0


if __name__ == "__main__":
    sys.exit(main())
