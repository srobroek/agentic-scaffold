#!/usr/bin/env python3
"""Refuse to render when the tooling or the destination is not ready.

    precheck.py <dest>

This is the only precheck in the catalog. `base/repo` renders before every other
layer, so failing here costs nothing, where failing halfway through leaves a
half-scaffolded tree.

Exit 0 to proceed, non-zero with a reason on stderr to stop.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Needed by the layers themselves, not by a generator a profile happens to pick.
REQUIRED = {
    "git": "version control",
    "just": "the task surface every layer contributes recipes to",
    "gitnr": "concatenates the gitignore sources in base/gitignore",
}

OPTIONAL = {
    "mise": "pins the toolchain; without it versions come from PATH",
    "prek": "installs the git hooks quality/hooks configures",
}


def main() -> int:
    dest = Path(sys.argv[1]) if len(sys.argv) > 1 else Path.cwd()

    missing = [f"{name} ({why})" for name, why in REQUIRED.items() if shutil.which(name) is None]
    if missing:
        print("missing required tooling:", file=sys.stderr)
        for item in missing:
            print(f"  {item}", file=sys.stderr)
        return 1

    absent = [name for name in OPTIONAL if shutil.which(name) is None]
    if absent:
        print(f"note: {', '.join(absent)} absent from PATH", file=sys.stderr)

    if dest.exists() and not dest.is_dir():
        print(f"destination is not a directory: {dest}", file=sys.stderr)
        return 1

    # Rendering over uncommitted work is unrecoverable: copier overwrites, and
    # there is no diff to review afterwards.
    if (dest / ".git").exists():
        result = subprocess.run(
            ["git", "-C", str(dest), "status", "--porcelain"],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode == 0 and result.stdout.strip():
            print(
                f"{dest} has uncommitted changes. Commit or stash them first: "
                "copier overwrites and leaves no diff to review.",
                file=sys.stderr,
            )
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
