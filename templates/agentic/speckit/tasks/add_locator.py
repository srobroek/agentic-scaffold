#!/usr/bin/env python3
"""Add the speckit-conductor locator to apm.yml's dependency list.

    add_locator.py <dest> <locator>

The layer declares a dependency rather than vendoring one. Vendoring would fork an
actively released package, and nothing checks a copy across a repository boundary: a
drifted guard script is not recoverable the way a drifted generated file is.

Idempotent, and it edits rather than rewrites. `agentic/apm` owns apm.yml and carries a
`_skip_if_exists` on it, so a re-render must not lose a package a person added by hand.
The `[]` placeholder that layer writes for an empty list is replaced rather than appended
to, because a list cannot hold both.
"""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) < 3:
        print(__doc__, file=sys.stderr)
        return 2

    dest, locator = Path(sys.argv[1]), sys.argv[2]
    manifest = dest / "apm.yml"
    if not manifest.is_file():
        # agentic/apm may not have rendered. Saying so beats writing a manifest this
        # layer does not own.
        print("speckit: no apm.yml, so the locator was not added. Render agentic/apm first.")
        return 0

    body = manifest.read_text(encoding="utf-8")
    # Compare on the package path: the constraint after `#` differs between a pinned and
    # an unpinned form, and both mean the package is already declared.
    package = locator.split("#")[0]
    if package in body:
        print(f"speckit: {package} is already in apm.yml")
        return 0

    lines = body.splitlines()
    for index, line in enumerate(lines):
        if line.strip() != "apm:":
            continue

        # The empty-list placeholder, which cannot coexist with an entry.
        for offset in range(index + 1, len(lines)):
            stripped = lines[offset].strip()
            if stripped == "[]":
                lines[offset] = f"    - {locator}"
                manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
                print(f"speckit: added {locator} to apm.yml")
                return 0
            if stripped.startswith("-"):
                lines.insert(offset, f"    - {locator}")
                manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
                print(f"speckit: added {locator} to apm.yml")
                return 0
            if stripped and not stripped.startswith("#"):
                break

        lines.insert(index + 1, f"    - {locator}")
        manifest.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"speckit: added {locator} to apm.yml")
        return 0

    print("speckit: apm.yml has no `dependencies.apm` list; add the locator by hand:")
    print(f"  - {locator}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
