"""The integration case files themselves, checked in the fast suite.

`just integration` renders and builds each case, which takes minutes and is deliberately out of
`just check`. That leaves the case files unguarded: a typo in a layer name or a case that
duplicates a profile would only surface when someone remembered to run the slow suite.

These tests read the files and never render, so they cost milliseconds and run in the gate.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES = REPO_ROOT / "tests-integration" / "cases"
RUNNER = REPO_ROOT / "tests-integration" / "run.py"
TEMPLATES = REPO_ROOT / "templates"
PROFILES = REPO_ROOT / "profiles"

REQUIRED = ("name", "summary", "gap", "layers", "build")


def case_paths() -> list[Path]:
    return sorted(CASES.glob("*.yml"))


def ids(paths: list[Path]) -> list[str]:
    return [path.stem for path in paths]


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def test_there_is_at_least_one_case() -> None:
    """An empty directory would make every test below pass vacuously."""
    assert case_paths(), "no cases under tests-integration/cases"


@pytest.mark.parametrize("path", case_paths(), ids=ids(case_paths()))
def test_a_case_carries_every_required_key(path: Path) -> None:
    case = load(path)
    missing = [key for key in REQUIRED if key not in case]
    assert not missing, f"missing {', '.join(missing)}"
    assert case["name"] == path.stem, f"names itself {case['name']!r}"


@pytest.mark.parametrize("path", case_paths(), ids=ids(case_paths()))
def test_every_layer_a_case_names_exists(path: Path) -> None:
    """A typo here fails partway through a render that already took a minute."""
    for layer in load(path)["layers"]:
        assert (TEMPLATES / layer / "copier.yml").is_file(), f"no such layer: {layer}"


@pytest.mark.parametrize("path", case_paths(), ids=ids(case_paths()))
def test_a_case_states_the_gap_it_covers(path: Path) -> None:
    """A case that duplicates a profile or a unit test costs minutes and proves nothing, so it
    has to say what is not already covered. Prose, deliberately: the judgement is the point and
    a keyword would be gamed."""
    gap = load(path)["gap"]
    assert len(gap.split()) >= 20, "the gap has to say what is not already covered"


@pytest.mark.parametrize("path", case_paths(), ids=ids(case_paths()))
def test_a_case_builds_something(path: Path) -> None:
    """A case that renders and asserts only paths is a unit test that took minutes. The point of
    the suite is putting a real tool in front of a combination."""
    assert load(path)["build"], "no build commands"


@pytest.mark.parametrize("path", case_paths(), ids=ids(case_paths()))
def test_a_case_is_not_a_profile_in_disguise(path: Path) -> None:
    """An identical layer set is already covered by `just profiles-build`.

    Compared as a set rather than a sequence, because a case whose whole point is the ORDER is
    exactly what a profile cannot express: the validator refuses a bad order inside a profile.
    """
    layers = set(load(path)["layers"])
    for profile_path in sorted(PROFILES.glob("*.yml")):
        profile = yaml.safe_load(profile_path.read_text()) or {}
        assert layers != set(profile.get("layers") or []), (
            f"the same layer set as profiles/{profile_path.name}; "
            "`just profiles-build` covers that already"
        )


def test_the_runner_lists_every_case() -> None:
    """`--list` is how someone finds a case to run, so it has to agree with the directory."""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "--list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    listed = {line.split()[0] for line in result.stdout.splitlines() if line.strip()}
    assert listed == {path.stem for path in case_paths()}


def test_the_runner_refuses_an_unknown_case() -> None:
    """A mistyped name has to fail rather than silently run everything, which is what an empty
    selection does."""
    result = subprocess.run(
        [sys.executable, str(RUNNER), "no-such-case"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
    assert "no such case" in result.stderr
    # Names what is available, so the fix does not need a second command.
    assert "available:" in result.stderr


def test_the_suite_is_not_in_the_gate() -> None:
    """`just check` runs on every edit and has to stay in seconds. A case renders a whole tree
    and runs its build, so putting the suite in `check` would make the gate unusable and get it
    skipped -- which is worse than a slow suite nobody forgot to run."""
    justfile = (REPO_ROOT / "justfile").read_text()
    check = next(line for line in justfile.splitlines() if line.startswith("check:"))
    assert "integration" not in check.split()
    # But it has to be reachable, or it is dead code.
    assert "\nintegration " in justfile
