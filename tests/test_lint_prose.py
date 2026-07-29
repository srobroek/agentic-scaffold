"""The prose gate wrapper runs on the shell this machine has, and it fails loudly.

Written after `mapfile` made the wrapper exit 0 on macOS while printing errors,
so `just check` reported ok against docs that had never been linted.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
WRAPPER = REPO_ROOT / "scripts" / "lint-prose.sh"
GATE = Path.home() / ".claude" / "skills" / "review-docs" / "scripts" / "slop-lint.sh"


def run() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(WRAPPER)],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )


def test_wrapper_uses_no_bash_4_builtins() -> None:
    """macOS ships bash 3.2, where `mapfile` and `readarray` do not exist."""
    code = [
        line
        for line in WRAPPER.read_text().splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for builtin in ("mapfile", "readarray", "declare -A"):
        offenders = [line for line in code if builtin in line]
        assert not offenders, f"{builtin} needs bash 4: {offenders}"


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
