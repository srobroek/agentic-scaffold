"""core.hooksPath must be absolute, or prek never fires in a linked worktree.

A worktree's `.git` is a file holding `gitdir: <primary>/.git/worktrees/<name>`,
so a relative `.git/hooks` resolves against the worktree root and git reports
"Not a directory". The commit then succeeds with no hook and no warning, which is
why this has a test rather than a comment.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
JUSTFILE = REPO_ROOT / "justfile"


def git(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=False)


def commit_all(path: Path, message: str) -> subprocess.CompletedProcess[str]:
    git("add", "-A", cwd=path)
    return git("-c", "user.email=t@t", "-c", "user.name=t", "commit", "-m", message, cwd=path)


@pytest.fixture
def repo_with_worktree(tmp_path: Path) -> tuple[Path, Path]:
    """A primary checkout plus a linked worktree, made with plain git.

    `git worktree add` rather than `wt switch --create`, so the test needs neither
    worktrunk nor its lifecycle rules.
    """
    primary = tmp_path / "primary"
    primary.mkdir()
    git("init", "-q", "-b", "main", ".", cwd=primary)
    (primary / "f.txt").write_text("x\n")
    commit_all(primary, "init")

    linked = tmp_path / "linked"
    git("worktree", "add", "-q", str(linked), "-b", "feat", cwd=primary)
    return primary, linked


def hooks_path_command(where: Path) -> str:
    """The value the justfile recipe would set, run from `where`."""
    common = git(
        "rev-parse", "--path-format=absolute", "--git-common-dir", cwd=where
    ).stdout.strip()
    return f"{common}/hooks"


def test_the_recipe_resolves_identically_from_both_worktrees(
    repo_with_worktree: tuple[Path, Path],
) -> None:
    primary, linked = repo_with_worktree
    assert hooks_path_command(primary) == hooks_path_command(linked)


def test_the_resolved_path_is_absolute_and_exists(
    repo_with_worktree: tuple[Path, Path],
) -> None:
    primary, _ = repo_with_worktree
    resolved = Path(hooks_path_command(primary))
    assert resolved.is_absolute()
    assert resolved.is_dir()


def test_a_relative_hooks_path_breaks_in_a_linked_worktree(
    repo_with_worktree: tuple[Path, Path],
) -> None:
    """The failure this recipe exists to prevent."""
    primary, linked = repo_with_worktree
    git("config", "--local", "core.hooksPath", ".git/hooks", cwd=primary)

    result = git("rev-parse", "--path-format=absolute", "--git-path", "hooks", cwd=linked)

    assert result.returncode != 0
    assert "Not a directory" in result.stderr


def test_an_absolute_hooks_path_resolves_in_a_linked_worktree(
    repo_with_worktree: tuple[Path, Path],
) -> None:
    primary, linked = repo_with_worktree
    git("config", "--local", "core.hooksPath", hooks_path_command(primary), cwd=primary)

    result = git("rev-parse", "--path-format=absolute", "--git-path", "hooks", cwd=linked)

    assert result.returncode == 0
    assert Path(result.stdout.strip()).is_dir()


def test_hooks_path_is_shared_across_worktrees(
    repo_with_worktree: tuple[Path, Path],
) -> None:
    """It is a local value in the shared .git/config, so setting it once is enough."""
    primary, linked = repo_with_worktree
    expected = hooks_path_command(primary)
    git("config", "--local", "core.hooksPath", expected, cwd=primary)

    assert git("config", "core.hooksPath", cwd=linked).stdout.strip() == expected


def test_setup_depends_on_hooks_path() -> None:
    """Otherwise a fresh clone installs shims git will never look for."""
    body = JUSTFILE.read_text()
    assert "setup: hooks-path" in body


def test_the_recipe_uses_git_common_dir() -> None:
    """--git-dir points at the worktree's own gitdir; --git-common-dir at the primary."""
    body = JUSTFILE.read_text()
    assert "--git-common-dir" in body
    assert "core.hooksPath .git/hooks" not in body
