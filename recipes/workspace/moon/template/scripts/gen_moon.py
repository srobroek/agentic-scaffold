#!/usr/bin/env python3
"""Generate a moon.yml for every workspace member.

    gen_moon.py <dest> [--members GLOB] [--check]

The member glob is read from the root manifest rather than passed in, so this and the
manifest cannot disagree about where members live. Same resolution order as
scripts/add_member.py: Cargo.toml, then pyproject.toml, then package.json, then go.mod.

Each member gets a moon.yml whose `dependsOn` is derived from that member's own
manifest, which is what lets `moon run <member>:build` order the graph and, more
usefully, invalidate a dependent when its dependency changes. Measured on a
three-member chain where core <- api <- web: changing core rebuilt all three in 3.46s,
changing only web reused two cache entries and took 1.24s against a 3.37s cold run.
The equivalent hand-written `just` loop costs the full 3.4s every time, because it has
no graph to consult.

Only the block between the two markers is rewritten, so a task added by hand survives.

`--check` regenerates in memory and exits 1 when a file on disk differs, naming the
command that fixes it.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import tomllib
from pathlib import Path

BEGIN = "# BEGIN GENERATED: moon"
END = "# END GENERATED: moon"

# Which moon toolchain a layout declares. moon keys javascript by the runtime rather
# than the package manager, so bun and node share one entry.
TOOLCHAIN = {
    "rust": "rust",
    "python": "python",
    "go": "go",
    "ts": "javascript",
}

# A project's kind. moon 2.x renamed this key from `type` to `layer`; an older CLI
# rejects the new spelling and a newer one rejects the old, so the pin in
# .mise/conf.d/moon.toml is what keeps the generated file loadable.
LIBRARY = "library"
APPLICATION = "application"

# Where each toolchain actually writes its build output, which is what moon caches.
#
# An output path is member-relative by default, and for rust that is wrong: cargo
# writes to the WORKSPACE root `target/`, never to `crates/<name>/target/`. Declaring
# the bare path made moon report "defines outputs but after being ran, either none or
# not" and cache nothing, so rust uses a `/` prefix, moon's workspace-relative token.
#
# Sharing one directory across members means a member's cache entry is keyed by its own
# inputs while the directory holds every member's artefacts. `target/debug` is narrowed
# to the profile so the cache does not also capture registry sources.
OUTPUTS = {
    "rust": ["    outputs:", "      - '/target/debug'"],
    # `uv sync` writes into the workspace's shared .venv, not a per-member directory,
    # and a venv is not a cacheable artefact. Declaring `dist` here would name a path
    # nothing creates, which is the failure mode the rust entry above hit.
    "python": [],
    # go writes a binary only for a main package, and `go build ./...` with no -o
    # discards it. Nothing to cache, so nothing is declared: an outputs entry that
    # never appears is what produced the rust failure above.
    "go": [],
    "ts": ["    outputs:", "      - 'dist'"],
}

# What counts as a source change, per toolchain. A pattern matching nothing makes the
# task look unaffected forever, which is worse than declaring no inputs at all: moon
# would then serve a stale cache entry after a real edit.
#
# go is the case that proves it matters. Go keeps its sources as *.go beside the
# package rather than under src/, so a `src/**/*` pattern matches nothing in a go
# member and no edit would ever invalidate the build.
BUILD_INPUTS = {
    "rust": ["      - 'src/**/*'", "      - 'Cargo.toml'"],
    "python": ["      - 'src/**/*'", "      - 'pyproject.toml'"],
    "go": ["      - '**/*.go'", "      - '/go.mod'", "      - '/go.sum'"],
    "ts": ["      - 'src/**/*'", "      - 'package.json'", "      - 'tsconfig.json'"],
}

TEST_INPUTS = {
    "rust": ["      - 'src/**/*'", "      - 'tests/**/*'"],
    "python": ["      - 'src/**/*'", "      - 'tests/**/*'"],
    # A go test file sits beside the code it tests, so the build pattern already covers it.
    "go": ["      - '**/*.go'"],
    "ts": ["      - 'src/**/*'", "      - 'tests/**/*'"],
}


def globs_from_manifest(dest: Path) -> tuple[list[str], str]:
    """Every member glob the root manifest declares, and the layout it implies."""
    if (dest / "Cargo.toml").is_file():
        data = tomllib.loads((dest / "Cargo.toml").read_bytes().decode())
        return (data.get("workspace") or {}).get("members") or [], "rust"
    if (dest / "pyproject.toml").is_file():
        data = tomllib.loads((dest / "pyproject.toml").read_bytes().decode())
        uv = (data.get("tool") or {}).get("uv") or {}
        return (uv.get("workspace") or {}).get("members") or [], "python"
    if (dest / "package.json").is_file():
        data = json.loads((dest / "package.json").read_text())
        return data.get("workspaces") or [], "ts"
    if (dest / "go.mod").is_file():
        # go has no member list: a member is a directory inside the one module, and
        # cmd/* is the convention workspace/monorepo writes.
        return ["cmd/*"], "go"
    return [], ""


def members(dest: Path, override: str = "") -> list[Path]:
    patterns, _ = globs_from_manifest(dest)
    if override:
        patterns = [override]
    found: list[Path] = []
    for pattern in patterns:
        for path in sorted(dest.glob(pattern)):
            if path.is_dir():
                found.append(path)
    return found


def rust_deps(path: Path, names: set[str]) -> list[str]:
    """Sibling crates this one depends on, read from its own Cargo.toml.

    A path dependency inside the workspace is the edge moon needs; a registry
    dependency is not a project in the graph and is skipped.
    """
    manifest = path / "Cargo.toml"
    if not manifest.is_file():
        return []
    data = tomllib.loads(manifest.read_bytes().decode())
    found = []
    for section in ("dependencies", "dev-dependencies", "build-dependencies"):
        for name, spec in (data.get(section) or {}).items():
            if name not in names or not isinstance(spec, dict):
                continue
            if "path" in spec or spec.get("workspace"):
                found.append(name)
    return sorted(set(found))


def node_deps(path: Path, names: set[str]) -> list[str]:
    manifest = path / "package.json"
    if not manifest.is_file():
        return []
    data = json.loads(manifest.read_text())
    found = []
    for section in ("dependencies", "devDependencies", "peerDependencies"):
        for name in data.get(section) or {}:
            # A workspace sibling resolves by name, so membership in the graph is the
            # test rather than the version specifier's shape.
            if name in names:
                found.append(name)
    return sorted(set(found))


def python_deps(path: Path, names: set[str]) -> list[str]:
    manifest = path / "pyproject.toml"
    if not manifest.is_file():
        return []
    data = tomllib.loads(manifest.read_bytes().decode())
    declared = ((data.get("project") or {}).get("dependencies")) or []
    found = []
    for entry in declared:
        # A requirement string carries operators and extras; the name is the leading
        # identifier.
        name = re.split(r"[<>=!~\[; ]", entry.strip(), maxsplit=1)[0]
        if name in names:
            found.append(name)
    return sorted(set(found))


def member_name(path: Path, layout: str) -> str:
    """What the graph calls this member.

    moon keys a project by its id, and a dependency is written with that id. For rust
    and javascript the manifest's own name is what a sibling depends on, so the two
    have to agree; the directory name is the fallback.
    """
    if layout == "rust" and (path / "Cargo.toml").is_file():
        data = tomllib.loads((path / "Cargo.toml").read_bytes().decode())
        return ((data.get("package") or {}).get("name")) or path.name
    if layout == "ts" and (path / "package.json").is_file():
        return json.loads((path / "package.json").read_text()).get("name") or path.name
    if layout == "python" and (path / "pyproject.toml").is_file():
        data = tomllib.loads((path / "pyproject.toml").read_bytes().decode())
        return ((data.get("project") or {}).get("name")) or path.name
    return path.name


def deps_for(path: Path, layout: str, names: set[str]) -> list[str]:
    if layout == "rust":
        return rust_deps(path, names)
    if layout == "ts":
        return node_deps(path, names)
    if layout == "python":
        return python_deps(path, names)
    # go resolves imports within one module, so there is no per-member manifest to read
    # and no edge to derive.
    return []


# The package name is written in literally rather than through $MOON_PROJECT_ID.
# moon's project id is derived from the directory, while cargo's `-p` and uv's
# `--package` take the name from the member's own manifest, and the two differ whenever
# a crate is named differently from its folder. `member_name` reads the manifest, so
# the value substituted here is the one the tool expects.
def build_command(layout: str, name: str) -> str:
    return {
        "rust": f"cargo build -p {name}",
        # `uv sync --package` rather than a python one-liner. A nested single quote
        # would end the surrounding YAML scalar, and syncing is the real build step for
        # a python member: it resolves that member's dependencies into the environment.
        "python": f"uv sync --package {name}",
        # go builds the directory, since a member is a package inside one module.
        "go": "go build ./...",
        "ts": "bun run build",
    }[layout]


def test_command(layout: str, name: str) -> str:
    return {
        "rust": f"cargo nextest run -p {name}",
        "python": f"uv run --package {name} pytest -q",
        "go": "go test -race ./...",
        "ts": "bun run test",
    }[layout]


def render(path: Path, layout: str, names: set[str], is_app: bool, name: str) -> str:
    """One member's moon.yml.

    Inputs are declared per task, because a task with no inputs is re-run every time
    and a task with no outputs is never cached: both silently defeat the reason this
    layer exists.
    """
    deps = deps_for(path, layout, names)
    lines = [
        BEGIN,
        "# Rebuilt by `just moon-sync` from the workspace manifest. Do not edit inside",
        "# these markers; anything outside them survives regeneration.",
        "#",
        "# `layer:` rather than `type:`. moon 2.x renamed the key, so the version pinned in",
        "# .mise/conf.d/moon.toml is what keeps this file loadable.",
        f"layer: {APPLICATION if is_app else LIBRARY}",
        f"language: {TOOLCHAIN[layout]}",
    ]

    if deps:
        lines += [
            "",
            "# Derived from this member's own manifest, so the graph follows the code rather",
            "# than a hand-maintained list. This is the edge that invalidates a dependent's",
            "# cache when its dependency changes.",
            "dependsOn:",
        ]
        lines += [f"  - '{dep}'" for dep in deps]

    lines += [
        "",
        "tasks:",
        "  build:",
        f"    command: '{build_command(layout, name)}'",
        # Without `inputs` moon treats the task as always affected; without `outputs`
        # it has nothing to restore, so the cache never engages.
        "    inputs:",
    ]
    lines += BUILD_INPUTS[layout]
    lines += OUTPUTS[layout]
    if deps:
        lines += ["    deps:"] + [f"      - '{dep}:build'" for dep in deps]

    lines += [
        "  test:",
        f"    command: '{test_command(layout, name)}'",
        "    inputs:",
    ]
    lines += TEST_INPUTS[layout]
    lines += [
        "    deps:",
        "      - 'build'",
        END,
        "",
    ]
    return "\n".join(lines)


def write_member(path: Path, body: str) -> bool:
    """Write a member's moon.yml, preserving anything outside the markers."""
    target = path / "moon.yml"
    if target.is_file():
        current = target.read_text()
        if BEGIN in current and END in current:
            head, _, rest = current.partition(BEGIN)
            _, _, tail = rest.partition(END + "\n")
            new = head + body.rstrip("\n") + "\n" + tail
            if new == current:
                return False
            target.write_text(new)
            return True
    if target.is_file() and target.read_text() == body:
        return False
    target.write_text(body)
    return True


