---
status: accepted
date: 2026-07-29
---

# Layers

36 layers and 105 asked variables, from 30 packages and 247 questions. Every
variable listed here is asked or derived; anything absent is fixed in the layer
per `../rules/choices.md`.

## base

Renders first. `base/license` is separate from `base/repo` because `lang/rust`
reads its answers file for the SPDX identifier, and `_external_data` reads a
sibling layer.

| Layer | Writes | Variables |
|---|---|---|
| `base/license` | `LICENSE` | `license`, `copyright_name`, `copyright_year` |
| `base/repo` | `README.md`, `.editorconfig`, `.gitattributes`, `docs/{adr,architecture}/`, `scripts/`, `tests/` | `project_name`, `description`, `org` |
| `base/gitignore` | `.gitignore`, through `gitnr create <templates> file:.gitignore.d/* -s` | none |

`license` takes any licence identifier and fetches the body through
`gh api /licenses/<key>`. No text is vendored here, since a copy would drift from
the source.

GitHub keys are lowercase and do not always match the SPDX identifier:
`AGPL-3.0-only` is `agpl-3.0` there, so the layer normalises `-only` and
`-or-later` before the call. `gh api /licenses/<key>` also serves identifiers
absent from the `/licenses` list, `EUPL-1.2` among them. Anything it refuses falls
back to the SPDX licence list, and an identifier neither carries fails while
listing what GitHub has. `none` writes no file.

The gitnr template list follows from which language layers rendered, plus
`Global/{macOS,Windows,Linux}` on every render. The operating system writes
`.DS_Store`, `._*`, `Thumbs.db`, and `*~` whatever the project is, and a docs-only
repository renders no language layer to derive them from.

Editor directories are left out. `.vscode/` and `.idea/` follow the developer
rather than the project, so they belong in a global `core.excludesFile` rather than
in every repository this scaffolds.

`base/repo` creates `docs/` and nothing inside it. `docs/agents` and `docs/adr`
own their own subtrees.

`base/repo` carries the only `precheck.py`. It requires `git`, `just`, and
`gitnr`, notes `mise` and `prek` when absent, and refuses a destination with
uncommitted changes, because copier overwrites and leaves no diff to review.

`base/gitignore` always ignores what a tool in the repository writes, meaning the
repomix pack and any generated skill directory.

A fragment opening with its own comment keeps it rather than gaining a second one.
The whole file is rebuilt from its sources each run, so two runs produce the same
bytes.

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
| `lang/api` | `openapi.yaml`, `.just.d/api.just`, the mise, hook, CI, and quality fragments | `api_title`, `api_version`, `api_server_url`, `api_ruleset`, `api_fail_severity`, `api_baseline_ref` |

`lang/ts` writes both `biome.json` and `.oxlintrc.json`. That pairing is fixed,
not a choice. When better-t-stack generated the project it already wrote
`biome.json` and `tsconfig.json`, so `lang/ts` guards both with
`_skip_if_exists` and contributes only the fragments and CI jobs.

`lang/api` uses vacuum for linting and oasdiff for breaking-change detection.
spectral renders only when a custom ruleset needs it.

Both tools ship a default that looks like a gate and is not one. `vacuum lint` exits 0
on warnings unless `--fail-severity` is passed, and a missing description or absent
`operationId` is reported at warn, so the recipe passes it. `oasdiff breaking` prints
every breaking change and exits 0 unless `--fail-on ERR` is passed. Measured against
vacuum 0.30.0 and oasdiff 1.26.1: removing an operation exited 0 bare and 1 with the
flag.

oasdiff installs through `ubi` rather than `aqua`, which carries no registry entry for
it.

The starter spec passes its own gate as rendered, which took four `example` blocks. It
scored 98 of 100 with four `missing examples` warnings until they were added, so the
scaffold failed the check it ships.

Only the lint runs at commit time. The breaking-change check reads the spec out of a
baseline ref, and a first commit on a fresh branch has no merge base, so it belongs in CI
where the pull request defines one. With no baseline reachable it exits 0 rather than
blocking the commit that introduces the contract.

`.gitignore.d/<name>` carries the conditional lines alone. gitnr's own templates
cover `/target`, `__pycache__`, and `node_modules`; what it cannot express is
`Cargo.lock` ignored for a library and committed for a binary, or `vendor/` under
Go vendor mode.

### In a monorepo

`just add <name> <lang>` renders the language layer at the member path. A
language layer therefore has two destination roots: the member directory for its
tool configs and its `.pre-commit-config.yaml`, and the repository root for
`.mise/conf.d/`, `.just.d/`, and the CI files, which are repository-wide.

copier renders to one destination, so `add_member.py` renders into the member path and
moves the repository-wide directories up, merging into whatever is already there. Two
members both contribute a `.mise/conf.d/` entry, and moving the directory wholesale
would drop the first.

The member's hook fragment is promoted to a real `.pre-commit-config.yaml`. prek's
workspace mode reads one config per directory and namespaces the hooks
`<dir>:<hook-id>`, but it skips dot-prefixed directories while discovering, so a
`.pre-commit.d/` fragment alone is invisible and the member's hooks never run.

prek also caches which directories hold a config, so a member added afterwards stays
invisible until the cache is rescanned. `add_member.py` runs `prek list --refresh`
once, which is enough: verified against prek 0.4.11, where `prek list` showed only
root hooks beforehand and kept listing `packages/svc:ruff-format` after.

The same script registers the member with release-please when that layer rendered, for
the same reason: `just add` is where the path becomes known, and release-please resolves
no globs.

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
`.github/security.d/<lang>.yml`, and the shared workflow builds its matrix by
reading that directory at run time.

The security fragment also names the layer's opengrep packs, which is the same inversion
applied to a ruleset: `lang/python` asks for `p/python`, `iac/terraform` for `p/terraform`,
and the discovery step unions them, deduplicated. `lang/ts` and `iac/cdk` both ask for
`p/typescript`, and passing it twice would run the same rules twice. An empty list is a
claim rather than a gap, which is what `lang/api` states: opengrep matches code constructs
and a contract is data.

`--sarif` writes to stdout and is redirected. `--sarif-output=FILE` is documented and
silently writes nothing: verified against opengrep 1.26.0, where the flag produced no file
while the same scan on stdout produced valid SARIF 2.1.0 carrying the finding. A workflow
trusting the documented flag uploads an empty file and reports a clean scan.

The scan runs without `--error`, so a finding does not end the job before the SARIF reaches
the security tab. A later step reads the file back and fails there. The GitLab job does pass
`--error`, because it has no upload to protect, and it reads the same
`.github/security.d/` fragments rather than a second copy: those are committed data rather
than a GitHub feature, and two copies would disagree about which rules run.

A `discover` job parses the fragments and emits the matrix as JSON, so a new
`lang/*` layer contributes its jobs without the host layer or a caller changing.
`discover` also emits a count per matrix, because a matrix of zero entries is a
workflow error rather than a skip, and a docs-only repository renders no language
layer at all. A fragment states `codeql.supported: false` positively rather than
omitting the key, which is how `lang/rust` records that CodeQL has no Rust
extractor.

