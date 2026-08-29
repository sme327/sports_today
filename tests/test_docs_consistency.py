"""Documentation facts that rot silently.

A wrong number in a doc is worse than no number: it reads as verified. `TESTING.md`
opens with a test count that is maintained by hand, and by 2026-08-29 it had drifted 83
behind — it claimed 663 against an actual 746, having missed every suite added that week.
Nothing failed, because nothing was checking.

Same shape as the publish hang that started this: the failure produced no signal, so it
survived until someone happened to look. The fix is the same too — make the machine
notice.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TESTING_DOC = PROJECT_ROOT / "docs/engineering/TESTING.md"
_COUNT_RE = re.compile(r"##\s*Test suites\s*\((\d[\d,]*)\s*tests passing\)")


def documented_test_count() -> int:
    found = _COUNT_RE.search(TESTING_DOC.read_text(encoding="utf-8"))
    assert found, f"{TESTING_DOC.name} no longer states a test count in its heading"
    return int(found.group(1).replace(",", ""))


def _is_whole_suite(config) -> bool:
    """Only a full, unfiltered run knows the real total.

    A subset run collects fewer tests by design, and failing on that would train everyone
    to ignore this check — which is exactly how the number drifted in the first place.
    """
    # Deliberately not `config.rootpath`: with no pytest ini file in the project,
    # pytest resolves the rootdir to a common ancestor (`/Users/sme` here), which no
    # target can ever equal — so this check silently skipped on every full run. The
    # project root is the directory this test file lives under, which cannot drift.
    targets = [Path(str(arg).split("::")[0]).resolve() for arg in config.args]
    if targets and not all(t == PROJECT_ROOT for t in targets):
        return False
    option = config.option
    return not any((getattr(option, "keyword", ""), getattr(option, "markexpr", ""),
                    getattr(option, "last_failed", False),
                    getattr(option, "failedfirst", False)))


def test_the_documented_test_count_is_the_real_one(request):
    """TESTING.md's headline count must match what the suite actually collects.

    If this fails you have added or removed tests: update the number in
    `docs/engineering/TESTING.md`, and add a row for the new suite while you are there.
    """
    if not _is_whole_suite(request.config):
        pytest.skip("count is only meaningful for a full, unfiltered run")

    actual = request.session.testscollected
    documented = documented_test_count()
    assert documented == actual, (
        f"docs/engineering/TESTING.md says {documented:,} tests, the suite collects "
        f"{actual:,}. Update the '## Test suites ({actual} tests passing)' heading — "
        f"and if you added a suite, give it a row in the table below it."
    )


def test_every_test_file_has_a_row_in_the_table():
    """The count catches size; this catches shape. A new suite that nobody documents is
    a suite nobody knows to read — three were missing when this was written."""
    tests_dir = PROJECT_ROOT / "tests"
    web_tests = PROJECT_ROOT / "web/tests"
    doc = TESTING_DOC.read_text(encoding="utf-8")

    undocumented = sorted(
        path.name
        for directory in (tests_dir, web_tests)
        if directory.is_dir()
        for path in directory.glob("test_*.py")
        if path.name not in doc
    )
    assert not undocumented, (
        "test suites missing from docs/engineering/TESTING.md: "
        + ", ".join(undocumented)
    )