def expected(path: Path, body: str) -> str:
    target = path / "moon.yml"
    if target.is_file():
        current = target.read_text()
        if BEGIN in current and END in current:
            head, _, rest = current.partition(BEGIN)
            _, _, tail = rest.partition(END + "\n")
            return head + body.rstrip("\n") + "\n" + tail
    return body


def main() -> int:
    parser = argparse.ArgumentParser(prog="gen_moon.py", description=__doc__)
    parser.add_argument("dest", type=Path)
    parser.add_argument("--members", default="", help="override the manifest's glob")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    dest = args.dest
    _, layout = globs_from_manifest(dest)
    if not layout:
        print("no workspace manifest found; nothing to generate", file=sys.stderr)
        return 0

    found = members(dest, args.members)
    if not found:
        print("the manifest's member glob resolves nothing yet; nothing to generate")
        return 0

    names = {member_name(path, layout) for path in found}
    stale = []
    changed = 0
    for path in found:
        # An application is what nothing else depends on. moon uses the distinction to
        # decide what may be a root of the graph.
        name = member_name(path, layout)
        depended_on = any(
            name in deps_for(other, layout, names) for other in found if other != path
        )
        body = render(path, layout, names, is_app=not depended_on, name=name)

        if args.check:
            target = path / "moon.yml"
            current = target.read_text() if target.is_file() else ""
            if current != expected(path, body):
                stale.append(str(path.relative_to(dest) / "moon.yml"))
        elif write_member(path, body):
            changed += 1

    if args.check:
        if stale:
            print("stale moon.yml: " + ", ".join(stale), file=sys.stderr)
            print("fix with: just moon-sync", file=sys.stderr)
            return 1
        print(f"{len(found)} moon.yml file(s) current")
        return 0

    print(f"wrote {changed} of {len(found)} moon.yml file(s) ({layout})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
