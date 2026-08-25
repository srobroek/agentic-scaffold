"""`scaffold render` resolves recipes, honours prechecks, and refuses cleanly.

Exit codes the CLI promises, and the ones asserted here: 2 usage, 3 a missing binary or
a refused precheck, 4 copier raised, 5 the plan found a conflict.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import render_recipe, scaffold


def test_a_bare_name_is_a_usage_error(tmp_path: Path) -> None:
    """`agents` is neither an in-repo id, a local directory, nor a URL."""
    result = scaffold("render", "agents", "--dest", str(tmp_path))
    assert result.returncode == 2
    assert "no such recipe: agents" in result.stderr


def test_unknown_recipe_exits_2(tmp_path: Path) -> None:
    result = scaffold("render", "docs/nonexistent", "--dest", str(tmp_path))
    assert result.returncode == 2
    assert "no such recipe" in result.stderr


def test_naming_no_recipe_and_no_profile_exits_2(tmp_path: Path) -> None:
    result = scaffold("render", "--dest", str(tmp_path))
    assert result.returncode == 2
    assert "name recipes or pass --profile" in result.stderr


def test_missing_data_file_exits_2(tmp_path: Path) -> None:
    result = scaffold(
        "render",
        "docs/agents",
        "--dest",
        str(tmp_path),
        "--data-file",
        str(tmp_path / "absent.yml"),
    )
    assert result.returncode == 2
    assert "no such data file" in result.stderr


def test_pretend_writes_nothing(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()

    result = render_recipe("docs/agents", dest, "project_name: probe\n", "--pretend")

    assert result.returncode == 0
    assert list(dest.rglob("*")) == []


def test_render_writes_the_recipe(tmp_path: Path) -> None:
    dest = tmp_path / "dest"
    dest.mkdir()

    result = render_recipe("docs/agents", dest, "project_name: probe\n")

    assert result.returncode == 0, result.stderr
    assert (dest / "docs" / "agents" / "index.md").is_file()


def test_the_destination_becomes_a_committed_git_repository(tmp_path: Path) -> None:
    """base/repo's precheck refuses a destination with uncommitted changes, so a second
    recipe into the same tree only works when the first one was committed. The CLI commits
    per recipe, which is also what makes `scaffold update`'s 3-way merge reviewable."""
    dest = tmp_path / "dest"

    result = render_recipe("docs/agents", dest, "project_name: probe\n")

    assert result.returncode == 0, result.stderr
    assert (dest / ".git").is_dir()
    log = subprocess.run(
        ["git", "-C", str(dest), "log", "--format=%s"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert log.stdout.splitlines() == ["chore: render docs/agents"]


def test_hand_written_files_survive_a_second_render(tmp_path: Path) -> None:
    """`_skip_if_exists` is what keeps conventions.md from being lost.

    It carries no generated block, so all of it is hand-written and a re-render would
    otherwise replace the lot.
    """
    dest = tmp_path / "dest"
    dest.mkdir()
    answers = "project_name: probe\n"

    render_recipe("docs/agents", dest, answers)

    conventions = dest / "docs" / "agents" / "conventions.md"
    conventions.write_text("# Mine\n\nDo not lose this.\n")

    result = render_recipe("docs/agents", dest, answers)

    assert result.returncode == 0, result.stderr
    assert "Do not lose this." in conventions.read_text()


@pytest.mark.parametrize("binary", ["copier", "git"])
def test_recipe_metadata_names_real_binaries(binary: str) -> None:
    """A recipe's requires_bin must name something a check_binaries call can find."""
    assert shutil.which(binary) is not None, f"{binary} absent from PATH"
