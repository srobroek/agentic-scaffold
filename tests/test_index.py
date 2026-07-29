"""index.py is idempotent, and --check catches drift."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
INDEX_SCRIPT = REPO_ROOT / "scripts" / "index.py"
INDEX = REPO_ROOT / "docs" / "INDEX.md"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(INDEX_SCRIPT), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_check_passes_against_a_generated_index() -> None:
    assert run().returncode == 0
    assert run("--check").returncode == 0


def test_generating_twice_changes_nothing() -> None:
    run()
    first = INDEX.read_text()
    run()
    assert INDEX.read_text() == first


def test_check_fails_on_drift_and_names_the_fix() -> None:
    run()
    original = INDEX.read_text()
    try:
        INDEX.write_text(original + "\ndrift\n")
        result = run("--check")
        assert result.returncode == 1
        assert "just index" in result.stderr
    finally:
        INDEX.write_text(original)


def test_every_layer_appears() -> None:
    run()
    content = INDEX.read_text()
    templates = REPO_ROOT / "templates"
    for config in templates.rglob("copier.yml"):
        name = config.parent.relative_to(templates)
        assert f"`{name}`" in content, f"{name} absent from the index"
