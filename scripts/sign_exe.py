#!/usr/bin/env python3
"""
Sign an EXE with the project PFX. Password from IMAGE_CLASSIFIER_PFX_PASSWORD
or installer/.pfx_password. Use this so passwords with ! or % are not corrupted by batch.
"""
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PASSWORD_FILE = REPO_ROOT / "installer" / ".pfx_password"
PFX = REPO_ROOT / "imageclassifier_cert.pfx"
WINDOWS_KITS_BIN = Path(r"C:\Program Files (x86)\Windows Kits\10\bin")


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


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: sign_exe.py <path-to-exe>", file=sys.stderr)
        return 1
    exe_path = Path(sys.argv[1])
    if not exe_path.is_absolute():
        exe_path = (Path.cwd() / exe_path).resolve()
    if not exe_path.exists():
        print(f"[ERROR] File not found: {exe_path}", file=sys.stderr)
        return 1

    password = os.environ.get("IMAGE_CLASSIFIER_PFX_PASSWORD")
    if password and "^!" in password:
        password = password.replace("^!", "!")
    if not password and PASSWORD_FILE.exists():
        password = PASSWORD_FILE.read_text(encoding="utf-8").strip()
    if not password:
        print("[ERROR] PFX password required (env or installer/.pfx_password)", file=sys.stderr)
        return 1

    if not PFX.exists():
        print(f"[ERROR] PFX not found: {PFX}", file=sys.stderr)
        return 1
    signtool = _find_signtool()
    if not signtool:
        print("[ERROR] signtool.exe not found (Windows SDK)", file=sys.stderr)
        return 1

    r = subprocess.run(
        [
            str(signtool),
            "sign",
            "/a",
            "/fd", "SHA256",
            "/f", str(PFX),
            "/p", password,
            "/tr", "http://timestamp.digicert.com",
            "/td", "SHA256",
            str(exe_path),
        ],
    )
    return r.returncode


if __name__ == "__main__":
    sys.exit(main())
