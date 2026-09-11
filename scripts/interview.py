#!/usr/bin/env python3
# /// script
# requires-python = ">=3.12"
# dependencies = ["copier>=9.18"]
# ///
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
    """A question's default, with Jinja rendered against the facts and answers known so far."""
    question_id = question["id"]
    if question_id in facts:
        return facts[question_id]
    default = question.get("default")
    if isinstance(default, str) and "{{" in default:
        rendered = Template(default).render(**facts)
        return rendered if rendered and "{{" not in rendered else None
    return default


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


ASK_PAGE_QUESTIONS = 5


def ask_question(question: dict[str, object], page_number: int) -> dict[str, object]:
    """Shape one Copier question for the agent's ``ask`` tool.

    At most five options; a list longer than that shows four per page plus the ``More choices``
    sentinel. A free-text question shows its default as the only option: the tool adds its own
    ``Other`` entry, which is the input path for a typed value.
    """
    question_id = str(question["id"])
    default = question.get("default")
    text = str(question.get("help") or question_id)
    multi = question.get("type") == "yaml" and isinstance(default, list)
    if question.get("type") == "bool":
        options = [{"label": "true"}, {"label": "false"}]
        recommended = 0 if default in (True, "true", None) else 1
        return {"id": question_id, "question": text, "options": options, "recommended": recommended, "multi": False}
    choices = [str(item) for item in question.get("choices", [])]
    paging: dict[str, object] | None = None
    if len(choices) > ASK_PAGE_QUESTIONS:
        pages = -(-len(choices) // PAGE_SIZE)
        page_number = max(0, min(page_number, pages - 1))
        shown = page_choices(choices, page_number)
        paging = {"page": page_number, "pages": pages, "more": None if page_number >= pages - 1 else json.dumps({"id": question_id, "number": page_number + 1})}
        text += f" (values {page_number * PAGE_SIZE + 1}-{min((page_number + 1) * PAGE_SIZE, len(choices))} of {len(choices)})"
    elif choices:
        shown = choices
    else:
        shown = [str(default)] if default not in (None, "") else ["Provide a value"]
    options = [{"label": str(item)} for item in shown]
    recommended = next((index for index, option in enumerate(options) if option["label"] == str(default)), 0)
    entry: dict[str, object] = {"id": question_id, "question": text, "options": options, "recommended": recommended, "multi": multi}
    if paging:
        entry["paging"] = paging
    return entry


def inspect(
    config_path: Path, cwd: Path, answers: dict[str, object], page: dict[str, object] | None = None
) -> dict[str, object]:
    config = yaml.safe_load(config_path.read_text()) or {}
    facts: dict[str, object] = {
        "name": answers.get("name") or cwd.name,
        "github_owner": answers.get("github_owner") or remote_owner(cwd),
        "hook_manager": answers.get("hook_manager") or hook_manager(cwd),
    }
    # The sentinel is navigation, never an answer: it is dropped before anything else reads the answers.
    answers = {key: value for key, value in answers.items() if value != MORE_CHOICES}
    for key, value in list(answers.items()):
        if isinstance(value, list):
            answers[key] = merge_multi_select([], value)
    combined = {**facts, **answers}
    for question_id, raw in config.items():
        if isinstance(raw, dict) and "type" in raw and question_id not in combined:
            default = _default({"id": question_id, **raw}, combined)
            if default is not None:
                combined[question_id] = default
    pending: list[dict[str, object]] = []
    data: dict[str, object] = {}
    for question_id, raw in config.items():
        if question_id.startswith("_") or not isinstance(raw, dict) or "type" not in raw:
            continue
        if not _render_when(raw.get("when"), combined):
            continue
        value = answers.get(question_id, _default({"id": question_id, **raw}, combined))
        # Only an answer, a derived fact, or a real default travels to Copier; an empty pending value does not.
        if value is not None and value != "":
            data[question_id] = value
        derived_name = question_id == "name" and bool(facts["name"])
        derived_owner = question_id == "github_owner" and bool(facts["github_owner"])
        if question_id in answers or derived_name or derived_owner:
            continue
        question: dict[str, object] = {"id": question_id, "type": raw["type"], "help": raw.get("help", "")}
        if "choices" in raw:
            question["choices"] = list(raw["choices"])
        if raw.get("default") is not None or question_id == "hook_manager":
            question["default"] = facts.get(question_id, _default({"id": question_id, **raw}, combined))
        pending.append(question)
    page_number = int(page.get("number", 0)) if page else 0
    paged_id = str(page.get("id")) if page else None
    shown = pending[:ASK_PAGE_QUESTIONS]
    ask_questions = [ask_question(question, page_number if question["id"] == paged_id else 0) for question in shown]
    emitted = [f"{key}={_normalise_data(data[key])}" for key in config if key in data]
    unresolved = [item for item in emitted if "{{" in item or "}}" in item]
    if unresolved:
        raise SystemExit(f"unresolved template in answers: {unresolved}")
    return {
        "facts": facts,
        "ask": {"questions": ask_questions},
        "remaining": len(pending),
        "complete": not pending,
        "data": emitted,
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