| Layer | Writes | Variables |
|---|---|---|
| `host/github` | `workflows/{wc-changes,wc-gate,wc-quality,wc-security}.yml`, `actions/ci-gate/`, `CODEOWNERS`, issue and pull-request templates, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` | `security_contact`, `coc_contact`, `default_branch`, `job_timeout_minutes` |

### Governance lives in a script

`host/github` renders the governance files and ships `scripts/repo_govern.py` for the rest.
Measured against a live repository rather than assumed: `gh api repos/<slug>` reports every
merge and feature setting, a freshly created repository returned zero rulesets and
`Branch not protected`, and GitHub reads no committed file for any of it. A layer renders a
file, so the API surface is a script. `../rules/choices.md` carries the split.

`gate` is the only required check, `just repo-govern` applies the settings, and
`just repo-govern-check` reports differences without changing anything, which is what CI can
run. Environment secrets stay manual: a secret passed to a script is a secret in a shell
history.

`host/gitlab` was written rather than ported: bailiff had no GitLab CI package, only
`repo/gitlab-repo`, so its four language fragments had no pipeline to be included by.

The `stages:` list is generated from what the `.gitlab/ci/*.yml` fragments declare.
GitLab fails the whole pipeline when a job names a stage the list omits rather than
skipping that job, and the include is a glob, so a language layer adopted later
contributes a fragment the list has to learn about. `quality` and `security` are
unconditional, because this layer's own two jobs sit there. A stage no `STAGE_ORDER`
entry covers fails the generator, where the message can name the fragment.

Governance wording differs between the hosts, though the substance does not. GitLab
has merge requests rather than pull requests, and no private vulnerability reporting
form, so `SECURITY.md` points at a confidential issue instead. That is the private
channel a GitLab project has without extra configuration.

`host/github` also takes `project_name` and `org`, threaded from `base/repo` for
the clone line and `CODEOWNERS`. An empty `org` writes a commented-out rule rather
than `*  @`, which GitHub reports as a parse error on every pull request.

The pull-request template goes to `.github/PULL_REQUEST_TEMPLATE.md`. A single
template inside a `PULL_REQUEST_TEMPLATE/` directory applies only through a query
parameter, so it silently never loads.

`SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, and `CODEOWNERS` carry
`_skip_if_exists`: each holds a contact address or a project-specific rule edited
after rendering.
| `host/gitlab` | `.gitlab-ci.yml` with the generated stages list and the glob include, `.gitlab/{CODEOWNERS,issue_templates,merge_request_templates}`, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, `scripts/gen_gitlab_stages.py`, `.just.d/gitlab.just` | `gitlab_host`, `security_contact`, `coc_contact`, `default_branch`, `job_timeout_minutes` |

## quality

| Layer | Writes | Variables |
|---|---|---|
| `quality/hooks` | `.pre-commit.d/{hygiene,beads}.yaml`, the generated root `.pre-commit-config.yaml`, `.mise/conf.d/hooks.toml`, `.just.d/hooks.just`, `scripts/merge_hooks.py` | `hook_exclude_patterns`, `max_file_kb`, `commit_scopes` |

Every hygiene check is on. prek is the manager.

`default_install_hook_types` is computed from the stages the folded hooks declare
rather than fixed. `prek install` writes one shim per entry, so a stage missing
from that list is a hook that never fires and reports nothing. A language layer
contributing a `pre-push` hook is what makes this necessary.

The merge runs from `scripts/merge_hooks.py` in the generated project, and the
copier task calls that same copy. A second copy in the layer would let the recipe
and the render fold fragments differently.

Conventional-commit checking uses `compilerla/conventional-pre-commit`, which
takes `--strict` to disallow `fixup!` and merge commits, `--force-scope`,
`--scopes <list>`, and positional custom types. It replaces a hand-written
74-line script. An empty `commit_scopes` drops `--force-scope`, which without an
allowlist demands a scope while accepting any spelling of it.

`.mise/conf.d/hooks.toml` pins betterleaks to 1.7.1 rather than the 1.7.2 that
GitHub lists. mise hides a release younger than its `minimum_release_age`, and
pinning the hidden one fails to install.

In a monorepo the language layer owns each member's `.pre-commit-config.yaml`
and prek unions them, so hooks travel with the language. `quality/hooks` then
carries the root config and the repository-wide hygiene hooks alone.

## workspace

| Layer | Writes | Variables |
|---|---|---|
| `workspace/monorepo` | the workspace manifest (`[workspace] members`, uv workspace, bun workspaces, or one go module), `scripts/add_member.py`, `.just.d/monorepo.just` | `layout`, `members`, `project_name` |
| `workspace/just` | `justfile` carrying `setup`, the aggregates, and one `import?` per `.just.d/*.just`, plus `scripts/gen_justfile.py` and `.mise/conf.d/just.toml` | none |
| `workspace/moon` | `.moon/workspace.yml`, `.moon/toolchain.yml`, `moon.yml` per member, `.just.d/moon.just` | `members`, `layout` |
| `workspace/devcontainer` | `.devcontainer/devcontainer.json` | `project_name`, `base_image`, `docker_in_docker`, `forward_ports` |
| `workspace/worktrunk` | `.config/wt.toml`, `.worktreeinclude` | `forge_platform`, `forge_hostname`, `worktree_includes` |

`workspace/monorepo` owns `just add`.

### The devcontainer has one toolchain source

`mise` is the only toolchain feature, and `postCreateCommand` is
`mise trust && mise install && just setup`. A per-language devcontainer feature would
pin a second copy of a compiler that could then disagree with what CI and a laptop
resolve from `.mise/conf.d/`.

`mise trust` has to precede `mise install`: an untrusted config is skipped silently
rather than failing, so the install would report success having installed nothing. The
container calls `just setup` rather than repeating its steps, so the two cannot drift.

`devcontainer.json` is JSONC, so it carries its reasoning in comments and `json.load`
rejects it. The layer's tests parse it through
`@devcontainers/cli read-configuration`, which is what an editor uses.

### moon alongside just, not instead of it

moon is the second task runner, not a replacement. `just` is the entry point a person
types and owns every repo-wide task with no member dimension. moon owns the member
graph underneath: it is the only thing here that models a dependency between members.

That distinction is what the layer buys, and it is not caching. Measured on a
three-member chain where `core` is depended on by `api`, which is depended on by `web`:

| Scenario | moon | the equivalent `just` loop |
|---|---|---|
| cold | 3.37s | 3.48s |
| nothing changed | 0.10s | 3.37s |
| one leaf changed | 1.24s | 3.37s |

The `just` loop costs the same every run because it has no graph to consult. moon
rebuilds a dependent when its dependency changes and skips it when only a sibling
moved, which is a correctness property rather than a speed one: a hand-written loop
either reruns everything or risks using a stale artefact. `moon run web:build` also
orders `core`, then `api`, then `web` from one command, with that order written nowhere
in the recipes.

`moon.yml` is generated per member by `gen_moon.py`, which reads the root manifest's
glob and each member's own dependency declarations. Nothing about the graph is asked,
because an answer could disagree with the manifest. Each toolchain spells a sibling
differently, and every spelling is read: rust `{ path = "../core" }`, ts
`"ui": "workspace:*"`, python the requirement string `lib>=0.1.0`. go declares no
edges, since a member there is a package inside one module.

moon 2.x renamed keys that render cleanly and fail only when the CLI reads them:

- The workspace section is `pipeline`, not `runner`.
- `vcs.client`, not `vcs.manager`. The published `workspace.json` still documents
  `manager`, and moon 2.4.6 rejects it, so the CLI is what this follows.
- A project's kind is `layer`, where 1.x used `type`.
- The task variable is `$MOON_PROJECT_ID`. There is no `$MOON_PROJECT_NAME`, and it is
  the directory rather than the package name, so `cargo -p` gets the manifest's name
  written in literally instead.

An output path is member-relative, which is wrong for cargo: it writes to the workspace
root `target/`, so rust declares `/target/debug` with moon's workspace-relative prefix.
A path nothing creates makes moon warn and cache nothing, so python and go declare no
outputs at all: `uv sync` writes into a shared `.venv`, and `go build ./...` discards
its binary. Inputs are declared per toolchain too. `src/**/*` matches nothing in a go
member, where sources sit beside the package, so no edit would ever invalidate the
build.

Each import is written `import?`, the optional form. Under the hard form a missing
file is a parse error that takes down every recipe in the justfile, so a fragment
deleted by hand would break `just` entirely rather than only its own recipes.

Every fragment shares one flat namespace, and just rejects a name defined twice.
Prefixing each recipe with its layer name is what keeps that from happening, and
`gen_justfile.py` refuses a colliding set while naming both fragments, since just's
own error breaks the whole file rather than the pair.

The aggregate recipes probe rather than depend. `check` and `each <phase>` ask
`just --show <name>` which per-language recipes exist, so one language renders and
one runs. A `needs:`-style dependency on a recipe no fragment provided is a parse
error, which is why `check` probes `hooks-all` rather than depending on it.

A fresh clone and a linked worktree need different work, so there are two recipes.

`setup` is for a clone: `mise trust` then `mise install`, each rendered language's
`<lang>-install`, then `hooks-install`, `rtk-setup`, and `apm-install`. Trust comes first
because an untrusted config is skipped, after which `mise install` reads nothing and
reports success.

`setup-worktree` is what `wt`'s blocking pre-start runs, and `setup_command` defaults to
it. It never runs `apm-install`: `.worktreeinclude` copies `apm_modules/` and
`node_modules/` from the primary, and a fresh `apm install` is slow. What it does run is
what a copy cannot provide, plus the language installs.

| Step | Why a worktree needs it |
|---|---|
| `mise trust` | a new directory is untrusted, and an untrusted config is skipped |
| `<lang>-install` | the user config excludes `.venv/` and `target/`, and an exclude beats an include, so those cannot be copied |
| `hooks-install` | a worktree's `$GIT_DIR` is `.git/worktrees/<name>/`, where git looks for its hooks, so shims in the primary never fire |
| `rtk-setup` | rtk records an absolute path per filter file, so this copy needs its own trust |

The language installs are close to free when a copy warmed them, well under a second for
each of uv, cargo, and go. They earn their place by catching a branch whose lockfile
moved, where the copied tree would otherwise build stale.

Both recipes probe with `just --show` rather than declaring dependencies, since a
dependency on a recipe no layer rendered is a parse error.

`--git-dir` replaced a `core.hooksPath` override. prek declines to install while an
ambient global hooksPath is set, which a machine-wide hook manager leaves behind, and it
writes no shim while printing only a note: a fresh clone silently had no hooks. Verified
on a machine with `git-defender`'s global path set, where the flag installed all six
shims and a bad commit message was blocked.

`workspace/worktrunk` sets `pre-merge = "just check"`, so a merge runs the same
gate CI does and cannot land what CI would reject. A project-defined command is
approved once and re-prompts when edited, so that line changing is visible.

Of the ten hooks worktrunk offers, the layer sets two. `pre-commit` is left to
prek, which owns the git-level hooks already. `post-commit`, `post-merge`, and
`pre-switch` describe work that belongs to CI or to the source worktree.
`pre-remove` would fire on every `wt merge`, since the user config sets
`remove = true`.

A dev server runs under `wt step tether`, whose teardown is automatic and needs no
`pre-remove` hook: the process group is signalled when the worktree goes. Its port
comes from `branch | hash_port`, which maps to 10000-19999 and is stable per
branch, so two worktrees never contend. `sanitize_db` does the same for a
per-branch database name.

`.worktreeinclude` names what a new worktree copies from the primary checkout. It
narrows rather than adds: a path is copied only when it is both gitignored and
listed. An exclude beats an include, and project excludes combine with the user's,
so a path the user config excludes cannot be recovered here.

Only `template-append` is honoured from a project `[commit.generation]`. The
command and the main template stay in user config, since they name which agent CLI
the developer has.

## release

| Layer | Writes | Variables |
|---|---|---|
| `release/release-please` | `release-please-config.json`, `.release-please-manifest.json`, the workflow, `.just.d/release.just` | `release_type`, `initial_version`, `default_branch`, `release_packages` |
| `release/cocogitto` | `cog.toml`, `.just.d/cog.just` | `initial_version`, `release_scopes` |
| `release/goreleaser` | `.goreleaser.yaml`, `.github/workflows/goreleaser.yml`, `.just.d/goreleaser.just`, plus the mise, gitignore, and quality fragments | `goreleaser_main`, `goreleaser_targets`, `goreleaser_version`, `go_version`, `goreleaser_sbom`, `syft_version` |
| `release/dep-updates` | `renovate.json`, `.github/dependabot.yml`, and the auto-merge workflow | `default_branch`, `auto_merge`, `renovate_timezone` |

Ecosystems follow from the language layers. renovate covers the language
ecosystems; dependabot covers action versions, which is what the existing
auto-merge workflow in `astro-up.github.io` consumes.

Both tools render, rather than one or the other as bailiff offered. renovate disables
its own `github-actions` manager, because dependabot's `fetch-metadata` action reports
the semver level of a bump and renovate emits no equivalent. Enabling both would open
two pull requests per action version.

`pep621` is the manager covering a uv `pyproject.toml`. There is no `uv` manager, and a
name renovate does not know silently updates nothing.

The auto-merge workflow triggers on `pull_request` and gates on
`github.event.pull_request.user.login`. `github.actor` can be spoofed by pushing to a
branch dependabot opened, which zizmor reports as `bot-conditions` at high confidence,
and `pull_request_target` runs with a writable token in the base repository's context
for no benefit here. A major update always waits for a person.

`release-please` and `cocogitto` are alternatives rather than companions: cog bumps and
tags from a developer's working copy, release-please through a pull request CI merges,
and a repository selecting both would tag twice. A profile picks one.

release-please has no glob support. `packages` takes a literal path per package, and the
`node-workspace` and `cargo-workspace` plugins only build a dependency graph over what is
already configured, so a member absent from the config is never versioned, tagged, or
written into the changelog.

`just add` registers the member as part of creating it, which is the moment the path is
known. Nothing reconciles the list afterwards. Adding an entry drops the `"."` package,
because a workspace releases its members rather than its root and the two tags would
collide, and turns on `include-component-in-tag`, without which every member's tag
collides on one version number.

The recorded versions are release-please's own after the first release, so an entry
already present keeps its version. A new member joins at the version the others share, or
at `initial_version` when they disagree, so a repository releasing 2.x ships no 0.1.0
package.

### release-please versions, goreleaser publishes

release-please computes the next version from the Conventional Commit subjects, writes
`CHANGELOG.md`, and pushes the tag. `release/goreleaser` triggers on that tag and attaches
what it built. Each tool covers what the other cannot, which is why they are separate
layers.

`changelog.disable: true` and `release.mode: append` are what keep them from colliding: the
changelog already exists before the tag does, and generating a second one from the same
commits would publish two that disagree on formatting.

Verified against goreleaser 2.17.1 rather than read from its documentation. `checksums` is
rejected outright, since the key is `checksum` singular. A snapshot build produced four
cross-compiled binaries and a checksums file from one runner, and the extracted binary
reported the version `ldflags` injected, which is what makes a bug report traceable to a
build.

`CGO_ENABLED=0` is what allows one runner to build every target. The release workflow sets
`cache: false`, unlike every other Go job: a poisoned cache entry would end up inside a
binary users download, which zizmor reports as cache-poisoning, and a release is infrequent
enough that a cold module download costs seconds nobody waits on.

`go-lib` does not render this layer. A Go library is consumed by module path and publishes no
artefact.

### SBOM and provenance

`goreleaser_sbom` is on by default and adds two things to a release: an SBOM per archive, and
a build provenance attestation over every published file.

The SBOM comes from goreleaser's own `sboms` block, which shells out to syft. Measured against
goreleaser 2.17.1 and syft 1.50.0: four archives produced four valid SPDX-2.3 documents of
about 3.8KB each, named `<archive>.sbom.json` beside their archive, with the cataloguing step
taking 36 seconds. `artifacts: archive` rather than `binary`, because the archive is what a
user downloads.

goreleaser does not install syft, so the workflow does. Without that step the release fails at
the cataloguing stage with the archives already built.

A pairing check runs before the attestation and fails when `dist/` holds no SBOM, because an
`sboms` block that produced nothing is a silent downgrade to no SBOM at all and the release
would otherwise succeed looking attested. Emptiness is tested with `${sboms[*]+x}` rather than
a length: under `set -u` an empty array reads as unbound on the runner's bash, which aborted
with `unbound variable` before reaching the message.

Provenance only, with no separate SBOM attestation. `actions/attest-sbom` warns that it is
deprecated in favour of `actions/attest`, and both take `sbom-path` as one file capped at 16MB
while goreleaser writes one per archive. A composite action cannot loop, so covering four
archives would need a matrix job, which means uploading and re-downloading `dist/` to attest
what the publishing job already holds. The SBOMs ship as release assets, and the provenance
subject list includes them.

The attestation runs after the publish, not before. Its subject is a digest, and a digest
exists only once the artefact does.

## docs

| Layer | Writes | Variables |
|---|---|---|
| `docs/site` | `docs/site/{astro.config.mjs,package.json,src/}`, `.gitignore.d/site`, `.mise/conf.d/site.toml`, `.just.d/site.just` | `docs_engine`, `site_url`, `project_name`, `description`, `node_version`, `repo_url`, `sidebar_autogenerate` |
| `docs/agents` | `docs/agents/**`, the `AGENTS.md` body, the `CLAUDE.md` symlink | none |
| `docs/adr` | `docs/adr/{0000-template.md,index.md}` | `project_name` |
| `docs/deploy-sibling` | `.github/workflows/pages.yml`, which builds and deploys in place | `pages_repo`, `default_branch`, `job_timeout_minutes` |
| `docs/deploy-split` | `.github/workflows/docs-publish.yml`, which pushes the built output across | `pages_repo`, `deploy_key_secret`, `default_branch`, `job_timeout_minutes` |
| `docs/api-refs` | `docs/site/scripts/{gen-api-refs.mjs,check-api-refs-fresh.sh,extract-<lang>-api.*}`, `.just.d/api-refs.just` | `api_ref_languages`, `api_ref_section` |

`docs_engine` is `starlight` or `fumadocs`, and one renders at a time: the comparison is a
derived boolean, since a conditional filename holding a quote breaks jinja compilation.
fumadocs brings React as a real dependency, where starlight needs none.

`site_url` is mandatory. Without an explicit `site:` the Astro sitemap integration warns
and emits nothing, so the sitemap is silently absent. Verified by building a rendered site:
with it, `sitemap-index.xml` and a populated `sitemap-0.xml` were produced.

An empty `repo_url` omits the edit link and the source link rather than rendering a dead
one.

Selecting `docs/api-refs` forces `docs/deploy-split`. The generated pages live in the code
repo, so the repo that holds the source is the one that has to build and push them.

`api-refs` ships the harness and one stub per language, not working extractors. An extractor
is where a language's whole toolchain leaks in, and none of it generalises:

| Language | Constraint the stub records |
|---|---|
| rust | rustdoc's JSON is nightly-only and its schema changes between nightlies, so any pin the scaffold shipped would be the wrong one |
| python | griffe reads statically, which is what lets it document a module whose import has a side effect |
| ts | typedoc needs `--excludeInternal`, or it publishes everything a package exports for its own tests |

The prior art this replaced ran to 2,622 lines, carrying one project's `packages/python`
layout and one project's nightly pin. Each stub emits valid empty IR, so the harness is
testable before an extractor exists.

`gen-api-refs.mjs` owns the page shape. An extractor owns one language and communicates only
through the IR documented in that file's header. A symbol whose `doc` is empty fails the run,
since a reference page with empty descriptions reads as complete while documenting nothing.
Every missing doc is collected and reported at once, because fixing them one run at a time is
the slowest possible order.

`check-api-refs-fresh.sh` checks two things:

- **Staleness.** `--check` renders to memory and writes nothing, so the gate cannot repair the
  drift it reports and pass on a rerun.
- **Determinism.** The generator runs twice and the outputs are compared. A renderer that
  iterates a hash map or embeds a timestamp makes every commit carry a reference diff, which
  makes the staleness check meaningless. With no extractor yet this step exits early, since a
  directory no render created is not evidence of nondeterminism.

Each deploy layer writes its own workflow. Pages deployment needs `pages: write` and `id-token: write`,
which the gate does not carry, and both are scoped to the deploy job rather than the whole
workflow.

`concurrency` is grouped per ref in both. A global group would make two different refs
cancel each other, where per ref two pushes to one branch serialise and the later wins.

Both write `.nojekyll` into the built output. Pages applies Jekyll unless told not to,
which drops every directory whose name opens with an underscore, and Astro emits `_astro/`,
so the assets 404 and the pages render unstyled.

`deploy-pages` clamps its own poll timeout and ignores a longer one, so `deploy-sibling`
runs a first attempt under `continue-on-error` and retries in a second step against the
same artefact.

`deploy-split` sets `keep_files: false`, so a page deleted here disappears there, and
excludes `.github` from the replacement. Removing the sibling's own workflow would leave
nothing to trigger on the next push, and it would stop deploying without saying so. An
`on.push.paths` filter is safe on both, unlike a required check: nothing waits on a deploy
workflow to report a status.

## agentic

| Layer | Writes | Variables |
|---|---|---|
| `agentic/apm` | `apm.yml`, `.just.d/apm.just`, `.gitignore.d/apm` | `apm_packages`, `apm_target`, `apm_cli_version` |
| `agentic/package` | `apm.yml` with a marketplace block, `packages/<name>/{apm.yml, .apm/skills, plugin manifests}`, `release-please-config.json` + manifest, `.just.d/package.just`, `.gitignore.d/package` | `project_name`, `package_name`, `category`, `marketplace_outputs`, `deploy_kiro`, `apm_cli_version` |
| `agentic/beads` | `.beads/` through `bd init --skip-hooks`, plus `.gitignore.d/beads` and `.just.d/beads.just` | `bd_prefix`, `bd_dolt_sync`, `bd_sync_remote`, `bd_auto_export`, `bd_dolt_auto_commit`, `bd_push_command` |
| `agentic/index` | `repomix.config.json`, `.gitignore.d/index`, `.just.d/index.just` | `index_languages`, `index_extra_ignores` |
| `agentic/rtk` | `.rtk/filters.toml`, `.just.d/rtk.just` | none |
| `agentic/speckit` | `.gitignore.d/speckit`, `.just.d/speckit.just`, and the locator added to `apm.yml` | `speckit_locator`, `speckit_integration`, `speckit_script_flavor`, `specify_cli_version` |
| `agentic/marketplace` | nothing; `tasks/recommend.py` reports what to register and install | none |

No per-harness configuration file. `agentic/marketplace` runs last.

### `agentic/apm` versus `agentic/package`

Both own `apm.yml`, so a repository takes one, never both. `agentic/apm` writes a
consumer's manifest, a `dependencies` block naming packages to install.
`agentic/package` writes a publisher's manifest, a `marketplace` block, and the
repository becomes its own marketplace. The `agentic-repo` profile, the 17-repo shape with no language layer,
is where `agentic/package` belongs.

The layer scaffolds the single-package shape shared by break-stuff and clerk: one
package under `packages/<name>`, published from the repository root. It grows to many
packages by hand.

### What apm requires, measured against 0.26.0

- Marketplace outputs are **claude and codex only**. `apm targets` also lists kiro, and
  the layer deploys the skill there, but `marketplace.outputs` has no kiro mapper and
  rejects the key. Deploy target and marketplace output are different axes: `targets:`
  names where a compiled skill lands, `outputs:` names which discovery catalog is built.
- The codex output requires `category` on every package, so it is a mandatory question
  rather than a free-text one.
- `apm pack` writes the repository-root catalogs, and none of the per-package
  `.claude-plugin/plugin.json` or `.codex-plugin/plugin.json`. Claude's `/plugin install`
  reads the per-package manifest at the catalog's `source:` path, so the layer renders
  those statically; without them a package lists but does not install.
- Each package needs its own `apm.yml`, or `apm pack --check-versions` reports it as
  `no_apm_yml`.
- `tagPattern` must match what release-please tags. The shipped
  `release-please-config.json` sets `include-component-in-tag: true` and
  `tag-separator: "--"`, which tags `<component>--v<version>`, so the marketplace's
  `tagPattern` is `'{name}--v{version}'`. Change one config and the other has to
  change with it.

The catalogs are committed generated artefacts, which is what `srobroek/agentic-packages`
and `srobroek/break-stuff` both do: both track `.claude-plugin/marketplace.json` and
`.agents/plugins/marketplace.json`, regenerate them on a pull request and fail on drift
without committing, and regenerate and commit at release. Committing them is what lets a
consumer resolve the marketplace from a clone with no build step.

`srobroek/speckit-conductor` commits neither, because the repository is the package rather
than a marketplace over several. A single-package bundle drops the fragment.

`apm pack` cannot be a copier task, since it needs uvx and may reach the network, so
`just package-build` performs it against a pinned CLI. `just package-check` is the
pull-request gate and passes `--check-clean --dry-run`, not `--check-clean` alone: without
`--dry-run` the run regenerates before diffing and so can never report drift.
`--check-versions` confirms only that a version renders under the pattern; it does not
verify the tag exists.

Registering a marketplace with a runtime is a separate matter. `apm marketplace add` writes
to `~/.claude/plugins/`, which is machine-global, so `agentic/marketplace` reports the
command rather than any layer running it.

`agentic/apm` writes the manifest but runs no install. `apm install` reaches the
network and needs uvx, so it would fail a render that had otherwise succeeded;
`just apm-install` performs it instead, against a pinned `apm_cli_version`.

Marketplace registration is machine-global, not per-project: `apm marketplace add`
writes to `~/.claude/plugins/`, so no template can seed it. `just apm-marketplaces`
is a one-time step per machine. A dependency locator carries its own source inline,
so a package resolves whether or not its marketplace was registered.

An empty `apm_packages` is valid. bailiff refused it with a validator, which made the
layer unusable until someone had chosen packages.

The agent then reads the rendered layer set and recommends packages against it:
`language-rust` and `rust-quality` for a rust layer, `mcp-tauri` for a Tauri
shell, `steering-infrastructure` for terraform, `speckit` when SpecKit is in use.
That match is judgement, so it belongs to the agent rather than a template.

`agentic/index` requires the `token-savings` package, which guards reading the
pack. It commits the patterns to `repomix.config.json`, which repomix reads
natively. They are then visible to anyone reading the repository.

Path filtering is the only lever that works. Measured against a 1,269-file
repository, the include and ignore pair cut a pack by 30.7 percent. The content
flags did not: `--remove-comments` takes 13.6 percent but deletes every `//` and
`#`, so safety notes and invariants go with them; `--compress` depends entirely on
whether its parser knows the language, so it is a second recipe rather than a flag on the
first: measured over this scaffold's python sources it cut 27,215 bytes to 14,321, a 47
percent reduction, and over its jinja templates it grew the pack by 0.1 percent because it
cannot parse them. `just pack-code` is the recipe that uses it;
`--remove-empty-lines`, `--no-file-summary`, and `--truncate-base64` take nothing;
`--style json` and `--parsable-style` make the output 10 percent larger.

One artefact, searched rather than read. A pack of a 4,107-file repository is 6.3
million tokens, roughly six context windows, so reading it cannot succeed; `rg` over it
lists every path in 0.009s and finds one in 0.010s, against 0.126s for the equivalent
walk of the live tree.

A separate metadata-only map was tried and dropped. It answered nothing the pack could
not, and keeping one artefact removes repomix's `--no-files` trap: there is no `--files`,
so a config carrying `files: false` cannot be overridden from the command line, and a
recipe pointing at such a config produces a metadata-only pack while calling itself
full.

Guarding the read belongs to the `token-savings` package, which already denies a
whole-file read of `repomix-full.xml` on both `Read` and `Bash`, so `cat pack` is
caught too. It carries a `TOKEN_SAVINGS_ALLOW_PACK_READ=1` escape hatch. This
layer ships no hook; `agentic/apm` names the package instead.

The pack needs its own config file. repomix has `--no-files` but no `--files`, so
the map's `files: false` cannot be overridden from the command line, and a single
config would silently produce a metadata-only pack. Both configs carry the same
`include` and `ignore`, or the pack would index what the map hides.

Every index artefact is ignored, including repomix's own default output names.
An unignored artefact is packed into the next one, which measured 38 percent of one
repository's whole pack, and `graphify update` has no output flag so it writes into
the tree regardless.

`agentic/apm` seeds two marketplaces: `srobroek/agentic-packages` and
`srobroek/slopvac`.

The worktrunk marketplace is not seeded, because `worktrunk-writer` and
`hooks-worktrunk` already wrap it with writer lifecycle, branch leases, and
cross-runtime enforcement that the single-plugin marketplace does not carry.

The repomix marketplace is not seeded either, because its MCP server earns
nothing over the CLI. `mcp-repomix`'s own refresh hook shells out to
`repomix --style xml --output <path> <root>`, and a pack costs 1.4s for 1,269
files or 3.6s for 4,107. No snapshot is stored: `docs/agents/index.md` names the
tool and the invocation, scoped with `--include`.

### `agentic/speckit`

That merge happened: `speckit`, `speckit-beads`, and `steering-speckit` are now one
package at `srobroek/speckit-conductor`, so the layer names a single pinned locator.

The layer is thin, because the package's own `speckit-setup` skill does the scaffolding.
Rendering a `.specify/` tree here would fork what `specify init` produces. It exists for
three things a skill installed under `apm_modules/` cannot do:

- The setup script appends `specs/**/spec-status.md` to the root `.gitignore`, and
  `base/gitignore` rebuilds that file from `.gitignore.d/`, so the entry is dropped on the
  next render. The layer carries it as a fragment instead, the same fix `agentic/beads`
  applies to bd's own appended block.
- `apm.yml` belongs to `agentic/apm` and is skip-guarded, so the locator is added by an
  idempotent edit. The `[]` placeholder that layer writes for an empty list is replaced
  rather than appended to, since a list cannot hold both.
- The script hardcodes twelve extensions and exits 0 when one could not be installed: a
  custom-source failure warns on stderr and continues. `agent-assign` is the one that
  matters, because the DAG hard-blocks `/speckit.implement` without it, so
  `just speckit-verify-extensions` checks the installed set rather than the exit code.

Renders after `agentic/beads`. The formula installs into `.beads/formulas/` and the guard
is inert without a workspace, so a repository with no `.beads/` gets a SpecKit that cannot
provision its phase DAG.

Pinned to `>=4.0.0 <5.0.0`. v4 is two breaking changes worth having: it dropped
`speckit-implement-task` and `speckit-research`, which the formula referenced zero times,
and it fixed a DAG that stalled permanently at step 3 because `bd gate check` does not see a
human gate. Each gate step now carries a condition and the formula takes an `autonomous`
variable, so an unattended pour filters the gates out and runs to completion. Verified that v4
installs and deploys exactly the two surviving agents.

The bootstrap is not a copier task. It runs `specify init`, reaches a catalog over the
network for the extensions, and calls `bd init`, so a render that had otherwise succeeded
would fail on it.

Holding architecture decisions as beads is a separate package, `adr-as-beads`: a
`decision` bead is the record and `.pre-commit.d/adr.yaml` renders it to
`docs/adr/NNNN-title.md`. That fragment renders unconditionally and no-ops without
`bd`, so a repository that has not adopted it pays nothing.

The renderer also rewrites the row block in `docs/adr/index.md`, between two markers.
Without that the index `docs/adr` ships keeps its placeholder row while numbered files
accumulate beside it, so the first artefact a reader opens reports no decisions. Only
the rows are generated: the prose above them is the project's, a hand-written record
takes a row below the block, and an index with no markers is left untouched rather than
injected into, because `docs/adr` may not have rendered at all.

A rendered record opens with its frontmatter. A leading HTML comment pushes `---` off
line one, and a parser then reads the block as body text, so `status`, `date`, and
`bead` go invisible to anything indexing the records; the provenance note follows the
block instead.

`agentic/beads` runs `bd init --skip-hooks` and keeps everything else bd writes.
Neither flag is an answer: `--skip-hooks` is always passed and `--skip-agents` never
is, so no answer can turn the compaction hooks off. bailiff's version passed
`--skip-agents` unconditionally.

It renders after `docs/agents`, because bd appends a marked
`BEGIN BEADS INTEGRATION` block to an existing `AGENTS.md` and leaves the `CLAUDE.md`
symlink alone. With neither present it writes its own beads-only file instead, which
would then be what the repository's agents read first.

The properties it sets come from surveying every repository here that uses beads.
`sync.remote` is the only one all five set, and it carries a `git+ssh://` or
`git+https://` prefix, which is what marks it a Dolt remote over the git transport
rather than a plain one. An empty answer derives it from the git origin, normalising an
scp-style address first. `export.auto` is set in slopvac, `dolt.auto-commit: batch` in
platevault, and `repos.additional` in skymath for cross-repository hydration.

