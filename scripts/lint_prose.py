#!/usr/bin/env python3
"""Run the prose gate over the docs.

    lint_prose.py [PATH ...]

Internal genre for everything under `docs/`, `rules/`, `profiles/`, and
`AGENTS.md`. Consumer genre for `README.md`. `docs/INDEX.md` is generated and is
not linted.

Given paths, lints those instead of the tracked set, so a hook can pass staged
files.

Exit codes:
    0  clean, or the gate is not installed
    1  the gate reported a finding
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
GATE = Path.home() / ".claude" / "skills" / "review-docs" / "scripts" / "slop-lint.sh"

INTERNAL_GLOBS = ("docs/*.md", "docs/**/*.md", "rules/*.md", "profiles/*.md", "AGENTS.md")
CONSUMER_FILES = ("README.md",)
GENERATED = ("docs/INDEX.md",)


def tracked(globs: tuple[str, ...]) -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *globs],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return [line for line in result.stdout.splitlines() if line]


def run_gate(genre: str, files: list[str]) -> int:
    if not files:
        return 0
    result = subprocess.run(
        ["bash", str(GATE), "--genre", genre, *files],
        check=False,
        cwd=REPO_ROOT,
    )
    return result.returncode


def partition(paths: list[str]) -> tuple[list[str], list[str]]:
    """Split paths into internal-genre and consumer-genre, dropping generated files."""
    internal, consumer = [], []
    for path in paths:
        if path in GENERATED:
            continue
        if path in CONSUMER_FILES:
            consumer.append(path)
        elif path.endswith(".md"):
            internal.append(path)
    return internal, consumer


def main() -> int:
    parser = argparse.ArgumentParser(prog="lint_prose.py", description=__doc__)
    parser.add_argument("paths", nargs="*", help="lint these instead of the tracked set")
    args = parser.parse_args()

    if not GATE.is_file():
        print(f"prose gate absent at {GATE}, skipping", file=sys.stderr)
        return 0

    if args.paths:
        internal, consumer = partition(args.paths)
    else:
        internal = [p for p in tracked(INTERNAL_GLOBS) if p not in GENERATED]
        consumer = [p for p in CONSUMER_FILES if (REPO_ROOT / p).is_file()]

    status = 0
    status |= run_gate("internal", internal)
    status |= run_gate("consumer", consumer)
    return 1 if status else 0


if __name__ == "__main__":
    raise SystemExit(main())
