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
    templates = REPO_ROOT / "recipes"
    for config in templates.rglob("copier.yml"):
        name = config.parent.relative_to(templates)
        assert f"`{name}`" in content, f"{name} absent from the index"


def test_the_index_lists_only_files_git_tracks() -> None:
    """The index is derived from what the repository contains, not from what happens to sit in
    a working tree.

    Walking the filesystem put two `__pycache__/*.pyc` paths from a local bytecode cache into
    the committed index. `just index-check` passed locally and failed on every CI run, because
    the runner has no such files, and the diagnosis cost a full CI cycle: the failure names a
    stale file rather than the reason it differs.
    """
    listed = {
        line.strip()
        for line in INDEX.read_text().splitlines()
        if line.strip() and not line.startswith(("#", "|", "`", "Writes", "Requires", "Generated"))
    }
    ignored = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "--others", "--ignored", "--exclude-standard",
         "--", "recipes"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()

    # Every ignored file's own path tail, as the index would render it.
    for path in ignored:
        tail = path.split("/template/", 1)[-1] if "/template/" in path else path
        assert tail not in listed, f"{path} is git-ignored but appears in docs/INDEX.md"


def test_an_untracked_file_under_a_template_is_not_indexed(tmp_path: Path) -> None:
    """The property directly, rather than through whatever happens to be ignored right now.

    A file that exists and is not tracked must not change the output, or the index depends on
    which working tree generated it.
    """
    before = subprocess.run(
        [sys.executable, str(INDEX_SCRIPT), "--check"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert before.returncode == 0, "the committed index is already stale; run `just index`"

    intruder = REPO_ROOT / "recipes" / "base" / "repo" / "template" / "zz-untracked-probe.txt"
    assert not intruder.exists()
    intruder.write_text("not tracked\n")
    try:
        after = subprocess.run(
            [sys.executable, str(INDEX_SCRIPT), "--check"],
            capture_output=True,
            text=True,
            check=False,
        )
        assert after.returncode == 0, (
            "an untracked file changed the index, so it is not a function of the repository: "
            + after.stderr
        )
    finally:
        intruder.unlink()
