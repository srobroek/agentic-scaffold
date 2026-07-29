"""The prose gate wrapper fails loudly.

Written after a shell version of this wrapper used `mapfile`, which bash 3.2 on
macOS does not have. It printed errors and exited 0, so `just check` reported ok
against docs that had never been linted. Rewriting it in Python removed the shell
portability question; these tests keep the exit-code contract.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "scripts" / "lint_prose.py"
GATE = Path.home() / ".claude" / "skills" / "review-docs" / "scripts" / "slop-lint.sh"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(WRAPPER), *args],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def test_generated_files_are_not_linted() -> None:
    """docs/INDEX.md is generated, so gate findings against it are not actionable."""
    result = run("docs/INDEX.md")
    assert result.returncode == 0
    assert "INDEX.md" not in result.stdout


def test_wrapper_runs_clean_and_prints_nothing_on_stderr() -> None:
    result = run()
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stderr.strip() == "", f"unexpected stderr: {result.stderr}"


@pytest.mark.skipif(not GATE.is_file(), reason="prose gate not installed")
def test_wrapper_fails_when_a_doc_violates_the_gate(tmp_path: Path) -> None:
    target = REPO_ROOT / "docs" / "agents" / "testing" / "index.md"
    backup = tmp_path / "backup.md"
    shutil.copy2(target, backup)
    try:
        target.write_text(target.read_text() + "\n\nThis is currently a WIP feature.\n")
        result = run()
        assert result.returncode == 1
        assert "StatusLanguage" in result.stdout + result.stderr
    finally:
        shutil.copy2(backup, target)
