"""Keeps docs/specs and tests in lock-step (see docs/specs/README.md).

A requirement is a table row ``| XX-n | ... |`` in a SPEC-*.md file; a row marked ``(retired`` needs no test. It is covered when its ID
appears in a ``tests/test_spec_*.py`` file. This test fails when a requirement has no test, when
a test cites an ID the specs do not define, or when a spec is not listed in the README index.
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPECS = sorted((ROOT / "docs" / "specs").glob("SPEC-*.md"))
TESTS = sorted((ROOT / "tests").glob("test_spec_*.py"))
ROW = re.compile(r"^\|\s*([A-Z]{2,4}-\d+)\s*\|(.*)$", re.MULTILINE)


def _defined():
    ids = {}
    for spec in SPECS:
        for found, rest in ROW.findall(spec.read_text(encoding="utf-8")):
            assert found not in ids, f"{found} defined twice ({ids[found]} and {spec.name})"
            ids[found] = None if "(retired" in rest else spec.name
    return ids


def test_specs_exist():
    assert SPECS, "docs/specs must contain at least one SPEC-*.md"
    assert (ROOT / "docs" / "specs" / "README.md").exists()
    assert (ROOT / "docs" / "specs" / "ARCHITECTURE.md").exists()


def test_every_requirement_has_a_test():
    defined = _defined()
    text = "\n".join(path.read_text(encoding="utf-8") for path in TESTS if path.name != Path(__file__).name)
    missing = sorted(i for i, where in defined.items() if where and not re.search(rf"\b{re.escape(i)}\b", text))
    assert not missing, f"requirements without a test: {missing}"


def test_tests_only_cite_defined_requirements():
    defined = _defined()
    prefixes = {i.split("-")[0] for i in defined}
    pattern = re.compile(rf"\b(?:{'|'.join(sorted(prefixes))})-\d+\b")
    cited = set()
    for path in TESTS:
        if path.name != Path(__file__).name:
            cited |= set(pattern.findall(path.read_text(encoding="utf-8")))
    retired = sorted(i for i in cited if i in defined and defined[i] is None)
    assert not retired, f"tests cite retired requirements: {retired}"
    unknown = sorted(cited - set(defined))
    assert not unknown, f"tests cite requirements that no spec defines: {unknown}"


def test_every_spec_is_indexed_in_the_readme():
    readme = (ROOT / "docs" / "specs" / "README.md").read_text(encoding="utf-8")
    unlisted = [spec.name for spec in SPECS if spec.name not in readme]
    assert not unlisted, f"specs missing from docs/specs/README.md index: {unlisted}"