`metrics.*` and `no-git-ops` are set in the user's own `~/.config/bd/config.yaml`, so no
layer writes them. `metadata.json` holds bd's generated `project_id` and database name,
which are per-clone rather than per-template.

bd also appends four ignore patterns to the root `.gitignore` under a header with no
end marker. `base/gitignore` rebuilds that file from `.gitignore.d/`, so the task
moves those lines into a fragment; left in place they survive until the next render
and then vanish.

bd installs two separate sets. Its git hooks are five 1.3KB shims running
`bd hooks run <event>` for `pre-commit`, `post-merge`, `post-checkout`,
`pre-push`, and `prepare-commit-msg`; `quality/hooks` reproduces those as local
prek entries, since prek supports all five stages. What made `--skip-hooks`
necessary was the ambient hook binaries copied in alongside them.

What each event earns, from bd's own git-integration reference:

| Event | What it does |
|---|---|
| `pre-commit` | exports `.beads/issues.jsonl` when `export.auto` is set, so it is committed alongside the change |
| `prepare-commit-msg` | adds an `Executed-By:` trailer when an agent made the commit |
| `post-merge` | imports JSONL as a legacy fallback; with `sync.remote` set, `bd dolt pull` is the real sync |
| `post-checkout` | runs chained hooks |
| `pre-push` | runs chained hooks |

