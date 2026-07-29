---
status: accepted
date: 2026-07-29
---

# Layers

19 layers and roughly 34 variables, from 30 packages and 247 questions. Every
variable listed here is asked or derived; anything absent is fixed in the layer
per `../rules/choices.md`.

## base

Renders first. `base/license` is separate from `base/repo` because `lang/rust`
reads its answers file for the SPDX identifier, and `_external_data` reads a
sibling layer.

| Layer | Writes | Variables |
|---|---|---|
| `base/license` | `LICENSE` | `license`, `copyright_name` |
| `base/repo` | `README.md`, `.editorconfig`, `.gitattributes`, `docs/{adr,architecture}/`, `scripts/`, `tests/` | `project_name`, `description`, `org` |
| `base/gitignore` | `.gitignore`, through `gitnr create <templates> file:.gitignore.d/* -s` | none |

`license` is one of `apache-2.0`, `mpl-2.0`, `agpl-3.0-only`. The gitnr template
list follows from which language layers rendered.

`base/repo` creates `docs/` and nothing inside it. `docs/agents` and `docs/adr`
own their own subtrees.

`base/repo` carries the only `precheck.py`. It verifies `copier`, `just`,
`gitnr`, `mise`, and `git`, plus the generator the chosen profile needs, and
exits non-zero before any file is written.

## lang

Each language layer writes the same six kinds of file, which is what makes
adding a language a one-directory change.

```
lang/<name>/template/
  <tool configs>
  .gitignore.d/<name>
  .pre-commit.d/<name>.yaml
  .mise/conf.d/<name>.toml
  .just.d/<name>.just
  .github/workflows/wc-{lint,test}-<name>.yml
  .github/actions/setup-<name>/action.yml
  .gitlab/ci/<name>.yml
```

| Layer | Tool configs | Variables |
|---|---|---|
| `lang/rust` | `rust-toolchain.toml`, `rustfmt.toml`, `clippy.toml`, `deny.toml` | `crate_kind`, `rust_edition` |
| `lang/python` | `ruff.toml`, `pytest.ini`, `noxfile.py` | `python_version`, `python_layout`, `python_framework` |
| `lang/ts` | `tsconfig.json`, `biome.json`, `.oxlintrc.json`, `vitest.config.ts` | `node_version`, `ts_framework` |
| `lang/go` | `.golangci.yml`, `cmd/<name>/main.go` | `go_module_path`, `go_version` |
| `lang/api` | `openapi.yaml`, vacuum and oasdiff config | `api_title` |

`lang/ts` writes both `biome.json` and `.oxlintrc.json`. That pairing is fixed,
not a choice. When better-t-stack generated the project it already wrote
`biome.json` and `tsconfig.json`, so `lang/ts` guards both with
`_skip_if_exists` and contributes only the fragments and CI jobs.

`lang/api` uses vacuum for linting and oasdiff for breaking-change detection.
spectral renders only when a custom ruleset needs it.

`.gitignore.d/<name>` carries the conditional lines alone. gitnr's own templates
cover `/target`, `__pycache__`, and `node_modules`; what it cannot express is
`Cargo.lock` ignored for a library and committed for a binary, or `vendor/` under
Go vendor mode.

### In a monorepo

`just add <name> <lang>` renders the language layer at the member path. A
language layer therefore has two destination roots: the member directory for its
tool configs and its `.pre-commit-config.yaml`, and the repository root for
`.mise/conf.d/`, `.just.d/`, and the CI files, which are repository-wide.

CI stays inside the language layer rather than in a layer of its own. A separate
CI layer would have to know which languages sit at which paths; inside the
language layer, a monorepo gets the right jobs by construction, and the reusable
workflows already take a `working-directory` input.

## host

Language-blind. Each language layer supplies its own jobs and setup action.

The shared quality and security jobs split across both. The host layer carries
actionlint, zizmor, cspell, lychee, taplo, yamllint, markdownlint, and the secret
scan, which need no language knowledge.

The rest cannot live here:

| Step | Why it is language-dependent |
|---|---|
| lizard | complexity thresholds differ per language |
| CodeQL | takes a language list, and its names differ from ours (`javascript-typescript`, not `ts`) |
| trivy | filesystem mode against dependencies, configuration mode against IaC |
| OSV | keys off which lockfiles exist |

