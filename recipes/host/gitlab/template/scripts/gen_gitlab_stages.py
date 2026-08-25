#!/usr/bin/env python3
"""Rebuild .gitlab-ci.yml's stages list from the fragments in .gitlab/ci/.

    gen_gitlab_stages.py <dest>

GitLab fails the whole pipeline when a job names a stage absent from the top-level
`stages:` list, rather than skipping that job. The include is a glob, so a language
layer adopted later drops a fragment nothing here knew about.

Only the block between the two markers is rewritten. Anything outside them survives.

Stages sort by pipeline order rather than alphabetically, since `stages:` is what
defines which jobs run before which. A fragment naming a stage this script does not
know about fails here, where the message can say so, rather than in a pipeline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

BEGIN = "# BEGIN GENERATED: stages"
END = "# END GENERATED: stages"

# Pipeline order. A fragment's stage has to be one of these, and the rendered list
# keeps this order so a lint job runs before the test job that depends on it.
STAGE_ORDER = ("quality", "lint", "test", "security", "build", "deploy")

PREAMBLE = f"""\
{BEGIN}
# Rebuilt by `just gitlab-sync` from the stages the .gitlab/ci/ fragments declare.
# Do not edit by hand.
#
# A job naming a stage absent from this list fails the whole pipeline, and the
# include below is a glob, so a language layer adopted later contributes a fragment
# this file has to learn about.
"""


def fragments(dest: Path) -> list[Path]:
    directory = dest / ".gitlab" / "ci"
    if not directory.is_dir():
        return []
    return sorted(p for p in directory.glob("*.yml") if p.is_file())


# This layer's own jobs sit here, so the stages apply whatever the fragments declare.
# Without them a repository with no language layer has a pipeline whose only jobs name
# stages the list omits, which fails rather than skipping.
HOST_STAGES = ("quality", "security")


def declared_stages(dest: Path) -> list[str]:
    """Every stage the fragments name, plus this layer's own, in pipeline order."""
    found: set[str] = set(HOST_STAGES)
    unknown: dict[str, str] = {}

    for fragment in fragments(dest):
        try:
            spec = yaml.safe_load(fragment.read_text()) or {}
        except yaml.YAMLError as exc:
            raise SystemExit(f"{fragment.name} is not valid YAML: {exc}") from exc
        if not isinstance(spec, dict):
            continue
        for name, job in spec.items():
            # A key opening with a dot is a template, not a job, and GitLab ignores it.
            if name.startswith(".") or not isinstance(job, dict):
                continue
            stage = job.get("stage")
            if not stage:
                continue
            if stage not in STAGE_ORDER:
                unknown[stage] = fragment.name
            found.add(stage)

    if unknown:
        detail = ", ".join(f"{stage!r} in {where}" for stage, where in sorted(unknown.items()))
        raise SystemExit(
            f"unknown stage(s): {detail}. Add the stage to STAGE_ORDER, or rename the "
            "job's stage to one of: " + ", ".join(STAGE_ORDER)
        )

    return [stage for stage in STAGE_ORDER if stage in found]


def block(dest: Path) -> str:
    lines = [PREAMBLE, "stages:\n"]
    lines.extend(f"  - {stage}\n" for stage in declared_stages(dest))
    lines.append(f"{END}\n")
    return "".join(lines)


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    dest = Path(sys.argv[1])
    config = dest / ".gitlab-ci.yml"
    if not config.is_file():
        print("no .gitlab-ci.yml to update", file=sys.stderr)
        return 3

    body = config.read_text()
    if BEGIN not in body or END not in body:
        print(
            f"'.gitlab-ci.yml' has no '{BEGIN}' / '{END}' markers; refusing to guess "
            "where the stages list goes",
            file=sys.stderr,
        )
        return 3

    head, _, rest = body.partition(BEGIN)
    _, _, tail = rest.partition(END + "\n")
    config.write_text(head + block(dest) + tail)

    print(f".gitlab-ci.yml stages: {', '.join(declared_stages(dest))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
