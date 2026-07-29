#!/usr/bin/env python3
"""Sync release-please's packages list with the workspace members.

    sync_release_packages.py <dest>

`just add` creates a member, and release-please does not discover it: a package absent
from the config is never versioned, tagged, or written into the changelog, and nothing
reports the omission.

The recorded versions are release-please's own after the first release, so a member
already listed keeps its version. Only the packages list changes, and a new member
starts at the version the manifest's other entries share, or 0.1.0 when it is the first.

A single-package repository has no member glob, and its config keeps `"."`.
"""

from __future__ import annotations

import json
import sys
import tomllib
from pathlib import Path

CONFIG = "release-please-config.json"
MANIFEST = ".release-please-manifest.json"


def member_globs(repo: Path) -> list[str]:
    """The globs the workspace manifest resolves members through."""
    cargo = repo / "Cargo.toml"
    if cargo.is_file():
        data = tomllib.loads(cargo.read_text())
        if members := (data.get("workspace") or {}).get("members"):
            return members

    pyproject = repo / "pyproject.toml"
    if pyproject.is_file():
        data = tomllib.loads(pyproject.read_text())
        workspace = ((data.get("tool") or {}).get("uv") or {}).get("workspace") or {}
        if members := workspace.get("members"):
            return members

    package = repo / "package.json"
    if package.is_file() and (members := json.loads(package.read_text()).get("workspaces")):
        return members

    # go is one module, so a directory under cmd/ is not a separately released package.
    return []


def members(repo: Path) -> list[str]:
    found = []
    for pattern in member_globs(repo):
        for path in sorted(repo.glob(pattern)):
            if path.is_dir():
                found.append(str(path.relative_to(repo)))
    return sorted(set(found))


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    repo = Path(sys.argv[1])
    config_path = repo / CONFIG
    manifest_path = repo / MANIFEST
    if not config_path.is_file() or not manifest_path.is_file():
        print("no release-please config to sync", file=sys.stderr)
        return 3

    config = json.loads(config_path.read_text())
    manifest = json.loads(manifest_path.read_text())
    found = members(repo)

    if not found:
        print("no workspace members; leaving the single-package config alone")
        return 0

    # A new member starts where the others are rather than at 0.1.0, so a repository
    # releasing 2.x does not ship a 0.1.0 package.
    versions = sorted(set(manifest.values()))
    fallback = versions[-1] if len(versions) == 1 else "0.1.0"

    config["separate-pull-requests"] = False
    config["include-component-in-tag"] = True
    config["packages"] = {pkg: {"component": pkg.rsplit("/", 1)[-1]} for pkg in found}
    # Versions already recorded are release-please's, so they are kept verbatim.
    manifest = {pkg: manifest.get(pkg, fallback) for pkg in found}

    config_path.write_text(json.dumps(config, indent=2) + "\n")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n")
    print(f"release-please tracks {len(found)} package(s): {', '.join(found)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
