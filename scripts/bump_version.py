#!/usr/bin/env python3
"""
Bump or set version for Image Classifier.
Updates version.txt (PyInstaller resource) and pyproject.toml.

Usage:
  py scripts/bump_version.py              # bump patch (1.9.0 -> 1.9.1)
  py scripts/bump_version.py patch        # same
  py scripts/bump_version.py minor        # 1.9.0 -> 1.10.0
  py scripts/bump_version.py major        # 1.9.0 -> 2.0.0
  py scripts/bump_version.py 2.0.0       # set explicit version
"""
import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_version_from_version_txt(path: Path) -> tuple[int, int, int, int]:
    """Read version.txt and return (major, minor, build, rev) from filevers=."""
    text = path.read_text(encoding="utf-8")
    m = re.search(r"filevers=\((\d+),\s*(\d+),\s*(\d+),\s*(\d+)\)", text)
    if not m:
        raise SystemExit("Could not parse filevers from version.txt")
    return tuple(int(x) for x in m.groups())


def bump(major: int, minor: int, build: int, rev: int, kind: str) -> tuple[int, int, int, int]:
    if kind == "patch":
        return (major, minor, build, rev + 1)
    if kind == "minor":
        return (major, minor + 1, 0, 0)
    if kind == "major":
        return (major + 1, 0, 0, 0)
    raise ValueError(f"Unknown bump kind: {kind}")


def set_version_from_string(ver_str: str) -> tuple[int, int, int, int]:
    """Parse 'M.m.b.r' or 'M.m' into (M, m, b, r); missing parts are 0."""
    parts = ver_str.strip().split(".")
    if len(parts) < 2:
        raise ValueError("Version must be at least M.m (e.g. 1.9 or 1.9.1)")
    major = int(parts[0])
    minor = int(parts[1])
    build = int(parts[2]) if len(parts) > 2 else 0
    rev = int(parts[3]) if len(parts) > 3 else 0
    return (major, minor, build, rev)


def update_version_txt(path: Path, old_tuple: tuple[int, int, int, int], new_tuple: tuple[int, int, int, int]) -> None:
    old_str = ".".join(map(str, old_tuple))
    new_str = ".".join(map(str, new_tuple))
    old_py = f"({old_tuple[0]}, {old_tuple[1]}, {old_tuple[2]}, {old_tuple[3]})"
    new_py = f"({new_tuple[0]}, {new_tuple[1]}, {new_tuple[2]}, {new_tuple[3]})"

    text = path.read_text(encoding="utf-8")
    text = text.replace(old_py, new_py)
    text = text.replace(f"'{old_str}'", f"'{new_str}'")
    path.write_text(text, encoding="utf-8")


def update_pyproject(path: Path, new_short: str) -> None:
    """Update version = "x.y" in pyproject.toml."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'version\s*=\s*"[^"]+"', f'version = "{new_short}"', text, count=1)
    path.write_text(text, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Bump or set Image Classifier version")
    parser.add_argument(
        "version_or_bump",
        nargs="?",
        default="patch",
        help="patch | minor | major | or explicit version (e.g. 1.10.0)",
    )
    args = parser.parse_args()

    version_txt = REPO_ROOT / "version.txt"
    pyproject = REPO_ROOT / "pyproject.toml"

    old_ver = parse_version_from_version_txt(version_txt)
    arg = args.version_or_bump.strip().lower()

    if arg in ("patch", "minor", "major"):
        new_ver = bump(*old_ver, arg)
    elif re.match(r"^\d+(\.\d+){1,3}$", arg):
        new_ver = set_version_from_string(arg)
    else:
        print("Usage: bump_version.py [patch|minor|major|M.m.b.r]", file=sys.stderr)
        sys.exit(1)

    new_str = ".".join(map(str, new_ver))
    new_short = f"{new_ver[0]}.{new_ver[1]}"

    update_version_txt(version_txt, old_ver, new_ver)
    if pyproject.exists():
        update_pyproject(pyproject, new_short)

    print(f"Version: {'.'.join(map(str, old_ver))} -> {new_str}")
    print(f"Updated: version.txt, pyproject.toml (if present)")


if __name__ == "__main__":
    main()
