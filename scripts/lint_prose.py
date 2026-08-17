#!/usr/bin/env python3
"""Run the prose gate over the docs.

    lint_prose.py [PATH ...]

Everything under `docs/`, `rules/`, `profiles/`, plus `AGENTS.md` and `README.md`.
`docs/INDEX.md` is generated and is not linted.

Given paths, lints those instead of the tracked set, so a hook can pass staged files.

slopvac is not on PyPI yet, so the gate is inactive until it is: the wrapper says so and exits
0. There is deliberately no `uvx --from <checkout>` fallback -- a gate that builds one
developer's working copy checks whatever that copy happens to say, which is not a gate.

WHY slopvac AND NOT THE VALE GATE. This called `~/.claude/skills/review-docs/scripts/
slop-lint.sh` until that script stopped existing: slopvac ba2f21e moved Vale into the linter
package and replaced the shell gate with this CLI. The installed skill was stale, and its
`.vale-change.ini` shared one `StylesPath` with `.vale.ini` while omitting the `prose-scope`
package. `vale sync` replaces that directory wholesale, so syncing either config deleted a style
the other needed and `just lint` failed at random until someone re-synced. Calling the linter
directly removes the shared directory, so there is nothing left to desync.

`--profile relaxed`, measured rather than picked: across the sixteen files gated here it scores
99.3/100 with zero errors, where `normal` scores 43.3 and reports 355 findings. The difference is
almost entirely Simplified Technical English rules the previous gate never applied, so `normal`
would be a new standard for this repository's prose rather than the same one. Raising it is a
decision to take deliberately, not a side effect of a linter migration.

Exit codes:
    0  clean, or the linter is not reachable
    1  the linter reported a finding
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# The profile and every override live in slopvac.toml, which is committed. Passing --profile
# here would silently outrank it.
CONFIG = REPO_ROOT / "slopvac.toml"

GLOBS = ("docs/*.md", "docs/**/*.md", "rules/*.md", "profiles/*.md", "AGENTS.md", "README.md")
GENERATED = ("docs/INDEX.md",)


def tracked() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", *GLOBS],
        capture_output=True,
        text=True,
        check=False,
        cwd=REPO_ROOT,
    )
    return [line for line in result.stdout.splitlines() if line]


def linter() -> list[str] | None:
    """The argv prefix that runs slopvac, or None when it cannot be reached.

    The published release only. A `uvx --from <checkout>` fallback was here while slopvac was
    unpublished, and it is gone deliberately: a gate that silently builds one developer's working
    copy checks whatever that copy happens to say, which is not a gate.

    Absent means no gate rather than a failure, matching the policy the previous gate had. The
    wrapper says so on stderr, and `just lint` still passes -- prose is enforced at commit time
    and in CI, where the linter is installed.
    """
    if shutil.which("slopvac") is not None:
        return ["slopvac"]
    if shutil.which("uvx") is None:
        return None
    probe = subprocess.run(
        ["uvx", "slopvac", "--version"], capture_output=True, text=True, check=False
    )
    return ["uvx", "slopvac"] if probe.returncode == 0 else None


def lintable(paths: list[str]) -> list[str]:
    return [p for p in paths if p.endswith(".md") and p not in GENERATED]


def main() -> int:
    parser = argparse.ArgumentParser(prog="lint_prose.py", description=__doc__)
    parser.add_argument("paths", nargs="*", help="lint these instead of the tracked set")
    args = parser.parse_args()

    command = linter()
    if command is None:
        print("slopvac is not installed; skipping the prose gate", file=sys.stderr)
        return 0

    files = lintable(args.paths or tracked())
    if not files:
        return 0

    result = subprocess.run(
        [*command, *files],
        check=False,
        cwd=REPO_ROOT,
    )
    return 1 if result.returncode else 0


if __name__ == "__main__":
    raise SystemExit(main())
