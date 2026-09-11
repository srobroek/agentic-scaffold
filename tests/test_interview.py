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
