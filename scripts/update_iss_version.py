#!/usr/bin/env python3
"""
Sync MyAppVersion in Image_Classifier.iss from version.txt (filevers=) so the
installer output filename uses the full version (e.g. ImageClassifierSetup_v1.9.0.4.exe).
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
    ver_str = ".".join(m.groups())

    iss_text = ISS_FILE.read_text(encoding="utf-8")
    # Replace #define MyAppVersion "..." with full version (handles #ifndef block or single line)
    new_text = re.sub(
        r'#define\s+MyAppVersion\s+"[^"]*"',
        f'#define MyAppVersion "{ver_str}"',
        iss_text,
        count=1,
    )
    if new_text == iss_text:
        print("[ERROR] Could not find MyAppVersion in Image_Classifier.iss", file=sys.stderr)
        return 1
    ISS_FILE.write_text(new_text, encoding="utf-8")
    print(f"[INFO] Image_Classifier.iss MyAppVersion -> {ver_str}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
