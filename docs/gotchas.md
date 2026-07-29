---
status: accepted
date: 2026-07-29
---

# Gotchas

Failures found by running the tools. Each one produces a wrong result silently or
fails at first use. The layers encode the fix; this file records why the fix
exists, and seeds `docs/agents/gotchas/` in a scaffolded repository.

## copier

| Failure | Cause |
|---|---|
| `found character '%' that cannot start any token` | `copier.yml` parses as YAML before jinja renders it. A top-level `{% set %}` fails. Use an inline expression inside a value |
| `SyntaxError` pointing at an unrelated line | a conditional filename containing a quote breaks jinja compilation, because the filename is embedded in generated Python. Use a derived boolean carrying `when: false` |
| a `yaml`-typed answer rejects its own default | a jinja list renders as a Python repr with single quotes. Append `| tojson` |
| a conditional path renders partially | each path segment needs its own guard |

`_external_data` resolves relative to the destination, so a layer can read a
sibling's answers file. A missing file warns and falls back to the default.

## Language tooling

| Tool | Failure |
|---|---|
| `cargo init` | writes no `license` key, so `cargo-deny` fails its licence check against the crate itself |
| golangci-lint v2 | rejects v1's top-level `linters-settings`; settings nest under `linters.settings` |
| golangci-lint | `gosec` ships inside it and is off by default |
| ruff | `DOC` rules are preview-gated and check nothing without `preview = true` |
| ruff | `D` in `select` makes a bare `ruff check` fail, defeating the advisory intent |
| bun | `bun exec` is not a command; use `bunx` |
| gix | needs an explicit `sha1` or `sha256` feature or the build fails |

## projen

`projen new` produces a project that cannot synthesise. It pins
`typescript: "*"`, which resolves to TypeScript 7, and `ts-node` fails against
it with `TypeError: Cannot read properties of undefined (reading 'fileExists')`.
The failure is identical on Node 22 and 24.

`runner: typescript.TypeScriptRunner.tsx()` fixes it, but the synth that would
write that task is the one that fails. Install `tsx` and run
`npx tsx .projenrc.ts` once directly.

`projenrcTsRunner` is not an option name and is ignored without warning. The
option is `runner`.

`.projen/tasks.json` and 16 other files are mode `444`.

## better-t-stack

`--yes` rejects any stack flag. `addonOptions` has no flag form. Use
`create-json`.

Requesting `biome` and `oxlint` together writes only `biome.json`; oxlint is
dropped with no warning. They are alternative toolchains, and `oxlint` alone
brings `oxfmt` with it.

Its tauri addon puts `src-tauri` inside the web app with no Cargo workspace.
A Rust-first project wants the reverse: a workspace member at
`apps/<name>/src-tauri` using `edition.workspace = true`.

`skills` writes nothing when no frontend is selected. `mcp` writes MCP
configuration for three editors.

## GitHub Actions

| Failure | Cause |
|---|---|
| a docs-only pull request cannot merge | `on.push.paths` gates the whole workflow, and a required check that never runs stays pending. Filter at job level |
| zizmor reports `unpinned-uses` on `actions/checkout` | the audit rejects a tag on any action, including first-party ones. Pin every action to a SHA |
| zizmor reports a credential finding | `actions/checkout` leaves `GITHUB_TOKEN` in `.git/config` by default. Set `persist-credentials: false` |
| a hung job burns six runner hours | the default timeout is 360 minutes. Set `timeout-minutes` |
| `deploy-pages` times out and the job fails | the action clamps its own poll timeout and ignores a longer one. Run the first attempt with `continue-on-error` and retry in a second step |
| a cross-repo docs publish stops deploying | replacing the target repository's content removed its workflow. Preserve `.git` and `.github` |
| concurrent pull requests cancel each other | a global `concurrency` group. Scope it per ref |
| `/_astro/` returns 404 | GitHub Pages applies Jekyll. Add `.nojekyll` |

## GitLab CI

The Terraform CI templates were removed in 18.0. The replacement is the
`components/opentofu` component. Components resolve from the instance they run
on, so a self-managed instance needs the component mirrored.

`include: local:` accepts globs. `*` matches one directory level and `**`
recurses. Merge order across a glob is not deterministic.

Plan artifacts published for the merge-request widget are readable by anyone
with the Guest role and are not encrypted. Set `public: false`.

## Hooks

`lefthook install` tries to rewrite files in the configured `core.hooksPath`
directory and fails without write access to it. `--reset-hooks-path` unsets a
repo-local override without restoring it.

`prek install` refuses to run while `core.hooksPath` points outside the
repository, and succeeds once it is set repo-locally.

`prek` skips dot-prefixed directories during discovery, so a `.pre-commit.d/`
fragment directory is invisible to it. It has no `extends` key; unknown keys are
ignored with a warning.

`pre-commit` rejects `repo: builtin` with `Missing required key: rev`, so
builtin hygiene hooks require prek.

## Astro

An Astro config without `site:` skips sitemap generation, warning rather than
failing.

## Toolchain

`gitnr` writes to a path that must already exist; `-s` writes `.gitignore` in
the working directory.

A `mise.toml` key holding a colon, such as `pipx:structkit`, must be quoted or
every `mise install` fails.
