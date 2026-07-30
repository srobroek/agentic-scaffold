#!/usr/bin/env python3
"""Validate the profiles under profiles/ against the layers under templates/.

    profiles.py [--check] [--list] [NAME]

A profile names layers by path, so a layer renamed or removed leaves a profile pointing at
nothing. Rendering would then fail per profile, one at a time, with a message about a
missing directory rather than about the profile that named it. This checks the whole set
at once, which is why `just check` runs it before the tests.

What it verifies:

- every layer a profile names exists and carries a copier.yml
- the layer order respects each layer's own `_scaffold.after`, so a profile cannot ask for
  a layer before the one it reads from
- `agentic/apm` and `agentic/package` never appear together, since both own apm.yml
- a monorepo profile puts `workspace/monorepo` before every `lang/*`
- the required keys are present and `build` is non-empty

Exit codes:
    0  every profile is valid
    1  at least one profile is not, with the reason
    2  usage error
"""

from __future__ import annotations

import argparse
import fnmatch
import os
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
# Overridable so a test can validate a copied directory. Writing a fixture into the real
# profiles/ made the suite fail under `-n auto`: one worker saw another worker's file.
PROFILES = Path(os.environ.get("SCAFFOLD_PROFILES") or REPO_ROOT / "profiles")
TEMPLATES = REPO_ROOT / "templates"

REQUIRED_KEYS = ("name", "summary", "generator", "layers", "build")

# Both own apm.yml, so a repository is either a package publisher or a package consumer.
EXCLUSIVE = (("agentic/apm", "agentic/package"),)


def layer_exists(layer: str) -> bool:
    return (TEMPLATES / layer / "copier.yml").is_file()


def declared_after(layer: str) -> list[str]:
    """The `_scaffold.after` list a layer declares, which may hold globs."""
    config = yaml.safe_load((TEMPLATES / layer / "copier.yml").read_text()) or {}
    meta = config.get("_scaffold") or {}
    after = meta.get("after") or []
    return [entry for entry in after if isinstance(entry, str)]


def matches(pattern: str, layers: list[str]) -> list[str]:
    return [layer for layer in layers if fnmatch.fnmatch(layer, pattern)]


# Each aggregator and the directory it reads. A layer shipping that directory in its
# template contributes to it.
AGGREGATORS = (
    ("workspace/just", ".just.d"),
    ("base/gitignore", ".gitignore.d"),
    ("quality/hooks", ".pre-commit.d"),
)


def contributes(layer: str, directory: str) -> bool:
    return (TEMPLATES / layer / "template" / directory).is_dir()


def aggregation_problems(present: list[str], position: dict[str, int]) -> list[str]:
    problems = []
    for aggregator, directory in AGGREGATORS:
        if aggregator not in position:
            continue
        for layer in present:
            if layer == aggregator or not contributes(layer, directory):
                continue
            if position[layer] > position[aggregator]:
                problems.append(
                    f"renders {layer} after {aggregator}, but it contributes a "
                    f"{directory} fragment that {aggregator} folds in"
                )
    return problems


def check_one(path: Path) -> list[str]:
    """Every problem with one profile, so a run reports them together."""
    problems: list[str] = []
    try:
        profile = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [f"is not valid YAML: {exc}"]

    for key in REQUIRED_KEYS:
        if key not in profile:
            problems.append(f"has no `{key}`")
    if problems:
        return problems

    if profile["name"] != path.stem:
        problems.append(f"names itself {profile['name']!r} but the file is {path.stem!r}")

    layers = profile["layers"]
    if not isinstance(layers, list) or not layers:
        return [*problems, "`layers` is empty"]

    for layer in layers:
        if not layer_exists(layer):
            problems.append(f"names {layer}, which has no templates/{layer}/copier.yml")

    if not profile["build"]:
        problems.append("`build` is empty, so rendering it would prove nothing")

    # Ordering. A layer's own `after` is the authority, and a glob there matches whatever
    # the profile selected: `lang/*` in host/github's list means every language layer the
    # profile names, not every language layer that exists.
    present = [layer for layer in layers if layer_exists(layer)]
    position = {layer: index for index, layer in enumerate(present)}
    for layer in present:
        for pattern in declared_after(layer):
            for earlier in matches(pattern, present):
                if earlier == layer:
                    continue
                if position[earlier] > position[layer]:
                    problems.append(
                        f"puts {layer} before {earlier}, but {layer} declares `after: {pattern}`"
                    )

    for first, second in EXCLUSIVE:
        if first in layers and second in layers:
            problems.append(f"names both {first} and {second}, which own the same apm.yml")

    # A layer that contributes to an aggregated directory has to precede the layer that
    # aggregates it, or the generated file is stale the moment the render finishes. A
    # layer's `after` list cannot express this on its own: workspace/just would have to
    # name every present and future contributor, and workspace/moon was missed exactly that
    # way -- rust-gui rendered clean and then failed `just just-check`.
    problems += aggregation_problems(present, position)

    # The monorepo axis. `workspace/monorepo` writes the root manifest that every member
    # resolves through, so a language layer rendering first would write into a repository
    # that is not yet a workspace.
    if "workspace/monorepo" in present:
        root = position["workspace/monorepo"]
        for language in matches("lang/*", present):
            if position[language] < root:
                problems.append(
                    f"renders {language} before workspace/monorepo, so the member glob "
                    "does not exist yet"
                )

    return problems


def profiles() -> list[Path]:
    return sorted(PROFILES.glob("*.yml"))


def main() -> int:
    parser = argparse.ArgumentParser(prog="profiles.py", description=__doc__)
    parser.add_argument("name", nargs="?", help="validate one profile rather than all")
    parser.add_argument("--check", action="store_true", help="exit 1 on any problem")
    parser.add_argument(
        "--list", action="store_true", help="print each profile and its layer count"
    )
    args = parser.parse_args()

    found = profiles()
    if not found:
        print("no profiles under profiles/", file=sys.stderr)
        return 1

    if args.name:
        found = [path for path in found if path.stem == args.name]
        if not found:
            print(f"no such profile: {args.name}", file=sys.stderr)
            return 2

    if args.list:
        for path in found:
            profile = yaml.safe_load(path.read_text()) or {}
            print(
                f"{profile.get('name', path.stem):<14} {len(profile.get('layers') or []):>2} layers"
            )
        return 0

    failed = 0
    for path in found:
        problems = check_one(path)
        if problems:
            failed += 1
            for problem in problems:
                print(f"{path.name}: {problem}", file=sys.stderr)

    if failed:
        print(f"\n{failed} of {len(found)} profile(s) invalid", file=sys.stderr)
        return 1

    print(f"{len(found)} profile(s) valid")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
