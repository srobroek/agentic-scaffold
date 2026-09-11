#!/usr/bin/env python3
"""Show a Copier render plan without modifying the destination."""

from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path


def parse_data(values: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for value in values:
        key, separator, item = value.partition("=")
        if not separator or not key:
            raise ValueError(f"data must be KEY=VALUE: {value!r}")
        result[key] = item
    return result

def conflict_files(root: Path) -> list[str]:
    result = subprocess.run(
        ["git", "-C", str(root), "grep", "-l", "<<<<<<<"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode not in (0, 1):
        raise RuntimeError(result.stderr.strip() or "git grep failed")
    return sorted(line for line in result.stdout.splitlines() if line)


def target_is_greenfield(target: Path) -> bool:
    if not target.exists():
        return True
    return all(path.name == ".git" or path.name.startswith(".copier-answers") for path in target.iterdir())


def bootstrap_steps(data: dict[str, str]) -> list[str]:
    steps = ["mise install"]
    if data.get("hooks", "true").lower() == "true":
        manager = data.get("hook_manager", "prek")
        steps.append(
            "prek install --git-dir \"$(git rev-parse --absolute-git-dir)\""
            if manager == "prek"
            else "git-defender precommit-tool-setup"
        )
    if data.get("agentic", "true").lower() == "true" and data.get("beads", "true").lower() == "true":
        steps.append("bd init --init-if-missing --skip-hooks")
    return steps


def copy_command(source: str, target: str, tag: str, data: dict[str, str]) -> str:
    parts = ["uvx", "copier", "copy", "--defaults", "--vcs-ref", tag]
    for key, value in data.items():
        parts.extend(["--data", f"{key}={value}"])
    parts.extend([source, target])
    return " ".join(parts)


def render_files(source: Path, data: dict[str, str], tag: str) -> list[str]:
    with tempfile.TemporaryDirectory(prefix="scaffold-plan-") as directory:
        destination = Path(directory) / "rendered"
        command = ["uvx", "copier", "copy", "--defaults", "--quiet", "--vcs-ref", tag]
        for key, value in data.items():
            command.extend(["--data", f"{key}={value}"])
        command.extend([str(source), str(destination)])
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip())
        return sorted(
            str(path.relative_to(destination))
            for path in destination.rglob("*")
            if path.is_file()
        )

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("--tag", default="HEAD")
    parser.add_argument("--data", action="append", default=[])
    args = parser.parse_args()
    try:
        data = parse_data(args.data)
        if not target_is_greenfield(args.target):
            print(json.dumps({"error": "target must contain only .git and .copier-answers*.yml"}))
            return 2
        files = render_files(args.source.resolve(), data, args.tag)
        plan = {
            "files": [{"path": path, "action": "create"} for path in files],
            "bootstrap": bootstrap_steps(data),
            "copy_command": copy_command(str(args.source), str(args.target), args.tag, data),
            "template_ref": args.tag,
        }
        print(json.dumps(plan, indent=2))
        return 0
    except (OSError, ValueError, RuntimeError) as exc:
        print(json.dumps({"error": str(exc)}))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
