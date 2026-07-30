# Profiles

One file per shape, derived from a survey of 54 repositories. A profile names its layer
set, its generator, the answers that are fixed or derived for the shape, and the commands
that prove a rendered tree is a working project.

`scripts/profiles.py --check` validates every file against `templates/`, so a layer
renamed or removed breaks here rather than during a render.

## The shapes

| Profile | Survey count | Generator |
|---|---|---|
| `agentic-repo` | 17 | none |
| `rust-lib`, `rust-app` | 12 combined | `cargo new [--lib]` |
| `rust-gui` | 3 | `cargo new`, then `create-tauri-app` |
| `python-lib`, `python-app` | 10 combined | `uv init [--lib]` |
| `go-lib`, `go-app` | 1 combined | `go mod init` |
| `ts-lib`, `ts-app`, `ts-tui` | 7 combined | `bun init` or `create-better-t-stack` |
| `terraform` | none surveyed | none |
| `cdk` | none surveyed | `projen new awscdk-app-ts` |

`agentic-repo` is the largest shape and the one the old catalog had no name for: a
repository whose product is skills, agents, or a marketplace, with no language layer.

## The monorepo axis

Monorepo is an axis rather than a profile. Any profile crosses it by adding
`workspace/monorepo` before `lang/*` and `workspace/moon` after `workspace/just`, plus the
`layout` and `members` answers. `just add <name> <lang>` then renders a language layer at
the member path.

`rust-gui` is the one profile that is a monorepo by construction, since the Tauri shell is
a TypeScript package beside a Rust core. `go-app` never crosses it: a go monorepo is one
module with a directory per member, so there is no workspace manifest to render.

The order is not cosmetic. In a monorepo the generator runs AFTER `workspace/monorepo`,
because `cargo init .` writes a `[package]` root, the layer then skips the manifest it
finds, and no `[workspace]` section is ever written. A single repository keeps
generator-first.

## Format

```yaml
name: <profile>
summary: <one line>
generator: <command, or `none`>
layers: [<group/layer>, ...]   # in render order
answers: {<key>: <value>}      # fixed or derived for this shape
build: [<command>, ...]        # each runs in the destination and must exit 0
```

`layers` is ordered, and the order is the one `docs/layers.md` states. A layer that reads
what an earlier one wrote has to appear after it, which is why `quality/hooks` follows
`iac/*` and `base/gitignore` follows everything that contributes a fragment.

`build` is what makes the check meaningful. A tree that renders is not a project that
builds, so each profile names its own resolve, install, or compile step rather than a
shared one.