Each language layer therefore drops `.github/quality.d/<lang>.yml` and
`.github/security.d/<lang>.yml`, and the shared workflow carries a matrix the
agent fills from those fragments.

| Layer | Writes | Variables |
|---|---|---|
| `host/github` | `workflows/{wc-changes,wc-gate,wc-quality,wc-security}.yml`, `actions/ci-gate/`, `CODEOWNERS`, issue and pull-request templates, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` | `security_contact`, `coc_contact`, `default_branch`, `job_timeout_minutes` |
| `host/gitlab` | `.gitlab-ci.yml` with the glob include and stages list, `.gitlab/ci/{quality,security}.yml`, `CODEOWNERS` | `gitlab_host`, `security_contact` |

## quality

| Layer | Writes | Variables |
|---|---|---|
| `quality/hooks` | root `.pre-commit-config.yaml` with `default_install_hook_types`, `.mise/conf.d/hooks.toml` | `hook_exclude_patterns`, `max_file_kb`, `commit_scopes` |

Every hygiene check is on. prek is the manager.

Conventional-commit checking uses `compilerla/conventional-pre-commit`, which
takes `--strict` to disallow `fixup!` and merge commits, `--force-scope`,
`--scopes <list>`, and positional custom types. It replaces a hand-written
74-line script.

In a monorepo the language layer owns each member's `.pre-commit-config.yaml`
and prek unions them, so hooks travel with the language. `quality/hooks` then
carries the root config and the repository-wide hygiene hooks alone.

## workspace

| Layer | Writes | Variables |
|---|---|---|
| `workspace/monorepo` | the workspace manifest: `[workspace] members`, uv workspace, or bun workspaces | `layout`, `members` |
| `workspace/just` | `justfile` carrying one `import` per `.just.d/*.just` | none |
| `workspace/moon` | `.moon/workspace.yml` | `members` |
| `workspace/devcontainer` | `.devcontainer/devcontainer.json` | none |

`workspace/monorepo` owns `just add`.

## release

| Layer | Writes | Variables |
|---|---|---|
| `release/release-please` | `release-please-config.json`, `.release-please-manifest.json`, the workflow | `release_type`, `initial_version` |
| `release/cocogitto` | `cog.toml` | `initial_version` |
| `release/dep-updates` | `renovate.json`, and `.github/dependabot.yml` for `github-actions` | none |

Ecosystems follow from the language layers. renovate covers the language
ecosystems; dependabot covers action versions, which is what the existing
auto-merge workflow in `astro-up.github.io` consumes.

## docs

| Layer | Writes | Variables |
|---|---|---|
| `docs/site` | `docs/site/{astro.config.mjs,package.json,src/content/docs/}` | `docs_engine`, `site_url` |
| `docs/agents` | `docs/agents/**`, the `AGENTS.md` body, the `CLAUDE.md` symlink | none |
| `docs/adr` | `docs/adr/{0000-template.md,index.md}` | none |
| `docs/deploy-sibling` | the sibling repository's workflow and `.nojekyll` | `pages_repo` |
| `docs/deploy-split` | the code repository's cross-repository publish workflow | `pages_repo`, `deploy_key_secret` |
| `docs/api-refs` | `docs/site/scripts/extract-<lang>-api.*`, `gen-api-refs.mjs` | none |

`docs_engine` is `starlight` or `fumadocs`. `site_url` is mandatory: without an
explicit `site:` the Astro sitemap integration warns and emits nothing.

Selecting `docs/api-refs` forces `docs/deploy-split`.

## agentic

| Layer | Writes | Variables |
|---|---|---|
| `agentic/apm` | `apm.yml` | `apm_packages`, `apm_target` |
| `agentic/beads` | `.beads/` through `bd init --skip-agents --skip-hooks`, plus `hooks/` in `.beads/.gitignore` | `bd_prefix` |
| `agentic/marketplace` | nothing; it reports recommended installs | none |

No per-harness configuration file. `agentic/marketplace` runs last.

`agentic/apm` seeds the marketplaces, `srobroek/agentic-packages` among them.
The agent then reads the rendered layer set and recommends packages against it:
`language-rust` and `rust-quality` for a rust layer, `mcp-tauri` for a Tauri
shell, `steering-infrastructure` for terraform, `speckit` when SpecKit is in use.
That match is judgement, so it belongs to the agent rather than a template.

`agentic/apm` seeds three marketplaces of your own: `srobroek/agentic-packages`,
`srobroek/slopvac`, and `srobroek/vibe-hero`. Third-party marketplaces are
offered rather than defaulted.

Choosing SpecKit pulls `speckit`, `speckit-beads`, and `steering-speckit`
together. `speckit-beads` is what connects SpecKit to `bd`.

`agentic/beads` runs `bd init --skip-hooks`, then `quality/hooks` reproduces bd's
five hooks as local prek entries. bd writes five 1.3KB shims that each run
`bd hooks run <event>` for `pre-commit`, `post-merge`, `post-checkout`,
`pre-push`, and `prepare-commit-msg`; prek supports every one of those stages.
What made `--skip-hooks` necessary was the ambient hook binaries copied in
alongside, not those shims.

## iac

| Layer | Writes | Variables |
|---|---|---|
| `iac/terraform` | `infra/{bootstrap,modules,envs/<env>,tests}`, `.tflint.hcl`, `.pre-commit.d/terraform.yaml` | `environments`, `aws_region`, `state_bucket` |
| `iac/cdk` | `.projenrc.ts` with `runner: tsx()` and `github: false` | `cdk_language` |

`environments` defaults to `[dev, prod]`.

## Render order

```
base/repo precheck
<generator>            cargo new, uv init, go mod init, bun init, bts, projen
base/license
base/repo
workspace/monorepo
lang/*
host/{github,gitlab}
quality/hooks
release/*  iac/*  docs/*
agentic/{apm,beads}
workspace/just
base/gitignore
agentic/marketplace
```

The generator runs before every layer. `cargo init` writes no `license` key and
`uv init` writes its own `pyproject.toml`, so a language layer patches an
existing manifest rather than creating one.

`workspace/monorepo` precedes `lang/*` so the manifest exists before members
render.

`workspace/just` and `base/gitignore` aggregate what earlier layers contributed,
so they follow every contributor including `agentic/*`: apm and beads add
ignores for `apm_modules/` and `.beads/dolt/`, and may contribute a
`.just.d/apm.just`.

`agentic/marketplace` reads the finished tree.

A profile states this order directly. 19 layers with a fixed order need no
dependency solver.

## Contribution points

| Contributed as | Combined by |
|---|---|
| `.gitignore.d/<name>` | `gitnr create` in `base/gitignore` |
| `.github/{quality,security}.d/<name>.yml` | a matrix in the host layer's shared workflow |
| `.pre-commit.d/<name>.yaml` | see below |
| `.mise/conf.d/<name>.toml` | mise reads the directory |
| `.just.d/<name>.just` | `import` lines in `workspace/just` |
| `.github/workflows/wc-*.yml` | the caller the agent writes |
| `.gitlab/ci/<name>.yml` | GitLab's `include: local:` glob |

### Hook fragments

In a monorepo each package carries a real `.pre-commit-config.yaml`, and prek's
workspace mode unions them with hooks namespaced `<dir>:<hook-id>`. Nothing
merges.

In a single directory two language layers cannot both own the root config, so
`just hooks:merge` concatenates `.pre-commit.d/*.yaml`. prek skips dot-prefixed
directories during discovery, so the fragment directory is invisible to it until
that recipe runs.

## Cross-layer reads

Two, both through `_external_data`, which resolves against the destination:

| Layer | Reads | For |
|---|---|---|
| `lang/rust` | `base/license` | the SPDX identifier for `Cargo.toml`, without which `cargo-deny` fails against the crate itself |
| `docs/deploy-*` | `docs/site` | the engine and the site URL |

Every other shared value is threaded by the agent, which writes one answers file
per layer.

## Dropped

| Package | Reason |
|---|---|
| `hooks/manager` | prek is the manager; lefthook rewrites the configured hooks path |
| `agentic/agentic` | per-harness configuration comes from a marketplace |
| `agentic/agent-hooks` | same |
| `docs/mkdocs` | starlight and fumadocs cover it |
| `docs/starlight` | replaced by `docs/site`, which needs no TypeScript project |
| `iac/cloudformation` | absent from every repository surveyed |
| `repo/gitlab-repo` | folded into `host/gitlab` |
| `repo/package-add` | replaced by `just add`, owned by `workspace/monorepo` |
