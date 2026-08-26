#!/usr/bin/env python3
"""Settle the release-type from the tree when the answer left it empty.

    detect_release_type.py <dest> <release-type>

release-please's release-type decides which file the version is written into,
so it has to match the language: node edits package.json, python
pyproject.toml, rust Cargo.toml, go a version file. The rendered tree already
says which of those exists, so an empty answer reads the same markers the
gitignore fold reads, and `simple` -- version.txt alone -- is the fallback for
a tree with no language at all, which is what an agentic or terraform
repository is.

Guarded to the empty answer: an explicit release-type was rendered into the
config directly and is never rewritten here.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

MARKERS = (
    ("rust-toolchain.toml", "rust"),
    ("pyproject.toml", "python"),
    ("package.json", "node"),
    ("go.mod", "go"),
)


def detected(dest: Path) -> str:
    for marker, release_type in MARKERS:
        if (dest / marker).is_file():
            return release_type
    return "simple"


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    dest = Path(sys.argv[1])
    if sys.argv[2].strip():
        return 0  # answered explicitly; the template rendered it already

    config = dest / "release-please-config.json"
    if not config.is_file():
        print("no release-please-config.json here, nothing to settle")
        return 0

    payload = json.loads(config.read_text())
    release_type = detected(dest)
    if payload.get("release-type") != release_type:
        payload["release-type"] = release_type
        config.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"release-type settled to {release_type}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
