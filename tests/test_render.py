from __future__ import annotations

import itertools
import subprocess
from pathlib import Path

from conftest import ROOT


def expected_files(*, hooks: bool, agentic: bool, beads: bool, visibility: str, license: str) -> set[str]:
    files = {
        ".copier-answers.yml",
        ".editorconfig",
        ".gitattributes",
        ".gitignore",
        ".github/CODEOWNERS",
        ".github/ISSUE_TEMPLATE/bug_report.yml",
        ".github/ISSUE_TEMPLATE/feature_request.yml",
        ".github/PULL_REQUEST_TEMPLATE.md",
        "justfile",
        "mise.toml",
        "README.md",
    }
    if license != "none":
        files.add("LICENSE")
    if visibility == "public":
        files.update({"CODE_OF_CONDUCT.md", "CONTRIBUTING.md", "SECURITY.md"})
    if hooks:
        files.add(".pre-commit-config.yaml")
    if agentic:
        files.update(
            {
                "AGENTS.md",
                "CLAUDE.md",
                ".codex/AGENTS.md",
                ".omp/context.py",
                ".omp/mcp.json",
                ".omp/plugins.toml",
                ".omp/project-context.json",
                ".omp/repomix.json",
            }
        )
    return files


def files_in(path: Path) -> set[str]:
    return {str(item.relative_to(path)) for item in path.rglob("*") if item.is_file() and ".git" not in item.parts}


def test_every_boolean_and_visibility_license_combination_renders_identically(copy_template, tmp_path):
    combinations = itertools.product(
        (False, True), (False, True), (False, True), ("private", "public"), ("none", "apache-2.0", "mit")
    )
    count = 0
    for hooks, agentic, beads, visibility, license in combinations:
        first = tmp_path / f"first-{count}"
        second = tmp_path / f"second-{count}"
        answers = {
            "name": f"demo-{count}",
            "github_owner": "example",
            "license": license,
            "visibility": visibility,
            "hooks": hooks,
            "hook_manager": "prek",
            "agentic": agentic,
            "beads": beads,
            "conduct_contact": "security@example.com",
            "codeowner": "@example",
            "language": "none",
        }
        copy_template(first, **answers)
        copy_template(second, **answers)
        assert files_in(first) == expected_files(
            hooks=hooks, agentic=agentic, beads=beads, visibility=visibility, license=license
        )
        assert files_in(first) == files_in(second)
        for relative in files_in(first):
            assert (first / relative).read_bytes() == (second / relative).read_bytes()
        listing = subprocess.run(["just", "--list"], cwd=first, capture_output=True, text=True, check=False)
        assert listing.returncode == 0, listing.stderr
        count += 1
    assert count == 48


def test_expected_file_set_is_answer_function():
    assert ".pre-commit-config.yaml" not in expected_files(
        hooks=False, agentic=False, beads=False, visibility="private", license="none"
    )
    assert ".omp/plugins.toml" in expected_files(
        hooks=True, agentic=True, beads=False, visibility="private", license="apache-2.0"
    )
