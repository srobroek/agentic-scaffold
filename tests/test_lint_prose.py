"""The prose gate wrapper fails loudly.

Written after a shell version of this wrapper used `mapfile`, which bash 3.2 on macOS does not
have. It printed errors and exited 0, so `just check` reported ok against docs that had never
been linted. Rewriting it in Python removed the shell portability question; these tests keep the
exit-code contract.

The gate itself moved. It called `~/.claude/skills/review-docs/scripts/slop-lint.sh` until that
script stopped existing: slopvac ba2f21e replaced the shell gate with a CLI. The installed skill
was stale, and its two Vale configs shared one `StylesPath` while asking for different packages,
so `vale sync` deleted a style the other needed and `just lint` failed at random. Calling the
linter directly removed the shared directory, so there is nothing left to desync.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "scripts" / "lint_prose.py"
CONFIG = REPO_ROOT / "slopvac.toml"
# The linter is not part of this repository, and is not on PyPI yet, so it is usually absent: the
# wrapper says so and exits 0. A test asserting a finding would then fail for the wrapper working
# correctly. There is no checkout fallback to fall back to -- see the wrapper's docstring.
needs_linter = pytest.mark.skipif(
    shutil.which("slopvac") is None, reason="slopvac is not installed"
)


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WRAPPER), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def test_generated_files_are_not_linted() -> None:
    """docs/INDEX.md is generated, so findings against it are not actionable: the fix would have
    to be made in a generator that has no prose to fix."""
    result = run("docs/INDEX.md")
    assert result.returncode == 0
    assert "INDEX.md" not in result.stdout


def test_the_wrapper_passes_no_profile_flag() -> None:
    """The profile and every override live in the committed config. A `--profile` on the command
    line outranks the file, so passing one would make the config decorative."""
    # The argv the wrapper builds, not its prose: the docstring explains the choice and says
    # `--profile` while doing so.
    body = WRAPPER.read_text()
    argv_lines = [line for line in body.splitlines() if "command," in line or "*files" in line]
    assert argv_lines, "could not find where the wrapper builds its argv"
    assert not any("--profile" in line for line in argv_lines)


def test_the_wrapper_has_no_checkout_fallback() -> None:
    """It had one while slopvac was unpublished, and it is gone deliberately.

    A gate that builds a developer's working copy checks whatever that copy happens to say, and
    two machines then enforce different rules. Absent is honest: the wrapper reports it and exits
    0, so the gate is off rather than arbitrary.
    """
    # Code, not prose: the docstrings say `--from` while explaining why it is gone.
    body = WRAPPER.read_text()
    code = [
        line
        for line in body.splitlines()
        if not line.lstrip().startswith("#") and '"' not in line.split("#")[0][:8]
    ]
    returns = [line for line in code if "return [" in line]
    assert returns, "could not find the argv the wrapper returns"
    assert not any("--from" in line for line in returns)


# --- the committed config --------------------------------------------------


def test_the_config_is_committed_and_parses() -> None:
    assert CONFIG.is_file()
    tomllib.loads(CONFIG.read_text())


def test_the_profile_is_normal_with_ste_demoted() -> None:
    """`relaxed` was the first choice and it was too weak: appending "This is currently a WIP
    feature that will leverage a robust solution" to a document still PASSED.

    `normal` catches that. What made `normal` unreachable was Simplified Technical English --
    measured on docs/layers.md, 241 of its 355 findings came from the eight ste-* categories --
    so those are advisory and the slop rules keep their severity. STE is written for aircraft
    maintenance procedures, and adopting it would be a decision about how this repository writes
    rather than a linter setting.
    """
    config = tomllib.loads(CONFIG.read_text())
    assert config["profile"] == "normal"

    demoted = {
        name for name, body in config["categories"].items() if body.get("severity") == "suggestion"
    }
    assert demoted == {
        "ste-descriptive",
        "ste-nouns",
        "ste-practices",
        "ste-procedural",
        "ste-punctuation",
        "ste-sentences",
        "ste-verbs",
        "ste-words",
    }, "the demotion has to be exactly the STE categories"

    # The gate is errors. Demoting a category below error would make it decorative.
    assert config["thresholds"]["max_errors"] == 0


def test_the_score_floor_is_lifted_only_for_the_steering_indexes() -> None:
    """A `docs/agents/**` file is short and mostly generated: a table of paths, a marked block,
    and two sentences of rule. The score floor is a density measure, so eight suggestions in a
    57-word file reads as 14 findings per 100 words and fails on arithmetic.

    Scoped, because lifting the floor everywhere would drop it for docs/layers.md too, where it
    is doing real work.
    """
    config = tomllib.loads(CONFIG.read_text())
    overrides = config["overrides"]
    assert len(overrides) == 1, "one override; a second needs its own reason"

    override = overrides[0]
    assert override["files"] == ["docs/agents/**/*.md"]
    assert override["thresholds"]["min_score"] == 0
    # Errors still gate them.
    assert override["thresholds"]["max_errors"] == 0


# --- the contract ----------------------------------------------------------


@needs_linter
def test_the_wrapper_runs_clean_and_prints_nothing_on_stderr() -> None:
    """Clean means clean: a warning on stderr from a passing run is noise that trains people to
    ignore the gate."""
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr.strip() == "", f"unexpected stderr: {result.stderr}"


@needs_linter
def test_the_wrapper_fails_on_slop(tmp_path: Path) -> None:
    """The sentence `relaxed` let through. This is the assertion that decided the profile."""
    target = REPO_ROOT / "docs" / "agents" / "testing" / "index.md"
    backup = tmp_path / "backup.md"
    shutil.copy2(target, backup)
    try:
        target.write_text(
            target.read_text()
            + "\n\nThis is currently a WIP feature that will leverage a robust solution.\n"
        )
        result = run()
        assert result.returncode == 1, "slop has to fail the gate"
        assert "error" in (result.stdout + result.stderr).lower()
    finally:
        shutil.copy2(backup, target)
