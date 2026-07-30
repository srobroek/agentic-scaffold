# Choices

What the agent decides without asking. Each row replaces a question.

## Ask

Six questions, one at a time.

1. What are you building? Name plus one line.
2. Which language?
3. One package, a monorepo, or several repos?
4. License. State the derived answer and accept an override.
5. Create the remote now?
6. If yes, private or public. Read a public answer back before running.

Ask about infrastructure only when the answer to question 1 implies it.
`terraform` and `cdk` are a genuine either/or and cannot be derived.

Ask about `api` and `database` for `ts-app`. A CLI or static site needs
neither, and the choice is not inferable from the project name.

## Derive

| Decision | Rule |
|---|---|
| Task runner | `just` at the root of every profile |
| Sub-runner | all-TypeScript monorepo uses turbo, which better-t-stack generates; mixed-language monorepo uses moon; single package uses `just` alone |
| Layout | one language and one deployable is `single`; two deployables or two languages is `monorepo` |
| License | niche library is `mpl-2.0`; application is `agpl-3.0-only`; template or dev tooling is `apache-2.0` |
| CI languages | the set of `lang/*` layers that rendered |
| CI jobs | the union of jobs those layers contribute, plus quality and security |
| CI host | `github` unless the remote is GitLab |
| Default branch | `main` |
| Project layout | `src/` versus flat, binary versus library, from what the project does |
| Framework | from the ask: "FastAPI service" selects fastapi. Ask only when two frameworks fit equally |
| `bd_prefix` | first three consonants of the project name |
| `decisions_dir` | `docs/adr` |
| `placement_dir` | `infra` for terraform, `infra/cdk` for cdk |
| Coverage floor | 80 percent |
| Version matrix | current stable only |
| Docs engine | `starlight` |
| Docs topology | sibling repo builds itself, unless the `docs/api-refs` layer renders |
| Structural tool | `gitnexus` when the repo has more than 50 source files, otherwise `repomix` |

## Fixed

Hard-coded in the layers, outside the interview and the derivation table.

| Domain | Choice |
|---|---|
| Python | uv, ruff, ty, pytest, deptry, nox |
| TypeScript | bun, biome, oxlint, vitest, tsc, knip |
| Rust | stable, edition 2024, nextest, cargo-deny, cargo-machete, cargo-llvm-cov |
| Go | golangci-lint v2 schema, gosec, revive, govulncheck |
| Hooks | prek with `repo: builtin` hygiene, betterleaks, trufflehog |
| CI quality | actionlint, zizmor, cspell, lychee, taplo, yamllint, markdownlint, scc, lizard |
| CI security | codeql, trivy, osv, secret scan |
| Release | release-please |
| Dependencies | renovate |
| Actions | SHA-pinned, `persist-credentials: false`, `timeout-minutes` set |
| Infrastructure | OpenTofu, S3 backend with `use_lockfile = true` |

Offer `pre-commit` in place of prek only when asked for by name. Offer
`cocogitto` in place of release-please only when asked for by name.

## Ruff configuration

`preview = true` is required or the `DOC` rules silently check nothing. `D`
stays out of `select`, because including it makes a bare `ruff check` fail and
defeats the advisory intent. ruff has no per-rule
severity, so warn-level and block-level rules run as separate invocations.

## Rust license metadata

`cargo init` writes no `license` key, and `cargo-deny` then fails its licence
check against the crate itself. The rust layer writes the SPDX identifier that
matches the chosen `LICENSE`.

## Go lint configuration

golangci-lint v2 rejects v1's top-level `linters-settings`. Settings nest under
`linters.settings`. `gosec` ships inside golangci-lint and is off by default.

## TypeScript commands

`bunx <tool>`, never `bun exec <tool>`. `bun exec` is not a command.

## Public repository creation

`gh repo create --public` publishes immediately. Read the name, owner, and
visibility back to the user and wait for confirmation before running it.

## Repository governance

The configuration surface that is neither a template file nor a CI job. Measured against
a live repository rather than assumed: `gh api repos/<owner>/<repo>` reports every merge
and feature setting, `/rulesets` and `/branches/<branch>/protection` report the rest, and
GitHub reads no committed file for any of them. A freshly created repository returned zero
rulesets and `Branch not protected`.

So the split is not a judgement call:

| Setting | Where it lives |
|---|---|
| `CODEOWNERS`, issue and pull-request templates, `SECURITY.md`, `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md` | committed files, `host/github` |
| branch protection, required checks, merge queue, allowed merge types, auto-merge, repository features | `gh api`, through `just repo-govern` |
| organisation versus personal owner, and visibility | asked, questions 5 and 6 |
| environment secrets | never automated: a secret in a script is a secret in a shell history |

`host/github` owns the files and ships the script. A layer renders a file, and GitHub reads
no file for any of these settings, so the API surface is a script.

Fixed settings, applied by the script:

- `gate` is the only required status check. It lists every other job in `needs:` and
  receives `toJSON(needs)`, so a new job is covered without touching branch protection.
- Squash only. A merge commit puts a second author's subject in the history that
  release-please then reads, and a rebase rewrites the commits CI already checked.
- Delete the branch on merge, and enable auto-merge.
- Issues on, wiki and projects off. A wiki is an unversioned second place for
  documentation the `docs/` tree already owns.
