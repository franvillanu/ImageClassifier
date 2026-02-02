#!/usr/bin/env python3
"""
Sync MyAppVersion in Image_Classifier.iss from version.txt (filevers=) so the
installer output filename uses the 3-digit version (e.g. ImageClassifierSetup_v2.0.1.exe).
Run before ISCC in Release.bat.
"""
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
VERSION_TXT = REPO_ROOT / "version.txt"
ISS_FILE = REPO_ROOT / "Image_Classifier.iss"


def main() -> int:
    text = VERSION_TXT.read_text(encoding="utf-8")
    m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", text)
    if not m:
        print("[ERROR] Could not parse filevers from version.txt", file=sys.stderr)
        return 1
    # 3-digit version: major.minor.build (revision ignored for display)
    major, minor, build, _rev = m.groups()
    ver_str = f"{major}.{minor}.{build}"

    iss_text = ISS_FILE.read_text(encoding="utf-8")
    # Replace the version string in MyAppVersion definition
    # This handles both standalone #define and #define inside #ifndef block
    # Match: MyAppVersion followed by any whitespace and quoted version string
    pattern = r'(MyAppVersion\s+")([^"]+)(")'
    match = re.search(pattern, iss_text)
    
    if not match:
        print("[ERROR] Could not find MyAppVersion in Image_Classifier.iss", file=sys.stderr)
        return 1
    
    # Replace just the version number, preserving the structure
    new_text = re.sub(
        pattern,
        lambda m: f'{m.group(1)}{ver_str}{m.group(3)}',
        iss_text,
        count=1,
    )
    ISS_FILE.write_text(new_text, encoding="utf-8")
    print(f"[INFO] Image_Classifier.iss MyAppVersion -> {ver_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