None of them pushes the database. Every workflow in bd's documentation runs
`bd dolt push` by hand before `git push`, and running each event directly produced no
output and no push. The issues would therefore stay on one machine.

`quality/hooks` adds `scripts/bd-dolt-push.sh` at `pre-push` to close that. A commit is
local, so a git push is the moment the database has to follow; pushing per commit would be
work nobody is waiting on.

It never blocks. An unreachable remote or a missing wrapper reports and exits 0, since
`bd dolt push` is recoverable by running it again and blocking would make an offline
push impossible. With no `sync.remote` configured it exits before doing anything.

bd's own `dolt.auto-push` stays off. It pushes after a write on a five-minute debounce,
which leaves a window where the remote is behind and nothing reports it, and its
documentation warns that concurrent pushes to a git-protocol remote "can corrupt or
strand remote history" with more than one writer. It also ignores
`custom.bd-push-command`, so on a machine needing the wrapper it would hang every write
until its timeout. The hook pushes at the one moment that matters instead.

The push command is read from `custom.bd-push-command` rather than assumed to be `bd`.
Where the database runs in a container a direct `bd dolt push` hangs until it times out,
and that key names the wrapper that works. `custom.*` is bd's namespace for user-defined
keys, so this is a local convention rather than something bd reads itself.

