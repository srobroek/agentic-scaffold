---
name: project-scaffold
description: Scaffold a new project or repository in any language from composable layers. Use when asked to set up, start, spin up, stand up, initialize, or bootstrap a project, service, API, app, or repo, or to add a monorepo member.
---

# Project scaffold

Render a working project from a profile: run the interview, derive what is derivable,
run the generator, then render the layer set in order.

Ask six questions and no more. Everything else is fixed in a layer or derived from
`rules/choices.md`. Asking a derived question wastes a turn and invites an answer that
contradicts the tree.

## The interview

One question at a time, in this order. Each answer narrows the next.

1. **What are you building?** Name plus one line.
2. **Which language?** rust, python, go, ts, or none for an agentic repository.
3. **One package, a monorepo, or several repos?**
4. **Licence.** State the derived answer and accept an override.
5. **Create the remote now?**
6. **Private or public**, if yes. Read a public answer back before running: `gh repo
   create --public` publishes immediately and is indexed.

## Pick the profile

`profiles/*.yml`, one per shape. `just profiles` lists them.

| Answer | Profile |
|---|---|
| no language, product is skills or agents | `agentic-repo` |
| rust library / binary / Tauri desktop | `rust-lib` / `rust-app` / `rust-gui` |
| python library / service | `python-lib` / `python-app` |
| go library / service | `go-lib` / `go-app` |
| ts library / web app / terminal app | `ts-lib` / `ts-app` / `ts-tui` |
| infrastructure only | `terraform` |
| AWS CDK | `cdk` |

The profile carries its own `layers`, `generator`, `answers`, and `build`. Read the file
rather than assembling a layer set by hand.

## Render

```bash
just render-profile <profile> <dest>     # renders the layer set and runs the build
just render <group>/<layer> <dest>       # one layer, when adjusting afterwards
just preview <group>/<layer> <dest>      # what a layer would write, writing nothing
```

`render-profile` does not run the generator. Run it yourself first, from the profile's
`generator` field, then render.

Order matters and the profile states it. The cases that bite:

- **In a monorepo the generator runs AFTER `workspace/monorepo`.** `cargo init .` writes a
  `[package]` root, the layer then skips the manifest it finds, and no `[workspace]`
  section is ever written, so the repository silently is not a workspace. A single
  repository keeps generator-first.
- **A fragment contributor precedes its aggregator.** `workspace/just` writes its import
  block from `.just.d/`, and `base/gitignore` rebuilds `.gitignore` from `.gitignore.d/`,
  so a layer rendering afterwards leaves a generated file stale.

Commit after each layer. `base/repo`'s precheck refuses a destination with uncommitted
changes, because copier overwrites and leaves no diff to review.

## After rendering

```bash
just setup            # toolchain, dependencies, hook shims
just check            # what CI runs
```

Then report: every file written, and every command that failed with its own output. A
summary that says "done" hides a failed build.

Recommend packages last. `agentic/marketplace` reads the finished tree and prints what to
register and install; it writes nothing, because per-harness configuration comes from a
marketplace and registration is machine-global.

## Rules

- Ask six questions. `rules/choices.md` marks everything else fixed or derived.
- Read the profile. Do not assemble a layer set by hand.
- A repository takes either `agentic/apm` or `agentic/package`, never both: they own the same
  `apm.yml`. `agentic/package` is the publisher, for a marketplace repository.
- Never run a generator that reaches the network without saying so first.
- Read a public repository name, owner, and visibility back before creating it.
- Verify by running the real tool against the rendered output, not by reading the template.
  Every defect found while building these layers rendered cleanly first.
- `just add <name> <lang>` adds a monorepo member. It renders the language layer at the
  member path and registers it, so do not patch the workspace manifest by hand.
