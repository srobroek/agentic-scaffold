from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import importlib.util

from conftest import ROOT, git_commit, git_init

spec = importlib.util.spec_from_file_location("plan", ROOT / "scripts/plan.py")
plan = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(plan)
conflict_files = plan.conflict_files

def test_update_round_trip_and_conflict_detection(tmp_path: Path):
    source = tmp_path / "template-repo"
    shutil.copytree(
        ROOT,
        source,
        symlinks=True,
        ignore=shutil.ignore_patterns(".git", ".agents", ".claude", ".pytest_cache", "__pycache__"),
    )
    git_init(source)
    git_commit(source, "template v-test")
    subprocess.run(["git", "-C", str(source), "tag", "v-test"], check=True)

    destination = tmp_path / "destination"
    command = [
        "uvx",
        "copier",
        "copy",
        "--defaults",
        "--vcs-ref",
        "v-test",
        "--data",
        "name=demo",
        "--data",
        "github_owner=example",
        "--data",
        "license=none",
        "--data",
        "visibility=private",
        "--data",
        "hooks=false",
        "--data",
        "agentic=false",
        "--data",
        "language=none",
        str(source),
        str(destination),
    ]
    rendered = subprocess.run(command, capture_output=True, text=True, check=False)
    assert rendered.returncode == 0, rendered.stderr or rendered.stdout
    git_init(destination)
    git_commit(destination, "render")
    (source / "template/mise.toml.jinja").write_text(
        (source / "template/mise.toml.jinja").read_text() + "[env]\nSCAFFOLD_TEST = \"updated\"\n"
    )
    git_commit(source, "template v-test2")
    subprocess.run(["git", "-C", str(source), "tag", "v-test2"], check=True)

    update = subprocess.run(
        ["uvx", "copier", "update", "--defaults", "--vcs-ref", "v-test2"],
        cwd=destination,
        capture_output=True,
        text=True,
    )
    assert 'SCAFFOLD_TEST = "updated"' in (destination / "mise.toml").read_text()
    assert update.returncode == 0, update.stderr
    assert conflict_files(destination) == []
    (destination / "justfile").write_text(
        (destination / "justfile").read_text().replace("# List the available", "# Local list", 1)
    )
    (source / "template/justfile.jinja").write_text(
        (source / "template/justfile.jinja").read_text().replace("# List the available", "# Changed list", 1)
    )
    git_commit(source, "template conflict")
    subprocess.run(["git", "-C", str(source), "tag", "v-test3"], check=True)
    conflict = subprocess.run(
        ["uvx", "copier", "update", "--defaults", "--vcs-ref", "v-test3", "--conflict", "inline"],
        cwd=destination,
        capture_output=True,
        text=True,
        check=False,
    )
    assert conflict.returncode == 0
    assert conflict_files(destination) == ["justfile"]