Its agent hooks come in two more sets, both kept as bd writes them. Four codex
lifecycle entries in `.codex/hooks.json` run `bd codex-hook` on `SessionStart`,
`UserPromptSubmit`, `PreCompact`, and `PostCompact`. One Claude entry in
`.claude/settings.json` runs `bd prime --hook-json` on `SessionStart`.

Those hooks reload beads context after compaction, which is what makes an
`AGENTS.md` carrying no beads prose safe. `--skip-agents` would remove them and
is therefore not used.

## container

| Layer | Writes | Variables |
|---|---|---|
| `container/image` | `Dockerfile`, `.dockerignore`, `.just.d/container.just`, the mise, hook, CI, and security fragments | `container_language`, `container_runtime_base`, `registry`, `expose_port`, `trivy_severity`, `container_attest` |

`docs/architecture.md` carries the measured base image policy and the build-scan-push
order. The layer's own `Dockerfile` repeats the measurement beside the `FROM` line, so the
reason for the base is where the choice is made.

Only hadolint runs at commit time. Building an image takes minutes and needs a daemon, so
the build and the image scan are CI. `trivy` runs twice against different things: `config`
mode reads the Dockerfile in the language-blind security workflow, and `image` mode reads
the built image in this layer's own job.

`container_attest` is on by default and attests the pushed image's provenance. The subject is
the digest the registry returned, taken from the push step's own output, rather than a tag: a
tag is mutable, so an attestation bound to one says nothing about what a puller receives
later. `push-to-registry` stores the bundle beside the image, which is what lets
`gh attestation verify oci://...` work for someone holding the image and not the repository.

