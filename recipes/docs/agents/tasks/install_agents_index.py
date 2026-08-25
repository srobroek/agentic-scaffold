#!/usr/bin/env python3
"""Install AGENTS.md from the rendered body, and point CLAUDE.md at it.

    install_agents_index.py <dest>

`docs/agents/AGENTS.body.md` is the body this layer owns. AGENTS.md is a copy of it
rather than a symlink, because `agentic/beads` appends a marked block to AGENTS.md and
a symlink would write that block back into the body.

CLAUDE.md is a relative symlink to AGENTS.md, so one file serves both harnesses.
A relative target keeps the link valid inside a linked worktree and after a clone.

Idempotent, and non-destructive: an AGENTS.md that already carries the body is left
alone, so a beads block appended after the first render survives.
"""

from __future__ import annotations

import sys
from pathlib import Path

MARKER = "## Read for"


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2

    dest = Path(sys.argv[1])
    body = dest / "docs" / "agents" / "AGENTS.body.md"
    if not body.is_file():
        print("docs/agents: no AGENTS.body.md, nothing to install", file=sys.stderr)
        return 3

    index = dest / "AGENTS.md"
    if index.is_file() and MARKER in index.read_text():
        print("AGENTS.md already carries the body, leaving it alone")
    else:
        # A pre-existing AGENTS.md without the body is bd's own, or another tool's.
        # The body goes first so it is what a reader sees, and any marked block that
        # follows is preserved.
        existing = index.read_text() if index.is_file() else ""
        index.write_text(body.read_text() + ("\n" + existing if existing.strip() else ""))
        print("wrote AGENTS.md from docs/agents/AGENTS.body.md")

    link = dest / "CLAUDE.md"
    if link.is_symlink():
        if link.readlink() == Path("AGENTS.md"):
            return 0
        link.unlink()
    elif link.exists():
        # A regular file here is bd's copy. AGENTS.md already carries what matters,
        # so replacing it with the link loses nothing.
        link.unlink()

    link.symlink_to("AGENTS.md")
    print("CLAUDE.md -> AGENTS.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
