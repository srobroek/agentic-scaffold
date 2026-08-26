---
name: project-scaffold
description: Scaffold a new project or repository in any language from composable recipes. Use when asked to set up, start, initialize, or bootstrap a project, service, API, app, or repo, or to add a monorepo member.
---

# Project scaffold

Interview, derive, plan, render. One CLI renders everything, from a checkout resolved
in order: a development checkout when present; else **this skill's own plugin install**
(two levels above this SKILL.md, verified by `recipes/`); else clone `srobroek/agentic-scaffold`.

```bash
# --project resolves the CLI's environment wherever the destination is; first run creates it.
uv run --project "$SCAFFOLD" python "$SCAFFOLD/scripts/scaffold.py" <list|check|plan|render|check-answers|update>
```

## Interview

A short opening round, one question per turn. `rules/choices.md` fixes or derives
everything else, and a question it already answers invites a reply that contradicts
the tree.

1. **What are you building?** Name plus one line.
2. **Which language?** rust, python, go, ts, or none for an agentic repository.
3. **One package, a monorepo, or several repos?**
4. **Licence.** Recommend one with its tradeoff (`rules/choices.md` lists the starting
   points) and ask -- never derived, the choice is the user's.
5. **Create the remote now?**
6. **Private or public**, if yes.

More where the answers demand them, all in `rules/choices.md`. Ask `api` and `database`
for a `ts-app`: a CLI or a static site needs neither, and no project name says which. Ask
about infrastructure where the first answer implies it. Marketplaces are asked at the
install gate, when registering is imminent, not here.

Classify before asking: an answer is **strong** when the user stated it IN THIS
conversation or `rules/choices.md` derives it from one, a **gap** otherwise. Memory,
stored preferences, and tool lookups (a gh login, a past project's licence) are
RECOMMENDATIONS: offer them as the default in the question, never record one as
decided -- what the user often chooses is still theirs to choose. Read a choice
question's options verbatim from that recipe's `copier.yml`. Licence answers are open
strings: normalise the obvious, say the correction, do not ask -- `apache2` is
`Apache-2.0`. A miss lists every SPDX key GitHub carries; correct and re-render.

## Grill the shape

The rounds above settle what the tool derives; what the application IS gets grilled
before the recipe set is proposed. Work the open decisions in rounds:

- A round is every question whose prerequisites are settled, numbered, each carrying
  your recommended answer so one word accepts it.
- A question belongs to the recipe that asks it, so a recipe's selection is a
  prerequisite for every question in its `copier.yml`. An either/or between recipes
  (iac/terraform vs iac/cdk) is a round of exactly that one question; the winner's
  keys enter a later round, never the same one.
- In scope: the generator's axes (`generator_answers`: frontend, backend, runtime, api,
  addons), auth and persistence, deployment target, the host contacts.
- Not here: marketplaces stay at the install gate, where registering is imminent.
- Out of scope: anything a tree, toolchain, or rule derives, and any padding question
  `check-answers` would not report.
- Stop when the frontier is empty.

## Propose the recipe set

`scaffold list` prints every recipe and profile with its summary. Two mappings the summaries
do not give away: no language, where the product is skills or agents, is `agentic-repo`, and
rust plus a Tauri desktop shell is `rust-gui`.

Read the profile for its `layers`, `generator`, `answers`, and `build`, then propose enablement
as one numbered table: Mandatory is the profile's own `layers`, Recommended what the answers
imply, Optional what the user may decline, with the cost of declining. Wait for confirmation.

An extra recipe on top of a profile is a shape check, not an append:

- The CLI unions `--profile <p> <extra...>`, orders the result, and validates it; a
  refusal naming REQUIRES or ordering is a verdict, not an obstacle to `--force` past.
- A recipe that is itself a profile's core -- profiles/<name>.yml with its own
  `generator` or pinned answers -- changes the shape: a second generator, a second
  language, an ordering the profile never validated. Present the real options: its
  own repository, a swap inside this one, or dropping it.

## Answers

The CLI never prompts. Every answer goes in one YAML file passed as `--data-file`, with
`--data key=value` for a single override, so a missing answer is a preflight finding rather
than a question the tool asks. The preflight runs before every render:

```bash
uv run scripts/scaffold.py check-answers --profile <profile> --data-file answers.yml
```

It reports every gap at once, as `Provide a value for '<key>' in recipe '<id>'`. Re-ask
exactly those keys. Render once it prints `answers complete`.

