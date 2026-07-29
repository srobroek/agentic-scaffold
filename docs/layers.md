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
| `workspace/moon` | `.moon/workspace.yml` | `members` |
| `workspace/devcontainer` | `.devcontainer/devcontainer.json` | none |
| `workspace/worktrunk` | `.config/wt.toml`, `.worktreeinclude` | `forge_platform`, `forge_hostname`, `worktree_includes` |

`workspace/monorepo` owns `just add`.

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
| `agentic/apm` | `apm.yml`, `.just.d/apm.just`, `.gitignore.d/apm` | `apm_packages`, `apm_target`, `apm_cli_version` |
| `agentic/beads` | `.beads/` through `bd init --skip-hooks`, plus `.gitignore.d/beads` and `.just.d/beads.just` | `bd_prefix`, `bd_dolt_sync`, `bd_sync_remote`, `bd_auto_export`, `bd_dolt_auto_commit`, `bd_push_command` |
| `agentic/index` | `repomix.config.json`, `.gitignore.d/index`, `.just.d/index.just` | `index_languages`, `index_extra_ignores` |
| `agentic/rtk` | `.rtk/filters.toml`, `.just.d/rtk.just` | none |
| `agentic/marketplace` | nothing; it reports recommended installs | none |

No per-harness configuration file. `agentic/marketplace` runs last.

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
`#`, so safety notes and invariants go with them; `--compress` takes 21 percent
against the 70 its documentation claims, and grows comment-dense files;
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

Choosing SpecKit pulls `speckit`, `speckit-beads`, and `steering-speckit`
together. `speckit-beads` is what connects SpecKit to `bd`.

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

## iac

| Layer | Writes | Variables |
|---|---|---|
| `iac/terraform` | `infra/{bootstrap,modules,envs/<env>,tests}`, `.tflint.hcl`, `.pre-commit.d/terraform.yaml` | `environments`, `aws_region`, `state_bucket` |
| `iac/cdk` | `.projenrc.ts` with `runner: tsx()` and `github: false` | `cdk_language` |

`environments` defaults to `[dev, prod]`.

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
agentic/{apm,beads}
quality/hooks
workspace/just
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

A profile states this order directly. 19 layers with a fixed order need no
dependency solver.

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
