---
status: accepted
date: 2026-07-29
---

# Architecture

How this repository scaffolds projects, and which decisions are fixed.

## Model

A project is a **profile** plus a set of **recipes**.

A recipe is one directory holding a `copier.yml` and, in every case here, a
`template/`. It carries the files for one tool or one concern. A profile names
its recipe set and the destination for each, and layers them in that order into
one destination, where each writes only its own files.

`just` calls its own targets recipes too. A justfile target is always written
`just <name>` here; an unqualified recipe is one of these directories.

What renders comes from three inputs:

| Input | Source | Example |
|---|---|---|
| Fixed preference | hard-coded in the recipe | `uv`, `prek`, `biome`, `release-please` |
| Derived | `rules/choices.md`, applied by the agent | task runner, license, CI job set |
| Asked | interview, one question at a time | project name, language, repo visibility |

The interview asks what nothing derives -- a short opening round, then rounds
grilling the application's shape. Everything else is fixed or derived.

## Plan before render

`scripts/scaffold.py` is the only entry point. `plan` renders each recipe into a
scratch git repository and reports what the set would write, which is what makes
a conditional or jinja-templated filename exact rather than guessed.

Every path gets a class:

| Class | Meaning |
|---|---|
| `create` | one owner, and the destination does not hold the path |
| `overwrite` | one owner, and the destination holds a different file |
| `unchanged` | one owner, path present, left to copier to compare |
| `skip` | a later owner declares the path under `_skip_if_exists`; the first owner wins |
| `fragment` | under a fold directory, where an aggregator merges it |
| `answers` | a `.copier-answers.<name>.yml`, which the CLI owns |
| `conflict` | two owners and no declared resolution |

Two owners of one path is refused. `plan` exits 5 naming both owners, and
`render` runs the same plan first and stops before writing anything. `--force`
exists and is the wrong answer: two recipes owning one file is a defect in the
profile or in a recipe.

The exception is declared rather than inferred. When every writer after the
first declares the path under `_skip_if_exists`, the class is `skip` and the
first writer wins, which is how `host/github` and `host/gitlab` can both carry
`SECURITY.md`. Fragment directories are the other exception, and
`_scaffold.merge` globs let a recipe declare a merged path of its own. Two
recipes writing the same fragment path still conflict.

`render` initialises the destination as a git repository and commits once per
recipe. That history is what makes a bad render reviewable, since copier
overwrites and leaves no diff.

## Update on a recorded ref

`copier update` cannot run against an in-repo recipe. copier records `_commit`
only when the template is a git repository root, and every recipe here is a
subdirectory of one, so there is no ref to replay from.

`render` therefore records the scaffold repository's HEAD as `_ref` in each
recipe's answers file, beside `_source`. `update` reads `_ref` back and renders
the recipe twice, once at that ref through a detached worktree and once at HEAD,
then merges the difference over the destination file with `git merge-file`.

Local edits survive where they do not overlap a template change. A true overlap
gets conflict markers and exit 5. The answers file is the one exception: HEAD's
copy is taken verbatim, because a three-way merge of that YAML mangles it.

`update` prints which aggregator fold to re-run for every fragment directory it
touched, since folding is the generated repository's own work.

A remote copier template keeps its `_commit`, so `copier update` remains the
right tool for that source.

## Recipe authoring rules

Applied across every recipe in the 2026-08 question audit; a new recipe follows
them or its review says why not.

| Rule | Example |
|---|---|
| A question may not ask what the tree already says | `release_type` reads rust-toolchain.toml, pyproject.toml, package.json, go.mod; `simple` is the no-marker fallback |
| A question may not ask what the toolchain or generator already decided | an empty `rust_edition` keeps what `cargo init` wrote; `go_version` reads go.mod's directive back |
| A version pin resolves latest at render where the backend lists fast, with a verified floor as the offline fallback; a backend that resolves by listing module versions, or a pin renovate owns in the rendered repo, stays concrete | `resolve_versions.py` asks `mise latest` for opentofu and tflint; govulncheck is pinned concrete because mise's go backend timed out on every measured resolve |
| A blank a user must fill stays blank, never guessed | `aws_region` and `state_bucket` render empty and fail at `tofu init` with their own message |
| A question consumed by nothing is deleted, not defaulted | `python_framework` was asked, recorded, and read by nothing |

