#!/usr/bin/env python3
"""Report which marketplaces to register and which packages suit the rendered tree.

    recommend.py <dest>

This layer writes nothing. Per-harness configuration comes from a marketplace, so no
`.claude/settings.json`, `.mcp.json`, `.codex/config.toml`, `marketplace.json`,
`opencode.json`, or kiro file is rendered here. Installing without saying so is the
thing the layer exists not to do, so the output is a report a person acts on.

Marketplace registration is machine-global rather than per-project: `apm marketplace add`
writes to `~/.claude/plugins/`, so no template can seed it and it is a one-time step per
machine. A dependency locator carries its own source inline, so a package resolves
whether or not its marketplace was registered.

Detection reads the tree, never the answers. A layer's answers file records what was
asked, while what actually rendered is what a recommendation should follow: a layer can
be rendered and then have its files removed by hand, and the tree is what an agent will
find.

The match from a rendered layer to a package is stated per layer below rather than
inferred. Anything requiring judgement, which package suits an unusual framework or
whether a repository wants a given MCP server, stays with the agent reading this report.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Marketplaces worth registering once per machine. `agentic/apm` names the apm two in
# its own recipe; they are repeated here because this report is what a person reads
# after a render, and a report that omits the prerequisite is a report they cannot act
# on. Each row carries the registration command, because apm and OMP register through
# different CLIs.
MARKETPLACES = (
    (
        "apm marketplace add srobroek/agentic-packages",
        "the language, quality, steering, and agent packages",
    ),
    ("apm marketplace add srobroek/slopvac", "write-docs and review-docs, the prose gate"),
    (
        "omp plugin marketplace add srobroek/omp-plugins",
        "the OMP plugin catalog: beads, delivery, speckit, per-language rules. OMP reads "
        ".omp-plugin/ and falls back to .claude-plugin/, so one repo serves both",
    ),
)

# What a rendered layer implies. A tuple of (locator, why) per detected layer, so the
# report says what a package is for rather than only naming it.
#
# Keyed on a path the layer writes rather than on its answers file: a layer whose files
# were removed by hand should stop being recommended against.
BY_MARKER: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "rust-toolchain.toml",
        (
            ("srobroek/agentic-packages/packages/language-rust", "rust idiom and review rules"),
            (
                "srobroek/agentic-packages/packages/rust-quality",
                "clippy, cargo-deny, and nextest conventions",
            ),
        ),
    ),
    (
        "ruff.toml",
        (
            ("srobroek/agentic-packages/packages/language-python", "python idiom and review rules"),
            (
                "srobroek/agentic-packages/packages/python-quality",
                "ruff, ty, and pytest conventions",
            ),
        ),
    ),
    (
        "biome.json",
        (
            (
                "srobroek/agentic-packages/packages/language-typescript",
                "typescript idiom and review rules",
            ),
            (
                "srobroek/agentic-packages/packages/typescript-quality",
                "biome, oxlint, and vitest conventions",
            ),
        ),
    ),
    (
        ".golangci.yml",
        (("srobroek/agentic-packages/packages/language-go", "go idiom and review rules"),),
    ),
    (
        "infra/versions.tf",
        (
            (
                "srobroek/agentic-packages/packages/steering-infrastructure",
                "OpenTofu and cloud steering, which the terraform layer's own files do not carry",
            ),
        ),
    ),
    (
        ".projenrc.ts",
        (
            (
                "srobroek/agentic-packages/packages/steering-infrastructure",
                "the same steering applies to a CDK app",
            ),
        ),
    ),
    (
        "repomix.config.json",
        (
            (
                "srobroek/agentic-packages/packages/token-savings",
                "REQUIRED by agentic/index: it guards a whole-file read of the pack, which"
                " costs six context windows on a large repository",
            ),
        ),
    ),
    (
        ".beads",
        (
            (
                "srobroek/agentic-packages/packages/beads",
                "the bd workflow rules and wisp conventions",
            ),
        ),
    ),
    (
        "openapi.yaml",
        (("srobroek/agentic-packages/packages/language-api", "contract-first review rules"),),
    ),
    (
        ".moon/workspace.yml",
        (
            (
                "srobroek/agentic-packages/packages/steering-monorepo",
                "how to reason about a member graph rather than a flat tree",
            ),
        ),
    ),
)

# Always worth having, whatever rendered.
ALWAYS = (
    (
        "srobroek/slopvac/packages/write-docs",
        "the prose rules every document here is written against",
    ),
    ("srobroek/agentic-packages/packages/core", "the shared agent conventions the rest build on"),
)


def detected(dest: Path) -> list[tuple[str, str]]:
    """Every recommendation the tree earns, deduplicated, in declaration order."""
    found: list[tuple[str, str]] = list(ALWAYS)
    seen = {locator for locator, _ in found}

    for marker, packages in BY_MARKER:
        if not (dest / marker).exists():
            continue
        for locator, why in packages:
            if locator in seen:
                continue
            found.append((locator, why))
            seen.add(locator)
    return found


def already_listed(dest: Path) -> set[str]:
    """Locators apm.yml already names, so the report does not repeat them.

    Read as text rather than parsed: a locator carries a version constraint after `#`,
    and the comparison is on the package path.
    """
    manifest = dest / "apm.yml"
    if not manifest.is_file():
        return set()
    body = manifest.read_text(encoding="utf-8")
    return {
        line.strip().lstrip("-").strip().strip("\"'").split("#")[0]
        for line in body.splitlines()
        if line.strip().startswith("-") and "/packages/" in line
    }


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__, file=sys.stderr)
        return 2
    dest = Path(sys.argv[1])

    print()
    print("agentic/marketplace: nothing was written. What follows is a recommendation.")
    print()

    print("Register these once per machine (`just apm-marketplaces` covers the apm two):")
    for command, why in MARKETPLACES:
        print(f"  {command}")
        print(f"      {why}")
    print()

    listed = already_listed(dest)
    recommended = detected(dest)
    missing = [(locator, why) for locator, why in recommended if locator not in listed]

    if not missing:
        print("Every package the rendered layers imply is already in apm.yml.")
    else:
        print("Add these to `apm.yml` under `dependencies.apm`, then `just apm-install`:")
        for locator, why in missing:
            print(f"  - {locator}")
            print(f"      {why}")
    print()

    if listed:
        print(f"apm.yml already names {len(listed)} package(s).")
        print()

    # Said out loud because the layer's value is the absence of these files, and an
    # absence is invisible in a render log.
    print("This layer wrote no per-harness configuration: no .claude/settings.json,")
    print(".mcp.json, .codex/config.toml, marketplace.json, opencode.json, or .kiro/.")
    print("Those come from a marketplace, which is machine-global rather than per-repo.")
    print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
