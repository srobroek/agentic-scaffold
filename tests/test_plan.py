from __future__ import annotations

import importlib.util
import json
import subprocess
from pathlib import Path

from conftest import ROOT


spec = importlib.util.spec_from_file_location("plan", ROOT / "scripts/plan.py")
plan = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(plan)


def test_refuses_non_greenfield_target(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / "notes.txt").write_text("owned")
    assert plan.main is not None
    assert plan.target_is_greenfield(target) is False


def test_accepts_git_and_answers_only(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    (target / ".git").mkdir()
    (target / ".copier-answers-old.yml").write_text("name: old\n")
    assert plan.target_is_greenfield(target)


def test_bootstrap_steps_follow_answers():
    assert plan.bootstrap_steps({"hooks": "false", "agentic": "false"}) == ["mise install"]
    assert plan.bootstrap_steps({"hooks": "true", "hook_manager": "git-defender", "agentic": "true", "beads": "true"}) == [
        "mise install",
        "git-defender precommit-tool-setup",
        "bd init --init-if-missing --skip-hooks",
    ]


def test_plan_file_map(tmp_path: Path):
    target = tmp_path / "target"
    command = [
        "python3",
        str(ROOT / "scripts/plan.py"),
        str(ROOT),
        str(target),
        "--tag",
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
    ]
    result = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    paths = {entry["path"] for entry in payload["files"]}
    assert "README.md" in paths
    assert "AGENTS.md" not in paths
    assert payload["template_ref"] == "v-test"
    assert payload["bootstrap"] == ["mise install"]