The step is gated on the push, since a pull request builds without publishing and there is no
digest to bind.

This job sets `cache: false` on mise, unlike every other mise-action call in the scaffold. It
pushes an image users pull, so a poisoned cache entry would end up inside that image. zizmor
reported exactly that against this workflow at high severity before the change. Only hadolint
and just come from mise here, so a cold install costs seconds. `release/goreleaser` sets the
same flag on setup-go.

## iac

| Layer | Writes | Variables |
|---|---|---|
| `iac/terraform` | `infra/{bootstrap,modules,envs,tests}`, `.tflint.hcl`, `.pre-commit.d/terraform.yaml` | `environments`, `aws_region`, `state_bucket` |
| `iac/cdk` | `.projenrc.ts` with `runner: tsx()`, `app: npx tsx`, and `github: false`, plus `.just.d/cdk.just` and the mise, gitignore, and security fragments | `cdk_version`, `projen_version`, `tsx_version`, `node_version` |

`environments` defaults to `[dev, prod]`.

### The ts-node trap has two call sites, not one

`projenrcTsOptions.runner: TypeScriptRunner.tsx()` governs only how `.projenrc.ts`
itself executes. projen writes `cdk.json`'s `app` separately, as
`npx ts-node -P tsconfig.json --prefer-ts-exts src/main.ts`, so with the runner set and
`app` left alone `npx projen` passed and `cdk synth` still failed. Both are overridden.

