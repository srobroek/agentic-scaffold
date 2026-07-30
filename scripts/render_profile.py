#!/usr/bin/env python3
"""Render a whole profile into a destination, then optionally run its build.

    render_profile.py <profile> <dest> [--build] [--answers FILE]

A tree that renders is not a project that builds, which is the failure class this exists
to catch: every defect found while porting these layers rendered cleanly first and failed
only when the real tool read the result.

The generator is NOT run. `cargo new`, `uv init`, and `create-better-t-stack` reach the
network or need a toolchain the machine may not carry, and the agent runs them per
rules/choices.md. This renders the layer set in the profile's order, which is what the
layers themselves have to get right.

Exit codes:
    0  rendered, and the build passed when --build was given
    1  a layer failed to render, or a build command exited non-zero
    2  usage error, or no such profile
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES = REPO_ROOT / "profiles"
RENDER = REPO_ROOT / "scripts" / "render.py"


def load(name: str) -> dict:
    path = PROFILES / f"{name}.yml"
    if not path.is_file():
        print(f"no such profile: {name}", file=sys.stderr)
        raise SystemExit(2)
    return yaml.safe_load(path.read_text()) or {}


def git_init(dest: Path) -> None:
    """base/repo's precheck refuses a destination with uncommitted changes, and every
    layer that reads a ref needs a repository, so the destination is one from the start."""
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    for key, value in (("user.email", "scaffold@example.com"), ("user.name", "Scaffold")):
        subprocess.run(["git", "-C", str(dest), "config", key, value], check=True)


def commit(dest: Path, message: str) -> None:
    """Stage and commit whatever a layer wrote. Silent when there is nothing to commit."""
    subprocess.run(["git", "-C", str(dest), "add", "-A"], check=False, capture_output=True)
    subprocess.run(
        ["git", "-C", str(dest), "commit", "-q", "-m", message],
        check=False,
        capture_output=True,
    )


def render_layer(layer: str, dest: Path, answers: Path | None) -> subprocess.CompletedProcess:
    argv = [sys.executable, str(RENDER), layer, str(dest)]
    if answers is not None:
        argv += ["--answers", str(answers)]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def write_answers(profile: dict, dest: Path, extra: Path | None) -> Path:
    """One answers file for the whole profile.

    copier ignores a key a layer does not declare, so a single file serves every layer and
    the profile does not have to say which layer reads which answer.
    """
    answers = {
        # The six interview answers, filled with values a build can actually use. A real
        # render takes these from the agent.
        "project_name": profile["name"].replace("-", "_"),
        "description": profile.get("summary", "A scaffolded project."),
        "org": "scaffold",
        "author": "Scaffold",
        "owner": "scaffold",
        "repo_url": "https://github.com/scaffold/demo",
        "default_branch": "main",
        "site_url": "https://scaffold.github.io/demo",
        "pages_repo": "scaffold/scaffold.github.io",
        "go_module_path": f"github.com/scaffold/{profile['name']}",
        "bd_prefix": "".join(c for c in profile["name"] if c not in "aeiou-")[:3] or "prj",
        # local-only, because a render must not reach a remote.
        "bd_dolt_sync": "local-only",
    }
    answers.update(profile.get("answers") or {})
    if extra is not None:
        answers.update(yaml.safe_load(extra.read_text()) or {})

    path = dest.parent / f"{dest.name}-profile-answers.yml"
    path.write_text(yaml.safe_dump(answers, sort_keys=False))
    return path


def run_build(profile: dict, dest: Path) -> int:
    """Each command in the profile's own build, in order, in the destination.

    Reported with the command's real output rather than a summary: the point of the check
    is what the tool said.
    """
    failures = 0
    for command in profile.get("build") or []:
        binary = command.split()[0]
        if shutil.which(binary) is None:
            print(f"  skip  {command}  ({binary} absent)")
            continue

        result = subprocess.run(
            command, shell=True, cwd=dest, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print(f"  ok    {command}")
            continue

        failures += 1
        print(f"  FAIL  {command}  (exit {result.returncode})", file=sys.stderr)
        for line in (result.stdout + result.stderr).splitlines()[-25:]:
            print(f"        {line}", file=sys.stderr)
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(prog="render_profile.py", description=__doc__)
    parser.add_argument("profile")
    parser.add_argument("dest", type=Path)
    parser.add_argument("--build", action="store_true", help="run the profile's build commands")
    parser.add_argument("--answers", type=Path, help="extra answers, overriding the profile's")
    args = parser.parse_args()

    profile = load(args.profile)
    dest = args.dest
    git_init(dest)
    answers = write_answers(profile, dest, args.answers)

    print(f"{profile['name']}: {len(profile['layers'])} layers -> {dest}")
    for layer in profile["layers"]:
        result = render_layer(layer, dest, answers)
        if result.returncode != 0:
            print(f"  FAIL  render {layer} (exit {result.returncode})", file=sys.stderr)
            for line in (result.stdout + result.stderr).splitlines()[-25:]:
                print(f"        {line}", file=sys.stderr)
            return 1
        print(f"  ok    render {layer}")

        # Committed after every layer, because base/repo's precheck refuses a destination
        # with uncommitted changes: copier overwrites and leaves no diff to review. In a
        # real render the agent commits per layer for the same reason, so this is the same
        # sequence rather than a test convenience.
        commit(dest, f"chore: render {layer}")

    if not args.build:
        return 0

    failures = run_build(profile, dest)
    if failures:
        print(f"\n{profile['name']}: {failures} build command(s) failed", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
