#!/usr/bin/env python3
"""Put back the comments release-please strips from apm.yml.

    restore_apm_comments.py [--check]

release-please rewrites apm.yml to set `version`, and its YAML writer drops every comment in the
file. At 0.2.0 that silently removed the note explaining why kiro is a deploy target but not a
marketplace output -- the distinction `agentic/package` exists to keep, and the one thing about
this manifest a reader cannot infer from the keys.

Called by `just release-restore`, which the release workflow runs after the bump and before it
amends the release branch. Idempotent, so running it on an untouched file changes nothing.

`--check` reports without writing, which is what the test uses.

Exit codes:
    0  the comments are present, or were restored
    1  under --check, a comment is missing
    2  apm.yml is absent or has no `targets:` key to anchor against
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MANIFEST = REPO_ROOT / "apm.yml"

# Each entry is the line it goes above, and the comment block itself. Anchoring on a key rather
# than a line number survives release-please reordering or reflowing the file.
BLOCKS = (
    (
        "targets:\n",
        """# Where compiled skills and steering deploy. kiro is a target rather than a marketplace
# output, because apm ships no kiro marketplace mapper.
#
# release-please rewrites this file to bump `version` and its YAML writer drops comments, so
# these were lost once already at 0.2.0. `just release-restore` puts them back, and
# test_the_kiro_rationale_survives_a_release fails when neither happened.
""",
    ),
)


# The phrase each block is identified by, so a reworded block is not duplicated.
def present(body: str, block: str) -> bool:
    first = block.splitlines()[0].lstrip("# ").rstrip()
    return first in body


def main() -> int:
    parser = argparse.ArgumentParser(prog="restore_apm_comments.py", description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    if not MANIFEST.is_file():
        print(f"no {MANIFEST.relative_to(REPO_ROOT)}", file=sys.stderr)
        return 2

    body = MANIFEST.read_text()
    missing = []

    for anchor, block in BLOCKS:
        if present(body, block):
            continue
        if anchor not in body:
            print(f"cannot anchor on {anchor.strip()!r}", file=sys.stderr)
            return 2
        missing.append(anchor)
        if not args.check:
            body = body.replace(anchor, block + anchor, 1)

    if args.check:
        if missing:
            print("apm.yml is missing its comments; run: just release-restore", file=sys.stderr)
            return 1
        return 0

    if not missing:
        print("apm.yml comments already present")
        return 0

    MANIFEST.write_text(body)
    print(f"restored {len(missing)} comment block(s) in apm.yml")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