Settling happens in a `_tasks` script that rewrites only an exact placeholder the
render produced, so a hand-tuned file is never touched -- the same contract
`_skip_if_exists` gives a re-render. A value that decides template-time structure
(a Dockerfile body, a conditional filename) cannot settle afterwards and is
derived by the skill from the same markers instead.

## Run record

A scaffold run is tracked as a beads molecule. `formulas/mol-scaffold-run.formula.toml`
pours nine steps: interview, plan approval, render, setup, remote creation,
secrets, marketplace installs, verify, and handoff.

`render` is a parent step with no children of its own at pour. The skill creates
one task bead per selected recipe under it, in profile order, each blocking the
next. It has to, because the recipe set is read from the profile at run time and
a formula's step count is fixed when it is cooked.

Four steps are human gates, and three of them are unconditional:

| Gate | Why a person resolves it |
|---|---|
| plan approval | the file map is the last point before anything is written |
| remote creation | `gh repo create --public` publishes immediately and has no undo |
| secrets | an agent must not mint, paste, or invent a credential |
| marketplace installs | registering a source reaches every project on the machine |

Only plan approval is conditional, through `--var autonomous=yes`, and skipping
it does not skip its judgement: the run records on the interview step which paths
the plan classed `overwrite` and which recipe owns each.

## Generators

Language and framework scaffolds come from upstream CLIs. This repository owns
the cross-cutting recipes that render on top.

| Profile | Generator | Then |
|---|---|---|
| `agentic-repo` | none | recipes only |
| `rust-lib`, `rust-app` | `cargo new [--lib]` | recipes |
| `rust-gui` | `rust-app`, then `create-tauri-app` at `apps/<name>` | add workspace member, set `edition.workspace` |
| `python-lib`, `python-app` | `uv init [--lib]` | recipes |
| `go-lib`, `go-app` | `go mod init <path>` | recipes |
| `ts-lib` | `bun init` | recipes |
| `ts-app` | `create-better-t-stack create-json` | recipes |
| `ts-tui` | `create-better-t-stack` + `opentui` addon | recipes |
| `cdk` | `projen new awscdk-app-{ts,py}` | recipes |
| `terraform` | none | recipes |

Every generator's output accepts recipes additively. Verified: rendering a
recipe over `create-better-t-stack` and `projen` output writes only new paths,
and a `projen` re-synth leaves those paths intact.

### projen

