#!/usr/bin/env python3
"""Add the dev dependencies the configs this layer writes require.

    add_dev_deps.py <dest> <type-aware>

`bun add -d` rather than editing package.json, so bun resolves the versions and
writes the lockfile.

`oxlint-tsgolint` is separate from `oxlint` and is what makes type-aware mode
work. Without it a config carrying `options.typeAware: true` fails with "Failed to
find tsgolint executable", so the layer must not write that option without also
installing the package.

It then runs `biome check --write` once. `bun init` writes an `index.ts` with no
trailing newline, which the formatter rejects, so a fresh scaffold fails its own
gate before a line is written.

Skips a package already present, so a second render adds nothing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

BASE = ("@biomejs/biome", "oxlint", "typescript", "knip")
TYPE_AWARE = ("oxlint-tsgolint",)

TIMEOUT_SECONDS = 180


def installed(manifest: Path) -> set[str]:
    if not manifest.is_file():
        return set()
    try:
        payload = json.loads(manifest.read_text())
    except json.JSONDecodeError:
        return set()
    names: set[str] = set()
    for field in ("dependencies", "devDependencies", "peerDependencies"):
        section = payload.get(field)
        if isinstance(section, dict):
            names.update(section)
    return names


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    dest = Path(sys.argv[1])
    type_aware = sys.argv[2].strip().lower() in {"true", "1", "yes"}

    manifest = dest / "package.json"
    if not manifest.is_file():
        print("no package.json here, nothing to add")
        return 0

    if shutil.which("bun") is None:
        print("bun absent from PATH, skipping the dev dependencies", file=sys.stderr)
        return 0

    wanted = list(BASE) + (list(TYPE_AWARE) if type_aware else [])
    missing = [name for name in wanted if name not in installed(manifest)]
    if not missing:
        print("every dev dependency is already present")
        return 0

    result = subprocess.run(
        ["bun", "add", "-d", *missing],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise SystemExit(f"bun add failed: {detail}")

    print(f"added {', '.join(missing)}")

    # `bun init`'s index.ts has no trailing newline, which biome's formatter
    # rejects, so normalise what the scaffold wrote before anyone runs the gate.
    formatted = subprocess.run(
        ["bunx", "biome", "check", "--write", "--no-errors-on-unmatched", "."],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )
    if formatted.returncode == 0:
        print("formatted the scaffold with biome")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
