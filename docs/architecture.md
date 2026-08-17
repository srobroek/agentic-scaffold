---
status: accepted
date: 2026-07-29
---

# Architecture

How this repository scaffolds projects, and which decisions are fixed.

## Model

A project is a **profile** plus **layers**.

Each layer is one copier template directory holding files for one tool or
concern, and a profile names the layer set plus the destination for each. Layers
render in sequence into one destination; each writes only its own files.

What renders comes from three inputs:

| Input | Source | Example |
|---|---|---|
| Fixed preference | hard-coded in the layer | `uv`, `prek`, `biome`, `release-please` |
| Derived | `rules/choices.md`, applied by the agent | task runner, license, CI job set |
| Asked | interview, one question at a time | project name, language, repo visibility |

The interview is six questions. Everything else is fixed or derived.

## Generators

Language and framework scaffolds come from upstream CLIs. This repository owns
the cross-cutting layers that render on top.

| Profile | Generator | Then |
|---|---|---|
| `agentic-repo` | none | layers only |
| `rust-lib`, `rust-app` | `cargo new [--lib]` | layers |
| `rust-gui` | `rust-app`, then `create-tauri-app` at `apps/<name>` | add workspace member, set `edition.workspace` |
| `python-lib`, `python-app` | `uv init [--lib]` | layers |
| `go-lib`, `go-app` | `go mod init <path>` | layers |
| `ts-lib` | `bun init` | layers |
| `ts-app` | `create-better-t-stack create-json` | layers |
| `ts-tui` | `create-better-t-stack` + `opentui` addon | layers |
| `cdk` | `projen new awscdk-app-{ts,py}` | layers |
| `terraform` | none | layers |

Every generator's output accepts copier layers additively. Verified: rendering
a layer over `create-better-t-stack` and `projen` output writes only new paths,
and a `projen` re-synth leaves those paths intact.

### projen

Set `runner: typescript.TypeScriptRunner.tsx()`, `github: false`,
`eslint: false`. The `tsx` runner is required: projen's default `ts-node`
runner fails under TypeScript 7 (`ts-node` issue #2174). `github: false`
removes projen's own workflows so the `host/*` layer owns CI.

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
all. `lang/api` gates that document with vacuum and oasdiff, so orpc is what makes the
contract layer mean anything for a `ts-app`.

`database` defaults to `none` because it is one of the two questions
`../rules/choices.md` marks as asked for `ts-app`. A CLI or a static site needs neither a
database nor an api, and no project name reveals which.

The CLI's own validator reports an incompatible combination, so the skill leans on it
rather than encoding a matrix.

Addon defaults:

| Addon | Default | Condition |
|---|---|---|
| `biome`, `turborepo` | on | always |
| `starlight` | off | the `docs/site` layer supersedes it |
| `tauri` | off | `ts-app` wanting a desktop shell |
| `opentui` | off | `ts-tui` |
| `pwa` | off | asked |
| `oxlint` | off | requesting it with `biome` drops it silently |
| `mcp`, `skills`, `nx`, `husky`, `electrobun`, `wxt`, `ultracite`, `vite-plus`, `evlog` | off | superseded by a layer |

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

`just add <name> <lang>` renders the language layer at the member path and
registers it in the workspace manifest.

## Fragment merging

copier overwrites files; it does not merge them. Each shared configuration file
has a native mechanism instead of a merge script.

| Target | Mechanism |
|---|---|
| `.pre-commit-config.yaml` | prek workspace mode: one config per directory, unioned and namespaced `<dir>:<hook-id>` |
| `.gitignore` | `gitnr create <templates> -s` concatenates sources |
| `.mise/conf.d/` | mise reads the directory |
| `justfile` | `import?` per fragment, one flat namespace, written by `gen_justfile.py` |
| `.gitlab-ci.yml` | `include: - local: .gitlab/ci/*.yml` |
| projen's `.gitignore` | `project.gitignore.addPatterns()` |

prek has no include directive and skips dot-prefixed directories during
discovery, so a `.pre-commit.d/` fragment directory does not work. One
directory with two language layers concatenates fragments in a `just` recipe.

`just` has no glob import either, so one line per fragment has to be written, which
is what `gen_justfile.py` does between two markers. `mod` was the alternative and
would namespace each fragment as `just rust::fmt`; `import` keeps the flat names the
fragments already use, at the cost of requiring them to be unique.

lefthook is excluded. `lefthook install` rewrites the configured
`core.hooksPath` directory, which fails without write access to it, and
`--reset-hooks-path` unsets a repo-local override without restoring it. prek
installs into `.git/hooks` when `core.hooksPath` is set repo-locally.

## CI

The host layer is language-blind. Each language layer ships its own jobs and
setup action.

```
templates/host/github/.github/
  workflows/{wc-changes,wc-gate,wc-quality,wc-security}.yml
  actions/ci-gate/action.yml
templates/lang/python/.github/
  workflows/{wc-lint-python,wc-test-python}.yml
  actions/setup-python/action.yml
```

Inclusion follows from which layers render, not from a conditional in a
filename. A conditional filename containing a quote breaks jinja compilation.

GitHub needs a caller workflow wiring `needs:` between the reusable workflows;
the agent writes it from `rules/ci-composition.md`. GitLab does not need a caller,
because the glob include resolves the same set.

Both hosts are supported. `*` in a GitLab include matches one level; `**`
recurses. Glob order is not deterministic, so two layers must not set the same
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
| Code repo builds, publishes across | the `docs/api-refs` layer is selected | code repo builds, pushes rendered output to the sibling repo over an SSH deploy key |

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
process there gets both root and a shell. alpine is the choice when a shell is genuinely
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
generated it owns it. The layer contributes the lint, the CI, and the ignore file around
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

`AGENTS.md` is an index. Detail sits in `docs/agents`, reached through
`.apm/context` pointers that `apm compile` weaves in. Directory structure is
not documented here: gitnexus and repomix answer structural questions, and
`index.md` names which of them this repository has.

`env/index.md` records variable names and what fails without each. Never
values.

## Skills

| Skill | Scope |
|---|---|
| `project-scaffold` | interview, render layers, generate steering |
| `project-scaffold-update` | adopt a layer, apply template changes, retrofit an existing repository |

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
| structkit | hooks are never rendered; documented behavior absent in three of three features tested |
| better-t-stack as a forked library | `template-processor.ts` does not perform a layered merge; the processors encode turbo-versus-nx knowledge |
| projen for python or typescript | generates `requirements.txt`; no `pyproject.toml` |
| ultracite | 366 pinned rules, fixed formatter profile, single maintainer |
| oxfmt | output identical to biome's; second formatter conflicts on import grouping |
| lefthook | rewrites the configured hooks path |
| terragrunt, atmos, digger | see Infrastructure |
| terramate, terraspace, pluralith, terrascan, tfsec | unmaintained |
