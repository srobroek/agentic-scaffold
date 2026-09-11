from __future__ import annotations

import importlib.util
from pathlib import Path

from conftest import ROOT


spec = importlib.util.spec_from_file_location("interview", ROOT / "scripts/interview.py")
interview = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(interview)


def test_paging_bounds_and_navigation_sentinel():
    choices = ["a", "b", "c", "d", "e"]
    assert interview.page_choices(choices, 0) == ["a", "b", "c", "d", interview.MORE_CHOICES]
    assert interview.page_choices(choices, 1) == ["e"]
    assert interview.page_choices(choices, 2) == []


def test_navigation_sentinel_never_enters_multi_select_data():
    assert interview.merge_multi_select(["python"], ["rust", interview.MORE_CHOICES]) == ["python", "rust"]


def test_when_evaluation_and_derived_defaults(tmp_path: Path):
    source = tmp_path / "copier.yml"
    source.write_text(
        """
name:
  type: str
  default: derived
hooks:
  type: bool
  default: true
public_contact:
  type: str
  when: "{{ hooks }}"
private_only:
  type: str
  when: "{{ not hooks }}"
"""
    )
    cwd = tmp_path / "sample"
    cwd.mkdir()
    result = interview.inspect(source, cwd, {"hooks": True})
    assert result["facts"]["name"] == "sample"
    question_ids = [question["id"] for question in result["ask"]["questions"]]
    assert "public_contact" in question_ids
    assert "private_only" not in question_ids


def test_command_emission_uses_data_pairs():
    command = interview.command("/template", "/destination", "v-test", ["name=demo", "hooks=true"])
    assert command == "uvx copier copy --vcs-ref v-test --data name=demo --data hooks=true /template /destination"


def test_inspect_emits_ask_pages_and_clean_data(tmp_path: Path):
    target = tmp_path / "e2e"
    target.mkdir()
    subprocess_git = ["git", "-C", str(target)]
    import subprocess

    subprocess.run([*subprocess_git, "init", "-q"], check=True)
    subprocess.run([*subprocess_git, "remote", "add", "origin", "git@github.com:acme/e2e.git"], check=True)
    first = interview.inspect(ROOT / "copier.yml", target, {})
    assert first["facts"]["github_owner"] == "acme" and first["facts"]["name"] == "e2e"
    questions = first["ask"]["questions"]
    assert 0 < len(questions) <= 5 and first["complete"] is False
    for question in questions:
        assert 1 <= len(question["options"]) <= 5, question["id"]
        assert all(set(option) <= {"label", "description"} for option in question["options"])
        assert 0 <= question["recommended"] < len(question["options"])
    booleans = {q["id"]: [o["label"] for o in q["options"]] for q in questions if q["id"] in {"hooks", "agentic"}}
    assert booleans == {"hooks": ["true", "false"], "agentic": ["true", "false"]}
    answered = {"license": "mit", "visibility": "public", "hooks": True, "hook_manager": "prek", "agentic": True, "beads": interview.MORE_CHOICES}
    second = interview.inspect(ROOT / "copier.yml", target, answered)
    ids = [q["id"] for q in second["ask"]["questions"]]
    assert "beads" in ids, "the navigation sentinel is not an answer"
    codeowner = next(q for q in second["ask"]["questions"] if q["id"] == "codeowner")
    assert codeowner["options"][0]["label"] == "@acme"
    assert all("{{" not in item for item in second["data"])
    assert not any(item.startswith("conduct_contact=") for item in second["data"]), "a pending free-text answer is not emitted"
    done = interview.inspect(ROOT / "copier.yml", target, {**answered, "beads": True, "conduct_contact": "x@y.z", "codeowner": "@acme", "language": "none"})
    assert done["complete"] is True and "codeowner=@acme" in done["data"] and "name=e2e" in done["data"]
