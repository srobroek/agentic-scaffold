#!/usr/bin/env python3
"""Refuse a destination where `bd init` cannot work.

    precheck.py <dest>

`bd init` stores issues in an embedded Dolt database under `.beads/` and reads the
repository's git config, so it aborts outside a work tree. Failing here keeps the
render from writing a partial layer.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path


def main() -> int:
    dest = Path(sys.argv[1] if len(sys.argv) > 1 else ".")

    if shutil.which("bd") is None:
        print("beads: bd is not on PATH", file=sys.stderr)
        return 1

    result = subprocess.run(
        ["git", "-C", str(dest), "rev-parse", "--is-inside-work-tree"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip() != "true":
        print(
            f"beads: {dest} is not a git repository. Run 'git init' there first.",
            file=sys.stderr,
        )
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
