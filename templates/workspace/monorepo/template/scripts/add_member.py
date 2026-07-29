#!/usr/bin/env python3
"""Add a workspace member: run the language generator, then place the layer's files.

    add_member.py <name> <lang> [--repo .] [--scaffold <path>]

A language layer has two destination roots. Its tool configs and its
`.pre-commit-config.yaml` belong to the member directory, because they describe that
package. Its `.mise/conf.d/`, `.just.d/`, `.gitignore.d/`, and CI fragments belong to
the repository root, because every aggregating layer reads them from there.

copier renders to one destination, so the layer renders into the member path and the
repository-wide fragments are moved up afterwards. Merging into an existing directory
rather than replacing it: two languages both contribute `.mise/conf.d/`.

The member path comes from the workspace manifest's own glob, so this script and the
manifest cannot disagree about where members live.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

# `name` reaches `uv init --name`, `go mod init`, and a manifest, so anything
# carrying a path separator or a shell metacharacter is refused before it gets there.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

# Directories the aggregating layers read from the repository root. Everything else a
# language layer writes describes the member and stays with it.
REPO_WIDE = (".mise", ".just.d", ".gitignore.d", ".github", ".gitlab")

# What each generator needs, and the command that creates a member.
GENERATORS = {
    "rust": ("cargo", ["cargo", "init", "--lib", "--vcs", "none", "--name"]),
    "python": ("uv", ["uv", "init", "--vcs", "none", "--name"]),
    "go": (None, None),  # one module: a member is a directory, so nothing to init
    "ts": ("bun", ["bun", "init", "-y"]),
}


def die(message: str) -> None:
    print(f"add-member: {message}", file=sys.stderr)
    raise SystemExit(1)


def member_glob(repo: Path) -> str:
    """Read the member path from the workspace manifest.

    Deriving it rather than taking an argument keeps `just add` and the manifest from
    disagreeing about where a member goes.
    """
    cargo = repo / "Cargo.toml"
    if cargo.is_file():
        data = tomllib.loads(cargo.read_text())
        members = (data.get("workspace") or {}).get("members") or []
        if members:
            return members[0]

    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text())
        members = ((data.get("tool") or {}).get("uv") or {}).get("workspace", {}).get(
            "members"
        ) or []
        if members:
            return members[0]

    package = repo / "package.json"
    if package.is_file():
        members = json.loads(package.read_text()).get("workspaces") or []
        if members:
            return members[0]

    if (repo / "go.mod").is_file():
        return "cmd/*"

    die("no workspace manifest found; render workspace/monorepo first")
    raise AssertionError  # unreachable, keeps the type checker happy


def install_member_hooks(member: Path) -> bool:
    """Promote the member's hook fragment to a real `.pre-commit-config.yaml`.

    prek's workspace mode unions one config per directory and namespaces the hooks
    `<dir>:<hook-id>`, so a member's hooks travel with it and nothing merges. It reads
    `.pre-commit-config.yaml` though, and skips dot-prefixed directories during
    discovery, so the `.pre-commit.d/` fragment alone is invisible to it.
    """
    fragments = sorted((member / ".pre-commit.d").glob("*.yaml"))
    if not fragments:
        return False

    target = member / ".pre-commit-config.yaml"
    if target.is_file():
        return False

    header = (
        "# Generated from .pre-commit.d/ by `just add`. prek's workspace mode reads one\n"
        "# config per directory and namespaces these <dir>:<hook-id>, so this member's\n"
        "# hooks travel with it.\n"
    )
    target.write_text(header + "".join(f.read_text() for f in fragments))
    return True


def register_release(repo: Path, member: str, release_type: str) -> bool:
    """Add the member to release-please's config and manifest.

    release-please has no glob support: `packages` takes a literal path per package, and
    its workspace plugins only build a dependency graph over what is already configured.
    A member absent from the config is never versioned, tagged, or written into the
    changelog, and nothing reports the omission.

    The recorded versions are release-please's own after the first release, so an entry
    already present is left alone and only the new member is added. It joins at the
    version the others share, or 0.1.0 when they disagree, so a repository releasing 2.x
    does not ship a 0.1.0 package.
    """
    config_path = repo / "release-please-config.json"
    manifest_path = repo / ".release-please-manifest.json"
    if not config_path.is_file() or not manifest_path.is_file():
        return False

    config = json.loads(config_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    if member in config.get("packages", {}):
        return False

    packages = config.setdefault("packages", {})
    # A single-package repository releases ".". Once a member exists, the root is no
    # longer the thing being released, and its tag would collide with the member's.
    packages.pop(".", None)
    manifest.pop(".", None)

    packages[member] = {"component": member.rsplit("/", 1)[-1]}
    if release_type:
        packages[member]["release-type"] = release_type
    # Per-package tags, or every member's tag collides on one version number.
    config["include-component-in-tag"] = True
    config.setdefault("separate-pull-requests", False)

    versions = sorted(set(manifest.values()))
    manifest[member] = versions[-1] if len(versions) == 1 else "0.1.0"

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    return True


def refresh_prek(repo: Path) -> None:
    """Rescan prek's workspace cache.

    prek caches which directories hold a config, so a member added afterwards is
    invisible until the cache is refreshed. Verified against prek 0.4.11: `prek list`
    showed only root hooks until `prek list --refresh` ran once, after which the
    member hooks stayed listed.
    """
    if shutil.which("prek") is None:
        return
    subprocess.run(
        ["prek", "list", "--refresh"],
        cwd=repo,
        capture_output=True,
        check=False,
    )


def move_repo_wide(member: Path, repo: Path) -> list[str]:
    """Lift the repository-wide fragments out of the member directory.

    Merged rather than replaced: two language layers both contribute a
    `.mise/conf.d/` entry, and moving the directory wholesale would drop the first.
    """
    moved = []
    for name in REPO_WIDE:
        source = member / name
        if not source.is_dir():
            continue
        for path in sorted(source.rglob("*")):
            if not path.is_file():
                continue
            target = repo / name / path.relative_to(source)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(path), target)
            moved.append(str(target.relative_to(repo)))
        shutil.rmtree(source)
    return moved


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name")
    parser.add_argument("lang", choices=sorted(GENERATORS))
    parser.add_argument("--repo", type=Path, default=Path("."))
    parser.add_argument(
        "--scaffold",
        type=Path,
        help="project-scaffold checkout holding scripts/render.py. Skipped when absent.",
    )
    args = parser.parse_args()

    if not NAME_RE.match(args.name):
        die(
            f"name {args.name!r} must start alphanumeric and hold only letters, digits, "
            "dot, dash, or underscore"
        )

    repo = args.repo.resolve()
    glob = member_glob(repo)
    if not glob.endswith("/*"):
        die(f"member glob {glob!r} does not end in /*, so a member path cannot be derived")
    member = repo / glob[:-2] / args.name

    if member.exists() and any(member.iterdir()):
        die(f"{member.relative_to(repo)} already exists and is not empty")
    member.mkdir(parents=True, exist_ok=True)

    binary, command = GENERATORS[args.lang]
    if binary and shutil.which(binary) is None:
        die(f"{binary} is not on PATH, which {args.lang} needs")
    if command:
        argv = [*command, args.name] if command[-1] == "--name" else list(command)
        print(f"add-member: {' '.join(argv)}")
        if subprocess.run(argv, cwd=member, check=False).returncode != 0:
            die(f"the {args.lang} generator failed in {member.relative_to(repo)}")

    if args.scaffold:
        render = args.scaffold / "scripts" / "render.py"
        if not render.is_file():
            die(f"no render.py under {args.scaffold}")
        print(f"add-member: rendering lang/{args.lang} at {member.relative_to(repo)}")
        if (
            subprocess.run(
                [sys.executable, str(render), f"lang/{args.lang}", str(member)], check=False
            ).returncode
            != 0
        ):
            die(f"rendering lang/{args.lang} failed")

        if install_member_hooks(member):
            print(f"add-member: {member.relative_to(repo)}/.pre-commit-config.yaml")
        for path in move_repo_wide(member, repo):
            print(f"add-member: {path}")
        refresh_prek(repo)

    # Independent of the layer render: a member is releasable whether or not the
    # language layer's own files were written.
    release_types = {"rust": "rust", "python": "python", "go": "go", "ts": "node"}
    if register_release(repo, str(member.relative_to(repo)), release_types[args.lang]):
        print("add-member: registered with release-please")

    print(f"add-member: {args.name} at {member.relative_to(repo)}")
    print("Run `just hooks-merge` and `just just-sync` to fold in what it contributed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