The gap list IS the question list: run it on the currently-resolved set, ask exactly
what it reports, and re-run it after any answer that changes the set -- a recipe
added, an either/or settled -- because the new recipe's keys and `when:`-gated
questions exist only from that point. A key the preflight does not report is not
asked; hand-reading copier.yml re-derives `when:` logic the tool already computes.

**A secret-shaped value never reaches the answers file.** The shapes: `ghp_`, `gho_`, `sk-`,
`AKIA`, `ASIA`, `glpat-`, `xox[baprs]-`, and a PEM header. Refuse to persist it, say the
credential now sits in a transcript and has to be rotated, and leave the key a gap. A secret
belongs in the environment or a secret manager, and `docs/agents/env/index.md` records the
variable name and what fails without it, never a value.

## Render

Plan first, and show the plan before anything touches disk:

```bash
uv run scripts/scaffold.py plan --profile <profile> --dest <dest> --data-file answers.yml
```

Each row is a path, its owning recipes, and its class: `create`, `overwrite`, `skip`,
`fragment`, or `answers`. Exit 5 is a `conflict`, where two recipes own one path. Stop, name both owners, and
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
  written, and the repository silently is not a workspace. A single package keeps generator-first.
- **A fragment contributor precedes its aggregator.** `workspace/just` folds `.just.d/`,
  `quality/hooks` folds `.pre-commit.d/`, and `base/gitignore` rebuilds `.gitignore` from
  `.gitignore.d/`.

## Record the run in beads

The run record is not optional, and it is poured AFTER the render: agentic/beads'
own task is the only correct `bd init` (server mode, the rendered AGENTS body, the
gitignore fragment), and a pre-render init would pin embedded storage that
`--init-if-missing` can never correct. The moment the render finishes:

```bash
mkdir -p <dest>/.beads/formulas
cp "$SCAFFOLD/formulas/mol-scaffold-run.formula.toml" <dest>/.beads/formulas/
cd <dest> && bd mol pour mol-scaffold-run --var feature=<slug> --var profile=<profile>
bd update <root-id> --metadata '{"dest":"<dest>"}'
```

Then bring the record up to now, and let the rest run live from the DAG:

- Close `interview` with the decision table. A gate is its own issue attached to the
  step (`bd show <step>` names it): `bd gate resolve <gate-id> --reason "who approved
  the plan, when"`, then `bd close <step>`.
- Create one task bead per rendered recipe under `<root>.render`, each closed with
  its render commit.
- Setup, secrets, build, verify, handoff, and the remote and install gates stay
  live. Each gate commits what an agent must not decide alone: a published
  repository, a credential, a machine-global registration.
- Pour `--var autonomous=yes` where no human can answer: the plan gate drops out,
  the secrets gate still stalls.

A crash before the pour has no DAG; the answers file and the printed plan are the
resume artifacts for that window, and a re-render from them is idempotent. Degrade
to a plain run only when `bd` itself is absent -- warn once, then carry on.

## After rendering

Run `just setup` in the destination for the toolchain, the dependencies, and the hook shims,
then `just check` for what CI runs. Report every file written, and every command that failed
with its own output: a summary saying "done" hides a failed build. Where `commit_scopes` was
left empty, say so: scopes stay unrestricted until the team lists a vocabulary there and
re-renders `quality/hooks`, and the render-time note that says so reaches nobody in a task log.

**Marketplaces are the user's to name.** Ask which sources this repository's agents should read
and register exactly those. Nothing here ships or derives a list: naming a source is a
supply-chain decision, suggesting one makes it for the user, and "none" is a complete answer.

Registration is machine-global, so each source goes behind the run's marketplace gate:
`omp plugin marketplace add <owner/repo>`; Claude `/plugin marketplace add <owner/repo>`;
Codex reads `.agents/plugins/marketplace.json`.

- One Claude-native catalog serves Claude and OMP, verified live (OMP falls back to
  `.claude-plugin/`).
- Boundaries: OMP loads rules and agents only with the `omp` package.json marker, and
  Claude hooks are inert there -- a plugin leaning on either under-delivers in one runtime.

## Rules

- Ask what nothing derives; `rules/choices.md` marks the rest fixed or derived.
- Never name a marketplace the user did not. No check catches a suggested source, and one
  registration reaches every project on the machine.
- Say a generator reaches the network before running it.
- Read name, owner, and visibility back before `gh repo create --public`: it publishes at once.
- Verify by running the real tool against rendered output, not by reading the recipe. Every
  defect found while building these recipes rendered cleanly first.
- `just add <name> <lang>` adds a monorepo member: recipe at the member path, manifest entry.