Set `runner: typescript.TypeScriptRunner.tsx()`, `github: false`,
`eslint: false`. The `tsx` runner is required: projen's default `ts-node`
runner fails under TypeScript 7 (`ts-node` issue #2174). `github: false`
removes projen's own workflows so the `host/*` recipe owns CI.

Bootstrap order matters. `projen new` writes a `ts-node` task, and the synth
that would replace it is the thing that fails. Install `tsx`, then run
`npx tsx .projenrc.ts` once directly. Subsequent `npx projen` calls work.

projen marks `.gitignore` read-only, so gitignore entries go through
`project.gitignore.addPatterns()`.

### better-t-stack

Invoke `create-json`, not the flag form: `--yes` rejects any stack flag, and
`addonOptions` has no flag equivalent. Read valid options at runtime from
`create-better-t-stack schema --name <name>`, which emits JSON Schema.

Option defaults, verified against the runtime schema rather than remembered. Every axis
below is an enum `create-better-t-stack schema --name <axis>` emits:

| Axis | Default | Why |
|---|---|---|
| `frontend` | `tanstack-router` | typed routing without a framework server |
| `backend` | `hono` | runs on bun, node, and workers unchanged |
| `runtime` | `bun` | the fixed package manager for TypeScript here |
| `api` | `orpc` | see below |
| `database`, `orm`, `auth`, `payments` | `none` | asked, not derived: a CLI or static site needs none |

`api` is `orpc` rather than `trpc`, and the deciding evidence is not weight. Both scaffold
the same `apps/{web,server}` shape and land within one dependency of each other, 45 against
44. orpc ships `@orpc/openapi` and its generated server registers an `OpenAPIHandler` and an
`OpenAPIReferencePlugin`, so the contract exists as a document. trpc does not emit an OpenAPI at
all. `lang/api` gates that document with vacuum and oasdiff, so orpc is what makes
that gate mean anything for a `ts-app`.

`database` defaults to `none` because it is one of the two questions
`../rules/choices.md` marks as asked for `ts-app`. A CLI or a static site needs neither a
database nor an api, and no project name reveals which.

The CLI's own validator reports an incompatible combination, so the skill leans on it
rather than encoding a matrix.

Addon defaults:

| Addon | Default | Condition |
|---|---|---|
| `biome`, `turborepo` | on | always |
| `starlight` | off | the `docs/site` recipe supersedes it |
| `tauri` | off | `ts-app` wanting a desktop shell |
| `opentui` | off | `ts-tui` |
| `pwa` | off | asked |
| `oxlint` | off | requesting it with `biome` drops it silently |
| `mcp`, `skills`, `nx`, `husky`, `electrobun`, `wxt`, `ultracite`, `vite-plus`, `evlog` | off | superseded by a recipe |

`mcp` writes MCP configuration that conflicts with globally managed config.

## Layout

Monorepo is an axis that every profile crosses:
`{lib, app} × {single, monorepo}`.

| Language | Monorepo mechanism | Member path |
|---|---|---|
| rust | `[workspace] members` | `crates/*` |
| python | uv workspace | `packages/*` |
| go | one module | `cmd/*`, `internal/*` |
| ts | bun workspaces | `packages/*`, `apps/*` |

`just add <name> <lang>` renders the language recipe at the member path and
registers it in the workspace manifest.

## Fragment merging

copier overwrites files; it does not merge them. Each shared configuration file
has a native mechanism instead of a merge script.

| Target | Mechanism |
|---|---|
| `.pre-commit-config.yaml` | prek workspace mode: one config per directory, unioned and namespaced `<dir>:<hook-id>` |
| `.gitignore` | `base/gitignore` fetches github/gitignore templates through `gh api` and concatenates the fragments |
| `.mise/conf.d/` | mise reads the directory |
| `justfile` | `import?` per fragment, one flat namespace, written by `gen_justfile.py` |
| `.gitlab-ci.yml` | `include: - local: .gitlab/ci/*.yml` |
| projen's `.gitignore` | `project.gitignore.addPatterns()` |

prek has no include directive and skips dot-prefixed directories during
discovery, so a `.pre-commit.d/` fragment directory does not work. One
directory with two language recipes concatenates fragments in a `just` recipe.

`just` has no glob import either, so one line per fragment has to be written, which
is what `gen_justfile.py` does between two markers. `mod` was the alternative and
would namespace each fragment as `just rust::fmt`; `import` keeps the flat names the
fragments already use, at the cost of requiring them to be unique.

lefthook is excluded. `lefthook install` rewrites the configured
`core.hooksPath` directory, which fails without write access to it, and
`--reset-hooks-path` unsets a repo-local override without restoring it. prek
installs into `.git/hooks` when `core.hooksPath` is set repo-locally.

## CI

The host recipe is language-blind. Each language recipe ships its own jobs and
setup action.

```
recipes/host/github/.github/
  workflows/{wc-changes,wc-gate,wc-quality,wc-security}.yml
  actions/ci-gate/action.yml
recipes/lang/python/.github/
  workflows/{wc-lint-python,wc-test-python}.yml
  actions/setup-python/action.yml
```

Inclusion follows from which recipes render, not from a conditional in a
filename. A conditional filename containing a quote breaks jinja compilation.

GitHub needs a caller workflow wiring `needs:` between the reusable workflows.
`scripts/gen_caller.py` in `host/github` writes it from what rendered, and `just ci-sync`
reruns it. GitLab needs no caller, because the glob include resolves the same set.

Both hosts are supported. `*` in a GitLab include matches one level; `**`
recurses. Glob order is not deterministic, so two recipes must not set the same
key.

## Quality

| Concern | Tool |
|---|---|
| Format, assists, organize-imports, CSS/JSON/GraphQL/HTML lint | biome |
| TypeScript lint | oxlint with `options.typeAware: true` |

Set `biome.linter.rules.preset: "none"` and enable only rules oxlint lacks.
Without this the two report the same finding twice, and nothing de-duplicates
them.

oxlint carries 59 of typescript-eslint's 61 type-aware rules against biome's 4
outside nursery. Type-aware mode requires TypeScript 7.

oxfmt is excluded: its output is byte-identical to biome's across 400 files, and
adding it means two formatters disagreeing over import grouping. `oxfmt
--migrate=biome` converts the configuration if the split is later abandoned.

Other languages fix their own tooling: ruff and ty for python, clippy with
`cargo-deny` and `cargo-machete` for rust, golangci-lint v2 schema with gosec
and revive for go, tflint and trivy for terraform.

## Docs

The site renders to `docs/site`. `docs/agents` holds steering and is never
published.

Deploy topology depends on whether the build needs the code:

| Topology | When | Mechanism |
|---|---|---|
| Sibling repo builds itself | default | `<name>.github.io` holds source; `upload-pages-artifact` and `deploy-pages` in that repo |
| Code repo builds, publishes across | the `docs/api-refs` recipe is selected | code repo builds, pushes rendered output to the sibling repo over an SSH deploy key |

The second topology exists because API reference extraction needs the
language toolchains, which live with the code. It costs a deploy key, and its
content replacement must preserve `.git` and `.github`: removing the sibling
repo's workflow does not leave a workflow to trigger on the next push.

Both need `.nojekyll`, an explicit `site:` in the Astro config for sitemap
generation, and `concurrency: group: docs-${{ github.ref }}` scoped per ref.
`actions/deploy-pages` clamps its own poll timeout and ignores a longer one, so
a first attempt runs with `continue-on-error` and a second step retries.

starlight is the default engine. fumadocs is selected for Notion or Obsidian
content sources, or docs AI chat; it hydrates the page shell as a React island
and ships 860K of client JavaScript against starlight's 564K.

## Infrastructure

OpenTofu 1.10 or later. One root module at `infra/`, with `infra/modules/<name>`,
`infra/tests/*.tftest.hcl`, and a `<env>.tfbackend` and `<env>.tfvars` pair per
environment under `infra/envs/`. `infra/bootstrap` is a second root module,
keeping local state because it creates the state bucket.

A file per environment rather than a directory per environment. The phrase
"directory per environment" here once read as a root module each, which is
incompatible with both of the decisions below: partial configuration configures a
single backend block, and `tofu test` reads `tests/` under the root module.

S3 backend with `use_lockfile = true` and no DynamoDB lock table. Partial
backend configuration through `-backend-config=envs/<env>.tfbackend`, wrapped
in `just plan <env>`.

Terragrunt, Atmos, and Digger are excluded. At two to four environments of one
root module, per-environment duplication is the provider and backend blocks,
which partial configuration removes. Digger licenses its GitLab CI backend
under a per-seat Enterprise license.

Tests use `tofu test` with `command = plan` and provider mocks.

## Containers

Multi-stage always, so the toolchain that builds never ships.

distroless is the runtime base. Measured against the same static Go binary:

| Base | Size | HIGH or CRITICAL | Shell |
|---|---|---|---|
| `distroless/static-debian12:nonroot` | 9.58MB | 12 | none |
| `alpine:3.22` | 16.8MB | 12 | yes, and uid 0 |
| `debian:stable-slim` | 143MB | 34 | yes |

The shell is the deciding column rather than the size. `docker run --entrypoint sh`
failed outright on distroless and returned `uid=0(root)` on alpine, so a compromised
process there gets both root and a shell. alpine is the choice when a shell is
needed to debug; debian when a dependency needs glibc and a full userland.

`static` requires a statically linked binary, which is why the compiled build stages set
`CGO_ENABLED=0`. An interpreted language takes the matching distroless variant instead,
since `static` carries no interpreter.

Build, scan, then push, in that order. An image already in a registry can be pulled by
anything watching it, so a scan running after the push reports a vulnerability that has
already shipped.

The build therefore loads into the local daemon rather than pushing. The scan reads it
there, and the push is a separate step gated on that scan.

A Dockerfile that already exists is never replaced, because whichever framework
generated it owns it. The recipe contributes the lint, the CI, and the ignore file around
whatever is there.

## Structural tool

A repository names one structural tool in `docs/agents/index.md`, either repomix
or gitnexus, with the invocation scoped by `--include` for that profile.

repomix does not cache a pack. One costs 1.4s for 1,269 files and 3.6s for 4,107, and
every stored form needs a fetch step the reader has to know about, which a fresh
clone does not.

Prose is the weakest of the mechanisms that keep the tool in use:

| Surface | Cost | Survives compaction |
|---|---|---|
| `docs/agents/index.md` naming the tool | none | no |
| `just pack-check` comparing HEAD against the pack's marker | about 80ms | n/a |
| `PreToolUse` on `Grep\|Glob` printing a reminder | none | yes |

`just pack` writes the HEAD it packed to `repomix-full.xml.sha`, and `just pack-check`
reports how many commits the pack is behind. The marker holds a commit, since a checkout or
a clone resets a modification time. It reports a count, which is what tells a reader whether
to repack.

The check reports and exits 0. A stale pack is information rather than a broken build, and a
non-zero exit would put it in `just check` and fail runs for a reader who never opens the
pack.

Packing at session start was the alternative and was rejected on cost: repomix has no
cache, two runs with identical arguments took 1.83s then 1.35s, and the snapshot goes stale
on the agent's first edit.

The reminder never denies the call. grep is the right tool for an exact-text
lookup, so blocking it would be wrong.

## Hooks versus CI

A local hook is advisory: `--no-verify` defeats it, and a fresh clone has no
shims until someone runs `just setup`. A check that must hold therefore runs in
CI, inside the quality job the gate depends on.

| Runs in CI | Stays a local hook |
|---|---|
| the whole hook set, through `prek run --all-files` | formatters and fixers that rewrite files |
| commit-message checks over the pull request range | anything reading staged state before a commit exists |
| the refusal of a hand-made version tag | nothing: a tag is pushed rather than committed |

The hook set runs over `--all-files`. A diff range covers only what a branch touched, so a
hook bypassed at commit time stays bypassed for every file outside that range.

The split follows from what each can see. A check that reads committed state runs
in CI. A check that rewrites, or that needs the index, stays a hook.

prek installs into `.git/hooks` once `core.hooksPath` is set repo-locally, and
its `pre-push` shim fires from there even where another tool sets the global
hooks path.

`prek install` writes one shim per entry in `default_install_hook_types`, so that
list has to name every stage the hooks declare. A stage missing from it is a hook
that never fires and reports nothing, so `quality/hooks` computes the list from the
folded fragments.

## Steering

`docs/agents` holds one directory per concern. Each concern has an index and
per-language leaves, so adding a language adds files rather than growing them.

```
docs/agents/
  index.md                 commands, toolchain pins, layout, structural tool
  conventions.md           hand-written: error handling, logging, ownership
  quality/index.md + <lang>.md
  ci/index.md + {github,gitlab}.md
  release/index.md  testing/index.md  docs/index.md  env/index.md
```

Derived content sits inside `<!-- BEGIN GENERATED: <id> -->` markers. The
generator replaces marked blocks and never touches text outside them, so
hand-written rationale survives regeneration. `conventions.md` carries no
generated block.

A failure found by running a tool goes in the file whose behaviour depends on it:
a test docstring when a test pins it, a comment beside the code that works around
it, or the decision record that measured it. Prose collected separately drifts from
whatever enforces it, and nothing fails when it does.

`AGENTS.md` is an index. The detail sits in `docs/agents`, and `docs/agents`
writes `AGENTS.md` from its own `AGENTS.body.md`, with `CLAUDE.md` a relative
symlink to it so one file serves both harnesses. Directory structure is not
documented here: gitnexus and repomix answer structural questions, and `index.md`
names which of them this repository has.

`env/index.md` records variable names and what fails without each. Never
values.

## Skills

Both skills are plain markdown at `skills/<name>/SKILL.md`. A harness reaches
them through a pointer into that directory rather than through a compiled copy,
so there is one source per skill and nothing to recompile after an edit.

| Skill | Scope |
|---|---|
| `project-scaffold` | interview, plan, render the recipe set, generate steering |
| `project-scaffold-update` | adopt a recipe, merge recipe changes into a rendered repository, retrofit one that predates this tool |

Regenerating steering is `just steering`, not a skill. It is a pure function of
files on disk, with no prompts and no network, so a skill wrapping it would put
a model in a decision that has none. `just steering-check` regenerates into a
temporary directory and exits non-zero on a difference. That check runs inside
the existing quality job.
A workflow of its own would be gated on paths, and a workflow that never runs
leaves a required check pending forever.

## Excluded

| Rejected | Reason |
|---|---|
| structkit | hooks are never rendered; documented behavior absent in three of three cases tested |
| better-t-stack as a forked library | `template-processor.ts` does not perform a layered merge; the processors encode turbo-versus-nx knowledge |
| projen for python or typescript | generates `requirements.txt`; no `pyproject.toml` |
| ultracite | 366 pinned rules, fixed formatter profile, single maintainer |
| oxfmt | output identical to biome's; second formatter conflicts on import grouping |
| lefthook | rewrites the configured hooks path |
| terragrunt, atmos, digger | see Infrastructure |
| terramate, terraspace, pluralith, terrascan, tfsec | unmaintained |
