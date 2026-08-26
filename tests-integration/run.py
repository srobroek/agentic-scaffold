#!/usr/bin/env python3
"""Render an integration case into a scratch tree, run its build, report what the tools said.

    run.py [name ...] [--list] [--keep]

A case is a combination of layers that no single profile and no unit test covers. See
README.md for the format and for what a case deliberately cannot do.

Reuses scripts/scaffold.py per layer rather than reimplementing the render, so a case
exercises the same path a person or the agent takes.

Exit codes:
    0  every selected case rendered, set up, built, and met its expectations
    1  a case failed; the output names which step and what the tool said
    2  usage error, or no such case
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parent
CASES = HERE / "cases"
SCAFFOLD = REPO_ROOT / "scripts" / "scaffold.py"

REQUIRED_KEYS = ("name", "summary", "gap", "layers", "build")


def load(path: Path) -> dict:
    case = yaml.safe_load(path.read_text()) or {}
    missing = [key for key in REQUIRED_KEYS if key not in case]
    if missing:
        print(f"{path.name}: missing {', '.join(missing)}", file=sys.stderr)
        raise SystemExit(2)
    if case["name"] != path.stem:
        print(f"{path.name}: names itself {case['name']!r}", file=sys.stderr)
        raise SystemExit(2)
    return case


def git_init(dest: Path) -> None:
    """base/repo's precheck refuses a dirty destination, and layers that read a ref need a
    repository, so the tree is one from the start. `-b main` because a layer defaulting to
    `main` would otherwise disagree with git's own default on some machines."""
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "main", str(dest)], check=True)
    for key, value in (("user.email", "case@example.com"), ("user.name", "Case")):
        subprocess.run(["git", "-C", str(dest), "config", key, value], check=True)
    subprocess.run(
        ["git", "-C", str(dest), "commit", "-q", "--allow-empty", "-m", "base"],
        check=True,
        capture_output=True,
    )


def commit(dest: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(dest), "add", "-A"], check=False, capture_output=True)
    subprocess.run(
        ["git", "-C", str(dest), "commit", "-q", "-m", message],
        check=False,
        capture_output=True,
    )


def render(case: dict, dest: Path) -> list[str]:
    """Each layer in the order the case gives.

    `scaffold render` commits per recipe itself, which is what lets a second layer render
    at all: base/repo's precheck refuses a destination with uncommitted changes, so it
    would otherwise fail on the first layer's output.
    """
    problems = []
    answers_path = dest.parent / f"{dest.name}-answers.yml"
    answers_path.write_text(yaml.safe_dump(case.get("answers") or {}, sort_keys=False))

    for layer in case["layers"]:
        result = subprocess.run(
            [
                sys.executable,
                str(SCAFFOLD),
                "render",
                layer,
                "--dest",
                str(dest),
                "--data-file",
                str(answers_path),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            problems.append(f"render {layer}: {result.stderr.strip()[:600]}")
            # A later layer expects the earlier one's files, so stop rather than cascade.
            break
        print(f"  ok    render {layer}")
    return problems


def run_commands(label: str, commands: list[str], dest: Path) -> list[str]:
    """Each command in the destination, reported with the tool's real output.

    A command whose binary is absent is skipped and said to be skipped. A run that quietly
    checked less than it appears to is worse than one that admits the gap.
    """
    problems = []
    for command in commands:
        binary = command.split()[0]
        if shutil.which(binary) is None:
            print(f"  skip  {label} {command}  ({binary} absent)")
            continue

        result = subprocess.run(
            command, shell=True, cwd=dest, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print(f"  ok    {label} {command}")
            continue

        output = (result.stdout + result.stderr).strip()
        problems.append(f"{label} {command} exited {result.returncode}:\n{output[-1200:]}")
    return problems


def check_expectations(case: dict, dest: Path) -> list[str]:
    """Each `expect` entry as a python expression over `tree`.

    An expression rather than a DSL: the assertions are one-offs per case, and inventing a
    matcher language for a handful of path checks costs more than it saves.
    """
    problems = []
    for expression in case.get("expect") or []:
        try:
            if eval(expression, {"tree": dest, "Path": Path}):
                print(f"  ok    expect {expression}")
            else:
                problems.append(f"expect failed: {expression}")
        except Exception as error:
            problems.append(f"expect raised on {expression}: {error!r}")
    return problems


def report(case: dict, problems: list[str], dest: Path, keep: bool) -> bool:
    """True when the case passed. A failure names the step and what the tool said."""
    if not problems:
        return True
    print(f"  FAIL  {case['name']}", file=sys.stderr)
    for problem in problems:
        print(f"    {problem}", file=sys.stderr)
    if keep:
        print(f"    tree kept at {dest}", file=sys.stderr)
    return False


def run_case(path: Path, keep: bool) -> bool:
    case = load(path)
    print(f"\n=== {case['name']}: {case['summary']}")

    scratch = Path(tempfile.mkdtemp(prefix=f"case-{case['name']}-"))
    dest = scratch / "tree"
    try:
        git_init(dest)
        # `before` populates the tree the way an existing repository arrives, which is what a
        # retrofit case needs: `_skip_if_exists` has nothing to skip on an empty tree, so a
        # case that renders first proves nothing about which side wins.
        problems = run_commands("before", case.get("before") or [], dest)
        if problems:
            return report(case, problems, dest, keep)
        commit(dest, "existing tree")

        problems = render(case, dest)
        if not problems:
            problems += run_commands("setup", case.get("setup") or [], dest)
        if not problems:
            problems += run_commands("build", case["build"], dest)
        if not problems:
            problems += check_expectations(case, dest)

        return report(case, problems, dest, keep)
    finally:
        if not keep:
            shutil.rmtree(scratch, ignore_errors=True)


def main() -> int:
    parser = argparse.ArgumentParser(prog="run.py", description=__doc__)
    parser.add_argument("names", nargs="*", help="case file stems; empty runs every case")
    parser.add_argument("--list", action="store_true", help="list the cases and exit")
    parser.add_argument(
        "--keep",
        action="store_true",
        help="leave a failing case's tree on disk, for inspecting what a tool saw",
    )
    args = parser.parse_args()

    available = sorted(CASES.glob("*.yml"))
    if args.list:
        for path in available:
            case = load(path)
            print(f"{case['name']:<34} {case['summary']}")
        return 0

    if args.names:
        by_stem = {path.stem: path for path in available}
        unknown = [name for name in args.names if name not in by_stem]
        if unknown:
            print(f"no such case: {', '.join(unknown)}", file=sys.stderr)
            print(f"available: {', '.join(sorted(by_stem))}", file=sys.stderr)
            return 2
        selected = [by_stem[name] for name in args.names]
    else:
        selected = available

    if not selected:
        print("no cases under tests-integration/cases", file=sys.stderr)
        return 2

    failed = [path.stem for path in selected if not run_case(path, args.keep)]

    print()
    if failed:
        print(f"{len(failed)} of {len(selected)} case(s) failed: {', '.join(failed)}")
        return 1
    print(f"{len(selected)} case(s) passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
