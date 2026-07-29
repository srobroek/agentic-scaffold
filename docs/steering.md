---
status: accepted
date: 2026-07-29
---

# Steering generation

What `docs/agents/` holds in a scaffolded repository, and which parts a
generator owns.

## Layout

One directory per concern. Each has an index, and concerns that vary by language
have one leaf per language.

```
docs/agents/
  index.md                    commands, toolchain pins, layout, structural tool
  conventions.md              error handling, logging, ownership boundaries
  quality/index.md
  quality/{rust,python,ts,go,terraform,cross-cutting}.md
  ci/index.md
  ci/{github,gitlab}.md
  release/index.md
  testing/index.md
  docs/index.md
  env/index.md
  gotchas/index.md
  gotchas/{rust,python,ts,go,ci,tooling}.md
```

Adding a language adds `quality/<lang>.md` and `gotchas/<lang>.md` plus one line
in each index. No existing file grows.

## Ownership

| Path | Generated | Hand-written |
|---|---|---|
| `index.md` | all | none |
| `quality/*` | what each tool enforces, and the command | why a rule is off |
| `ci/*` | job graph, merge gates, local reproduction | none |
| `release/index.md` | tool, tag format, publish targets | pull request title rules |
| `testing/index.md` | test directories, runners, single-test invocation | what is expected before review |
| `docs/index.md` | topology, deploy trigger, generated versus authored | none |
| `env/index.md` | variable names from CI and configuration | what fails without each |
| `conventions.md` | none | all |
| `gotchas/*` | none | all |

Generated content sits between markers:

```markdown
<!-- BEGIN GENERATED: quality-rust -->
<!-- END GENERATED -->
```

The generator replaces marked blocks and leaves everything else. A file with no
marker is never written after it is first created, which is why `conventions.md`
and `gotchas/*` survive.

## Sources

| Output | Read from |
|---|---|
| `index.md` | rendered layer set, `mise.toml`, `rust-toolchain.toml`, workspace manifest |
| `quality/rust.md` | `clippy.toml`, `[lints]` in `Cargo.toml`, `rustfmt.toml`, `deny.toml` |
| `quality/python.md` | `ruff.toml`, type checker configuration |
| `quality/ts.md` | `biome.json`, `.oxlintrc.json` |
| `quality/go.md` | `.golangci.yml` |
| `quality/terraform.md` | `.tflint.hcl`, trivy configuration |
| `quality/cross-cutting.md` | `.pre-commit-config.yaml`, `typos.toml`, cspell configuration |
| `ci/*` | the rendered workflow files |
| `release/index.md` | `release-please-config.json` or `cog.toml` |
| `testing/index.md` | test directories on disk, runner configuration |
| `env/index.md` | `env:` keys in workflows, `.env.example` |

`env/index.md` records names. Values never enter it.

## Index files

`AGENTS.md` and `CLAUDE.md` stay an index. Both are produced by `apm compile`
from `.apm/` primitives, so the generator writes `.apm/context/*.context.md`
pointers into `docs/agents/` and runs `apm compile` last.

Directory structure is not documented. gitnexus and repomix answer structural
questions, and `index.md` names which of the two this repository has.

### Each block stands alone

Every tool appending to `AGENTS.md` owns one block, and each block is complete
on its own. Removing any one of them leaves the rest accurate, because no block
depends on another for context. A row in the index table names a file that
exists; a reader who drops the beads block still finds every document.

`AGENTS.md` is the only agent index. `CLAUDE.md` is a symlink to it, tracked by
git as mode `120000`, so a tool appending to `AGENTS.md` is visible through both
names and neither can drift from the other.

The layer supplies the `AGENTS.md` body, then each tool appends its own block:

```sh
bd init --prefix <p> --non-interactive --skip-hooks --skip-agents
ln -s AGENTS.md CLAUDE.md
bd setup codex                      # appends one managed block to AGENTS.md
```

`--skip-agents` is required. Without it `bd init` writes a 127-line `AGENTS.md`
carrying three overlapping beads blocks, and its `minimal` profile is not
minimal. `bd setup <recipe>` appends exactly one block and is idempotent on
re-run. `bd setup -o <path>` writes the block elsewhere, and
`bd init --agents-template <file>` supplies the body instead of a hand-written
file, whichever suits the layer.

`--skip-hooks` is equally required. Without it `bd init` copies the ambient hook
binaries from the configured `core.hooksPath` into `.beads/hooks`, repoints
`core.hooksPath` at the copy, and stages the result. Observed on macOS with a
hooks path owned by another tool: the copied `pre-commit` was 24MB with an
unusable arm64 slice, and every commit failed with `cannot execute binary file`.

`.beads/.gitignore` gets a `hooks/` line so a later `bd` invocation cannot stage
them either.

## Freshness

`just docs:agents` regenerates in place. `just docs:agents --check` regenerates
into a temporary directory and exits non-zero on a difference, naming each stale
file and the command that fixes it.

That check runs inside the quality job. A workflow of its own would be gated on
paths, and a workflow that never runs leaves a required check pending forever.

## Skills

| Skill | Reads | Writes | Network |
|---|---|---|---|
| `project-scaffold` | interview answers, templates | a new repository | yes |
| `project-scaffold-steering` | configuration on disk | marked blocks in `docs/agents/` | no |
| `project-scaffold-update` | templates, repository state | layers and marked blocks | yes |

`project-scaffold-steering` takes no arguments and asks nothing. Given the same
files on disk it produces the same output, which is what lets CI verify it.

`project-scaffold-update` handles a new layer, a template change landing in an
existing repository, and retrofitting a repository scaffolded before this
existed.

Duplication and token-budget judgements belong to the `audit-steering` skill.
The generator produces content and defers to it.
