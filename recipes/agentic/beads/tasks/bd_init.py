#!/usr/bin/env python3
"""Bootstrap beads in the destination repository.

    bd_init.py <dest> [--prefix P] [--dolt-sync git-origin|local-only] [--auto-export]

Wraps `bd init --init-if-missing --non-interactive --skip-hooks`, which exits 0 on a
second run rather than aborting.

`--skip-hooks` always. bd's five git hooks are reproduced as prek entries by
quality/hooks; letting bd install its own repoints core.hooksPath at .beads/hooks,
and that copy picks up whatever hook binaries are ambient.

`--skip-agents` never. It would remove the four codex lifecycle hooks and the Claude
SessionStart entry, which reload beads context after compaction.

bd appends its own lines to the root .gitignore with a header and no end marker.
base/gitignore rebuilds that file from .gitignore.d/, so those lines would be lost on
the next render. They are moved into a fragment here, which is where a rebuild reads
them from.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# What bd writes into the root .gitignore, as of bd 1.1.2. Kept as a fragment so
# base/gitignore's rebuild preserves it.
BD_HEADER = "# Beads / Dolt files (added by bd init)"

FRAGMENT = """\
# Beads. Written by bd init into the root .gitignore, moved here so
# base/gitignore's rebuild does not drop it.
#
# The Dolt database itself is ignored by .beads/.gitignore, which bd tracks.
.dolt/
*.db
.beads-credential-key
.beads/proxieddb/
"""


def run(command: list[str], dest: Path, *, required: bool = True) -> int:
    print(f"beads: {' '.join(command)}")
    code = subprocess.run(command, cwd=dest, check=False).returncode
    if code != 0 and required:
        print(f"beads: {' '.join(command)} failed with exit {code}", file=sys.stderr)
    return code


def move_gitignore_lines(dest: Path) -> None:
    """Take bd's block out of the root .gitignore and into a fragment.

    Leaving it in place would work until the next `base/gitignore` render, which
    rebuilds the whole file from its sources and would silently drop it.
    """
    (dest / ".gitignore.d").mkdir(exist_ok=True)
    (dest / ".gitignore.d" / "beads").write_text(FRAGMENT)

    root = dest / ".gitignore"
    if not root.is_file():
        return

    lines = root.read_text().splitlines(keepends=True)
    if not any(line.strip() == BD_HEADER for line in lines):
        return

    kept, dropping = [], False
    for line in lines:
        if line.strip() == BD_HEADER:
            dropping = True
            continue
        # bd writes no end marker, so the block runs to the next blank line.
        if dropping:
            if line.strip():
                continue
            dropping = False
            continue
        kept.append(line)

    root.write_text("".join(kept).rstrip("\n") + "\n")
    print("beads: moved bd's ignore lines into .gitignore.d/beads")


def agents_template(dest: Path) -> str:
    """The body bd should use, when docs/agents left one.

    `docs/agents` renders `docs/agents/AGENTS.body.md` as the index a repository's
    agents read first. Without it bd writes its own 127-line beads-only file, which
    would then be that index.
    """
    candidate = dest / "docs" / "agents" / "AGENTS.body.md"
    return str(candidate) if candidate.is_file() else ""


def derive_sync_remote(dest: Path) -> str:
    """Turn the git origin into a Dolt remote URL.

    The database travels over `refs/dolt/data` on the same remote the code lives on, so
    the URL is the git origin's with a `git+` scheme prefix. Without that prefix bd reads
    it as a plain remote rather than one over the git transport.
    """
    result = subprocess.run(
        ["git", "-C", str(dest), "remote", "get-url", "origin"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return ""

    url = result.stdout.strip()
    if not url:
        return ""
    # A scp-style address is not a URL, so it is normalised first: git@host:owner/repo.
    if url.startswith("git@"):
        host, _, path = url.partition(":")
        url = f"ssh://{host}/{path}"
    return url if url.startswith("git+") else f"git+{url}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dest", type=Path)
    parser.add_argument("--prefix", default="")
    parser.add_argument("--dolt-sync", default="git-origin", choices=["git-origin", "local-only"])
    parser.add_argument("--auto-export", action="store_true")
    parser.add_argument("--agents-template", default="")
    parser.add_argument("--sync-remote", default="")
    parser.add_argument("--dolt-auto-commit", default="")
    parser.add_argument("--push-command", default="")
    args = parser.parse_args(argv)

    dest = args.dest
    command = ["bd", "init", "--init-if-missing", "--non-interactive", "--skip-hooks"]
    if args.prefix:
        command += ["--prefix", args.prefix]
    # bd's own AGENTS.md is 127 lines carrying three overlapping beads blocks, and
    # its `minimal` profile is not minimal. Supplying the body keeps docs/agents in
    # charge of what a repository's agents read first, and bd still appends its one
    # marked block. Verified against bd 1.1.2: 29 lines rather than 127.
    template = args.agents_template or agents_template(dest)
    if template:
        command += ["--agents-template", template]
    if (code := run(command, dest)) != 0:
        return code

    if args.dolt_sync == "local-only":
        # A missing remote is the desired end state, so a failure here is not one.
        run(["bd", "dolt", "remote", "remove", "origin"], dest, required=False)

    # Every repository with beads sets sync.remote, surveyed across five. The
    # `git+ssh://` or `git+https://` prefix is what marks it a Dolt remote over the git
    # transport rather than a git remote, so a bare URL would be read as the wrong kind.
    remote = args.sync_remote or (
        derive_sync_remote(dest) if args.dolt_sync == "git-origin" else ""
    )
    if remote and (code := run(["bd", "config", "set", "sync.remote", remote], dest)):
        return code

    settings = [
        ("export.auto", "true" if args.auto_export else ""),
        ("dolt.auto-commit", args.dolt_auto_commit),
        # A direct `bd dolt push` hangs where the database runs in a container. Setting
        # this makes beads' own automatic push go through the wrapper instead.
        ("custom.bd-push-command", args.push_command),
    ]
    for key, value in settings:
        if value and (code := run(["bd", "config", "set", key, value], dest)):
            return code

    move_gitignore_lines(dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