Reproduced rather than assumed, against projen 0.101.22: under TypeScript 7.0.2 the
default ts-node runner throws inside `findAndReadConfig`, and after both overrides
`npx projen` and `cdk synth` each exit 0.

`packageManager` is set explicitly too. projen otherwise defaults to `yarn_classic` and
warns that the option will become required, and nothing else here uses yarn.

### One root module, not one per environment

`infra/` is a single root module. An environment is a pair of files under
`infra/envs/`, `<env>.tfbackend` and `<env>.tfvars`, rather than a directory of its
own.

This follows from the two decisions `architecture.md` fixes. Partial backend
configuration through `-backend-config=envs/<env>.tfbackend` configures one
`backend "s3" {}` block, which presupposes one root module, and `tofu test` reads
`tests/` under the root module, so `infra/tests/` is found only from there. An
earlier version of the row above said `envs/<env>`, which contradicted both: that
shape needs `-test-directory` on every test run, and it repeats the provider and
backend blocks per environment, which is the repetition partial configuration
removes.

The corollary is that a child module's source is `./modules/<name>`. `tofu test`
resolves a module source from the root module rather than from the test file, so
the `../` form fails under plan and test alike.

`bootstrap` is the exception, a second root module keeping local state, because it
creates the bucket the first one stores its state in.

### What the tools require, measured

| Constraint | Consequence if ignored |
|---|---|
| tflint reads no parent directory's config | every directory lints with the default rules, reporting findings `.tflint.hcl` disabled |
| tflint's failure threshold is error | a run exits 0 having printed real warnings |
| `tflint --init` needs a GitHub token | 403 rate limit, then "Plugin not found" per directory |
| `terraform_required_version` covers child modules | the lint gate fails on `modules/*` |
| pre-commit-terraform prefers `terraform` over `tofu` | the hooks run terraform against an OpenTofu repository |
| the hook ids are `terraform_*`, and tflint's is `terraform_tflint` | prek rejects the fragment on an unknown id |
| just shares jinja's `{{ }}` | an unwrapped fragment loses every recipe parameter |

Each was found by rendering the layer and running the tool, not by reading the
template.

## Render order

```
base/repo precheck
<generator>            single repo only: cargo new, uv init, go mod init, bun init
base/license
base/repo
workspace/monorepo     monorepo: the root manifest, then the generator per member
lang/*
host/{github,gitlab}
release/*  iac/*  docs/*
agentic/{apm|package,beads}
agentic/speckit        when SpecKit is in use: needs the beads workspace
quality/hooks
workspace/just
workspace/moon         monorepo only: the member graph, after every member exists
workspace/devcontainer container only: postCreateCommand calls `just setup`
base/gitignore
agentic/marketplace
```

The generator runs before every layer. `cargo init` writes no `license` key and
`uv init` writes its own `pyproject.toml`, so a language layer patches an
existing manifest rather than creating one.

`workspace/monorepo` precedes `lang/*` so the manifest exists before members render.

The generator's position depends on the shape. In a single repository it runs first,
against the repository root, and a language layer patches the manifest it wrote. In a
monorepo it cannot: `cargo init .` writes a `[package]` root, `workspace/monorepo`
then skips the file it finds, and no `[workspace]` section is ever written, so the
repository silently is not a workspace. Verified by rendering in that order.

A monorepo therefore renders the root manifest first and runs the generator per member,
which is what `just add` does. Members resolve through the manifest's glob, so a
directory created under it is a member with no edit to the root: confirmed against
cargo, uv, and bun, and go needs no registration because a member is a directory in
one module.

`agentic/beads` follows `docs/*` because bd appends to an existing `AGENTS.md` and
writes its own beads-only one when none exists. The order is what decides which file
a repository's agents read first.

`quality/hooks` follows `iac/*` because it folds `.pre-commit.d/*` into the root
config, and `iac/terraform` contributes a fragment. Rendering it earlier would
leave that fragment out, with nothing to report the omission: prek reads the merged
file and never sees the fragment directory.

Re-rendering any fragment-contributing layer therefore needs the merge again.
`just hooks-install` and `just hooks-all` both run it first, so the config cannot
lag the fragments.

