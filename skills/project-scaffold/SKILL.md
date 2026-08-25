---
name: project-scaffold
description: Scaffold a new project or repository in any language from composable recipes. Use when asked to set up, start, initialize, or bootstrap a project, service, API, app, or repo, or to add a monorepo member.
---

# Project scaffold

Interview, derive, plan, render. From a scaffold checkout, one CLI renders:

```bash
uv run scripts/scaffold.py <list|check|plan|render|check-answers|update>
```

## Interview

Six questions, one per turn. `rules/choices.md` fixes or derives everything else, and a
question it already answers invites a reply that contradicts the tree.

1. **What are you building?** Name plus one line.
2. **Which language?** rust, python, go, ts, or none for an agentic repository.
3. **One package, a monorepo, or several repos?**
4. **Licence.** State the derived answer and accept an override.
5. **Create the remote now?**
6. **Private or public**, if yes.

Classify before asking. An answer is **strong** when the user stated it or
`rules/choices.md` derives it, and a **gap** otherwise. Grill the gaps, one question per
turn, because each answer narrows the next. Read a choice question's options verbatim from
that recipe's `copier.yml`. `base/license` carries thirteen, and copier rejects a value
recalled from anywhere else.

## Propose the recipe set

`scaffold list` prints every recipe and profile with its summary. Two mappings the summaries
do not give away: no language, where the product is skills or agents, is `agentic-repo`, and
rust plus a Tauri desktop shell is `rust-gui`.

Read the profile for its `layers`, `generator`, `answers`, and `build`. Then propose
enablement as one numbered table. Mandatory holds the profile's own `layers`. Recommended
holds what the answers imply. Optional holds what the user may decline, with the cost of
declining. Wait for them to confirm that table.

## Answers

The CLI never prompts. Every answer goes in one YAML file passed as `--data-file`, with
`--data key=value` for a single override, so a missing answer is a preflight finding rather
than a question the tool asks. The preflight runs before every render:

```bash
uv run scripts/scaffold.py check-answers --profile <profile> --data-file answers.yml
```

It reports every gap at once, as `Provide a value for '<key>' in recipe '<id>'`. Re-ask
exactly those keys. Render once it prints `answers complete`.

**A secret-shaped value never reaches the answers file.** The shapes: `ghp_`, `gho_`, `sk-`,
`AKIA`, `ASIA`, `glpat-`, `xox[baprs]-`, and a PEM header. Refuse to persist it, say the
credential now sits in a transcript and has to be rotated, and leave the key a gap. A secret
belongs in the environment or a secret manager, and `docs/agents/env/index.md` records the
variable name and what fails without it, never a value.

## Record the run in beads

Where the destination has beads, pour the run before rendering:

```bash
bd mol pour mol-scaffold-run --var feature=<slug> --var profile=<profile>
bd update <root-id> --metadata '{"dest":"<dest>"}'
```

Create one task bead per selected recipe under `<root>.render`, in profile order, each
blocking the next. Four steps are human gates that only `bd gate resolve` closes: plan
approval, remote creation, secrets, and marketplace installs. Remote creation resolves before
secrets, because a repository secret needs the repository. A gate with nothing to approve is
resolved on that reason rather than skipped.

Pour with `--var autonomous=yes` where no human can answer: the plan gate drops out and the
secrets gate still stalls, which is what it is for. A destination without beads degrades to a
plain run: warn once, then carry on.

## Render

Plan first, and show the plan before anything touches disk:

```bash
uv run scripts/scaffold.py plan --profile <profile> --dest <dest> --data-file answers.yml
```

Each row is a path, its owning recipes, and its class: `create`, `overwrite`, `skip`, or
`answers`. Exit 5 is a `conflict`, where two recipes own one path. Stop, name both owners, and
either drop one recipe or declare the path under `_skip_if_exists` in the later one so the
first writer wins. `--force` renders past a conflict and is the user's call to make.

Run the profile's `generator` yourself. `render` does not run it.

```bash
uv run scripts/scaffold.py render --profile <profile> --dest <dest> --data-file answers.yml
```

It git-inits the destination, commits per recipe, and records the scaffold HEAD as `_ref` in
each `.copier-answers.<recipe>.yml`, which is what `project-scaffold-update` replays.

Order comes from the profile, and `scaffold check` proves it. Two cases bite:

- **In a monorepo the generator runs after `workspace/monorepo`.** `cargo init .` writes a
  `[package]` root, the recipe then skips the manifest it finds, no `[workspace]` section is
  written, and the repository silently is not a workspace. A single package keeps
  generator-first.
- **A fragment contributor precedes its aggregator.** `workspace/just` folds `.just.d/`,
  `quality/hooks` folds `.pre-commit.d/`, and `base/gitignore` rebuilds `.gitignore` from
  `.gitignore.d/`.

## After rendering

Run `just setup` in the destination for the toolchain, the dependencies, and the hook shims,
then `just check` for what CI runs. Report every file written, and every command that failed
with its own output: a summary saying "done" hides a failed build.

Recommend packages last. `agentic/marketplace` reads the finished tree and prints what to
register and install, writing nothing, because registration is machine-global.

## Rules

- Ask six questions. `rules/choices.md` marks the rest fixed or derived.
- A repository takes either `agentic/apm` or `agentic/package`, never both. Both write
  `apm.yml` and the second skip-guards it, so the plan reports `skip` rather than refusing,
  and whichever renders first silently owns the manifest.
- Say a generator reaches the network before running it.
- Read a public repository's name, owner, and visibility back before
  `gh repo create --public`, which publishes immediately.
- Verify by running the real tool against rendered output, not by reading the recipe. Every
  defect found while building these recipes rendered cleanly first.
- `just add <name> <lang>` adds a monorepo member: it renders the language recipe at the
  member path and registers it in the workspace manifest.
