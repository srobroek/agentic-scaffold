"""render.py resolves layers, honours prechecks, and refuses cleanly."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RENDER), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_layer_without_a_group_is_a_usage_error(tmp_path: Path) -> None:
    result = run("agents", str(tmp_path))
    assert result.returncode == 2
    assert "<group>/<name>" in result.stderr


def test_unknown_layer_exits_2(tmp_path: Path) -> None:
    result = run("docs/nonexistent", str(tmp_path))
    assert result.returncode == 2
    assert "no such layer" in result.stderr


def test_missing_answers_file_exits_2(tmp_path: Path) -> None:
    result = run("docs/agents", str(tmp_path), "--answers", str(tmp_path / "absent.yml"))
    assert result.returncode == 2
    assert "no such answers file" in result.stderr


def test_pretend_writes_nothing(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    answers = tmp_path / "a.yml"
    answers.write_text("project_name: probe\n")

    result = run("docs/agents", str(dest), "--answers", str(answers), "--pretend")

    assert result.returncode == 0
    assert list(dest.rglob("*")) == []


def test_render_writes_the_layer(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()
    answers = tmp_path / "a.yml"
    answers.write_text("project_name: probe\n")

    result = run("docs/agents", str(dest), "--answers", str(answers))

    assert result.returncode == 0
    assert (dest / "docs" / "agents" / "index.md").is_file()


def test_hand_written_files_survive_a_second_render(tmp_path: Path) -> None:
    """`_skip_if_exists` is what keeps conventions.md from being lost.

    It carries no generated block, so all of it is hand-written and a re-render would
    otherwise replace the lot.
    """
    dest = tmp_path / "dest"
    dest.mkdir()
    answers = tmp_path / "a.yml"
    answers.write_text("project_name: probe\n")

    run("docs/agents", str(dest), "--answers", str(answers))

    conventions = dest / "docs" / "agents" / "conventions.md"
    conventions.write_text("# Mine\n\nDo not lose this.\n")

    result = run("docs/agents", str(dest), "--answers", str(answers))

    assert result.returncode == 0
    assert "Do not lose this." in conventions.read_text()


@pytest.mark.parametrize("binary", ["copier", "git"])
def test_layer_metadata_names_real_binaries(binary: str) -> None:
    """A layer's requires_bin must name something a check_binaries call can find."""
    import shutil

    assert shutil.which(binary) is not None, f"{binary} absent from PATH"