`workspace/just` and `base/gitignore` aggregate what earlier layers contributed,
so they follow every contributor including `agentic/*`: apm and beads add
ignores for `apm_modules/` and `.beads/dolt/`, and may contribute a
`.just.d/apm.just`.

Both of the generated files can therefore go stale when a layer is adopted later.
`just just-check` and `just hooks-all` catch each case, and the quality workflow runs
the first, so a pull request cannot merge a justfile that omits a fragment. Both
compare in a copy rather than rewriting, since a check that fixes what it checks
leaves a dirty tree and passes on the rerun.

`agentic/marketplace` reads the finished tree.

A profile states this order directly. 34 layers with a fixed order need no
dependency solver.

## Profiles

`profiles/*.yml` names, per shape, its layer set in render order, its generator, the
answers fixed or derived for it, and the commands that prove a rendered tree builds.
`profiles/README.md` carries the format and the survey counts.

Thirteen shapes, matching the generator table in `../docs/architecture.md`.
`scripts/profiles.py` validates every one against `templates/`, and `just profiles-build`
renders each into a temporary directory and runs its own build.

That check earns its cost. A tree that renders is not a project that builds, and it caught
two ordering bugs no unit test did:

- `lang/api` declared `after: host/github` while `host/github` declares `after: lang/*`,
  a cycle no profile could satisfy. Every other language layer renders before the host,
  because the host's matrix discovers the fragments they contribute.
- `rust-gui` put `workspace/moon` after `workspace/just`, so the justfile's import block
  never learned about `.just.d/moon.just`. The rendered tree then failed
  `just just-check`.

The second is why the validator checks aggregation separately from each layer's own
`after`. A contributor has to precede its aggregator, and `workspace/just` cannot express
that by naming every present and future contributor in its own list.

A build command asserts only what the layers produce. `render_profile.py` does not run the
generator, since `cargo new` and `create-better-t-stack` reach the network or need a
toolchain the machine may lack, so `cargo build` there would fail for a missing manifest
rather than for anything a layer got wrong.

## Steering generation

`docs/agents` ships `scripts/gen_steering.py`, which fills the marked blocks in
`docs/agents/` from what is on disk. `docs/steering.md` carries the ownership table; the
generator implements the generated half.

A pure function of the tree. Nothing is asked, because an answer could disagree with the
files an agent will actually read, and nothing reaches the network, so
`just steering-check` can gate it in CI.

| Reads | Produces |
|---|---|
| `justfile` and `.just.d/*` | the command surface in `index.md` |
| `.mise/conf.d/*.toml` | the toolchain pin table |
| each language layer's tool config | one `quality/<lang>.md` leaf, plus its index row |
| `.github/workflows/*` | the job list and the gate's role |
| `release-please-config.json` | the tool and the real tag shape |
| the workflows and the Dockerfile | variable names, never values |

Both markers carry the block name: `<!-- END GENERATED: index -->`, not a bare
`<!-- END GENERATED -->`. A generator matching the bare form finds nothing, writes an empty
block, and reports that it wrote the file.

A file with no marker is never written after it is first created, which is what keeps
`conventions.md` and each leaf's "why a rule is off" section. `--check` reports drift
without repairing it, so the gate cannot destroy a hand edit and pass on the rerun.

Adding a language adds `quality/<lang>.md` and one index row. No existing file grows, which
is the property `docs/steering.md` asks for.

## Linting this repository

`just lint` covers the python and the prose. `just lint-config` covers the structural
surface: yamllint, taplo, JSON parsing, actionlint, and zizmor.

Both run in `just check`. The layers put these tools in a generated project's CI, and a
scaffold that does not run them on itself has 87 unchecked YAML files and a workflow nobody
audits, which is what this repository had until the gate existed.

They skip `templates/`. A `.jinja` file is deliberately not valid YAML, TOML, or JSON: it
holds jinja delimiters, and a conditional filename is not a path a parser accepts. The layer
tests cover those instead, by rendering the template and running the real parser against the
result.

## Running the tests

Most tests render a layer and run the real tool against the result, which is what catches
the defects a template read cannot. That makes the suite wait on toolchains rather than on
CPU, and every test renders into its own `tmp_path` sharing no state, so it parallelises
cleanly.

| Command | Measured on 14 cores |
|---|---|
| `just test` | 160s, 543 passing |
| `just test-serial` | 889s, for a readable failure or a debugger |
| `just test-fast` | skips what installs an npm tree, builds an image, or compiles a crate |

A test that shells out to something expensive carries `@pytest.mark.slow`. An npm install
or a container build dominates a run otherwise, and the cdk fixture is session-scoped for
the same reason: its install and synth cost about 40 seconds and every test reading it only
reads.

## Contribution points

| Contributed as | Combined by |
|---|---|
| `.gitignore.d/<name>` | `gitnr create` in `base/gitignore` |
| `.github/{quality,security}.d/<name>.yml` | a matrix in the host layer's shared workflow |
| `.pre-commit.d/<name>.yaml` | see below |
| `.mise/conf.d/<name>.toml` | mise reads the directory |
| `.just.d/<name>.just` | `import?` lines written by `gen_justfile.py` in `workspace/just` |
| `.github/workflows/wc-*.yml` | the caller the agent writes |
| `.gitlab/ci/<name>.yml` | GitLab's `include: local:` glob |

### The agentic hooks with a git event

Three of the thirteen agentic-packages hooks act on a git action, and those move into
`.pre-commit.d/git-actions.yaml`. As PreToolUse hooks they fire only for an agent whose
harness is configured; as prek entries in a committed config they fire for every committer and
survive an agent running without that config.

| Hook | Stage | Behaviour |
|---|---|---|
| `normalize-close-keywords` | `commit-msg` | rewrites the message in place |
| `attribution-guard` | `commit-msg` | advisory, prints and exits 0 |
| `no-force-push-to-default` | `pre-push` | refuses a non-fast-forward |

`Closes #1, #2, #3` closes only `#1`, because GitHub binds a closing keyword to the first
issue in a list. The rewrite distributes it so the rest close too, verified end to end through
prek's `commit-msg` stage.

The attribution guard prints rather than blocking. A commit message is trivially fixable and a
denied commit costs more than a nudge; the enforcing copy is the `commits` job in the quality
workflow, which reads the whole pull request range. Its patterns are vendored rather than
rewritten, because they carry recorded false-positive fixes: the bare
`users.noreply.github.com` domain was removed after an ordinary human co-author trailer was
reported as AI attribution.

The rest stayed behind, and the fragment records why beside the three that moved.
`hooks-quality` fires on an edit, which git never sees. `reset --hard`, `clean -fd`, and
`checkout --` are pre-execution guards: by the time a git hook runs, the work is already gone.
Only the force-push guard has an event, and `pre-push` is it.

A pre-push hook receives its refs on stdin and cannot see the `--force` flag, so the guard
compares ancestry instead: a non-fast-forward push means the remote commit is not an ancestor
of the local one.

### Hook fragments

In a monorepo each package carries a real `.pre-commit-config.yaml`, and prek's
workspace mode unions them with hooks namespaced `<dir>:<hook-id>`. Nothing
merges.

In a single directory two language layers cannot both own the root config, so
`just hooks-merge` concatenates `.pre-commit.d/*.yaml`. prek skips dot-prefixed
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
