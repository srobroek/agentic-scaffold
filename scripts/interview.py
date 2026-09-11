#!/usr/bin/env python3
"""Present the Copier questions without writing files."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import yaml
from jinja2 import Template

PAGE_SIZE = 4
MORE_CHOICES = "More choices"


def _git(*args: str, cwd: Path) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False
    )
    return result.stdout.strip() if result.returncode == 0 else ""


def remote_owner(cwd: Path) -> str:
    """Return the owner from origin, for HTTPS and SSH remotes."""
    remote = _git("remote", "get-url", "origin", cwd=cwd)
    if not remote:
        return ""
    if ":" in remote and "@" in remote.split(":", 1)[0]:
        path = remote.rsplit(":", 1)[1]
    else:
        path = urlparse(remote).path
    parts = [part for part in path.strip("/").split("/") if part]
    return re.sub(r"\.git$", "", parts[-2]) if len(parts) >= 2 else ""


def hook_manager(cwd: Path) -> str:
    """Derive the manager from a git-defender hooks path, defaulting to prek."""
    hooks_path = _git("config", "--get", "core.hooksPath", cwd=cwd)
    return "git-defender" if "git-defender" in hooks_path else "prek"


def _render_when(expression: object, answers: dict[str, object]) -> bool:
    if expression in (None, True, ""):
        return True
    if expression is False:
        return False
    rendered = Template(str(expression)).render(**answers).strip().lower()
    return rendered not in {"", "0", "false", "none", "null", "no"}


def _default(question: dict, facts: dict[str, object]) -> object:
    question_id = question["id"]
    if question_id in facts:
        return facts[question_id]
    return question.get("default")


def _normalise_data(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def page_choices(choices: list[object], page: int) -> list[object]:
    """Return four choices and a navigation sentinel when another page exists."""
    if page < 0:
        raise ValueError("page must be non-negative")
    start = page * PAGE_SIZE
    selected = choices[start : start + PAGE_SIZE]
    if start + PAGE_SIZE < len(choices):
        selected.append(MORE_CHOICES)
    return selected


def merge_multi_select(previous: object, selected: list[object]) -> list[object]:
    """Merge page selections while never treating the navigation sentinel as data."""
    old = list(previous) if isinstance(previous, list) else []
    return list(dict.fromkeys([*old, *(item for item in selected if item != MORE_CHOICES)]))


def inspect(
    config_path: Path, cwd: Path, answers: dict[str, object], page: dict[str, int] | None = None
) -> dict[str, object]:
    config = yaml.safe_load(config_path.read_text()) or {}
    facts: dict[str, object] = {
        "name": answers.get("name") or cwd.name,
        "github_owner": answers.get("github_owner") or remote_owner(cwd),
        "hook_manager": answers.get("hook_manager") or hook_manager(cwd),
    }
    combined = {**facts, **answers}
    for question_id, raw in config.items():
        if isinstance(raw, dict) and "type" in raw and question_id not in combined:
            default = _default({"id": question_id, **raw}, facts)
            if default is not None:
                combined[question_id] = default
    questions: list[dict[str, object]] = []
    data: dict[str, object] = {}
    for question_id, raw in config.items():
        if question_id.startswith("_") or not isinstance(raw, dict) or "type" not in raw:
            continue
        if not _render_when(raw.get("when"), combined):
            continue
        value = answers.get(question_id, _default({"id": question_id, **raw}, facts))
        if value is not None:
            data[question_id] = value
        derived_name = question_id == "name" and bool(facts["name"])
        derived_owner = question_id == "github_owner" and bool(facts["github_owner"])
        if question_id in answers or derived_name or derived_owner:
            continue
        question = {"id": question_id, "type": raw["type"], "help": raw.get("help", "")}
        if "choices" in raw:
            choices = list(raw["choices"])
            if page and page.get("id") == len(questions):
                question["choices"] = page_choices(choices, page.get("number", 0))
            else:
                question["choices"] = choices
        if raw.get("default") is not None or question_id == "hook_manager":
            question["default"] = facts.get(question_id, raw.get("default"))
    complete = not questions
    return {
        "facts": facts,
        "ask": {"questions": questions},
        "complete": complete,
        "data": [f"{key}={_normalise_data(data[key])}" for key in config if key in data],
    }


def command(source: str, dest: str, tag: str, data: list[str]) -> str:
    parts = ["uvx", "copier", "copy", "--vcs-ref", tag]
    for item in data:
        parts.extend(["--data", item])
    parts.extend([source, dest])
    return " ".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=Path("copier.yml"))
    parser.add_argument("--answers-so-far", default="{}")
    parser.add_argument("--page", default=None)
    parser.add_argument("--emit-command", action="store_true")
    parser.add_argument("--source", default=".")
    parser.add_argument("--dest", default=".")
    parser.add_argument("--tag", default="HEAD")
    args = parser.parse_args()
    answers = json.loads(args.answers_so_far)
    page = json.loads(args.page) if args.page else None
    result = inspect(args.config, Path.cwd(), answers, page)
    if args.emit_command:
        print(command(args.source, args.dest, args.tag, result["data"]))
    else:
        print(json.dumps(result, indent=2, sort_keys=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
