# CI composition

Each recipe contributes reusable workflows. What wires them depends on which recipes
rendered, so the caller is derived per repository rather than shipped.

## GitHub

`.github/workflows/ci.yml` is generated. `scripts/gen_caller.py` reads
`.github/workflows/`, finds every `wc-lint-<lang>.yml` and `wc-test-<lang>.yml`, and
rewrites the whole file. `just ci-sync` runs it, and so does the render. Adopting a
language layer is that one command.

Job graph:

```
changes ─┬─> lint-<lang> ─┐
         └─> test-<lang> ─┤
                          ├──> gate
quality ──────────────────┤
security ─────────────────┘
```

What it emits:

- `changes` runs first and outputs the filter keys that matched. Every language job takes
  its own key as a condition. A key's path set names that language's sources, the
  manifests and lockfiles that decide what is built, the workflow that runs it, and
  `ci.yml`, so the pull request that wires a language exercises the jobs it adds.
- One `lint-<lang>` and one `test-<lang>` per contributed workflow. Each kind is found on
  its own: `lang/api` contributes a lint workflow and no test one.
- `quality` and `security` wait for nothing. Each is one reusable workflow that reads
  `.github/quality.d/` or `.github/security.d/` and builds its own matrix, so the caller
  passes nothing about languages and has no filter for them to read.
- `gate` lists every other job in `needs:`, passes `toJSON(needs)` to `wc-gate.yml`, and
  carries `if: always()`. `gate` is the only required status check.
- A push trigger naming the default branch, so a branch with an open pull request runs
  once rather than twice. The value arrives from this layer's `default_branch` answer at
  render time, and a later `just ci-sync` reads it back out of the file it replaces.

Only `changes` and `gate` receive an input. Every lint and test workflow declares its
inputs optional with a default its own layer chose, so a caller passing one would
overwrite a recorded answer with a guess. A monorepo wanting `working-directory` per
member is a reason to own the caller, which the last paragraph covers.

`quality` carries a `commits` job that reads the whole pull request range. A
commit-message hook runs at `commit-msg`, which `--no-verify` defeats, and it sees only the
message being written; neither property survives a pull request, where a bypassed commit
stays bypassed and a branch holds several messages. It needs `fetch-depth: 0`, since the
range resolves from the merge base, and runs only on `pull_request`, because nothing else
defines a range.

That job also refuses a hand-made version tag in the range. release-please derives the next
version from tags, so a tag pushed by hand makes it compute the wrong one, and a tag is
pushed rather than committed, so no hook ever sees it.

`quality` and `security` do not need a path filter. Both already skip their
language-dependent jobs when no fragment supplies one, and their language-blind
jobs (the secret scan, the workflow audit, the prose and YAML checks) apply to any
change.

`security` needs `security-events: write` to upload SARIF. The jobs that upload
declare it, but a called workflow cannot hold more than its caller granted, so the
caller must grant it too. Without it the run fails at the upload rather than at the
scan.

Job-level path filtering goes in the caller, never in `on.push.paths`. A
workflow gated at the `on:` level does not run for an unrelated change, and a
required check that never runs leaves the pull request unmergeable. A job the filter
skipped reports `skipped`, which the gate counts as a pass. `always()` is what lets the
gate report at all when one of its needs was skipped or failed.

A language with no entry in the generator's filter table is refused by name. An unfiltered
job runs on every change, and a wrong filter skips a change it should have tested.

A reusable workflow the generator does not model is named in a comment in the file it
writes, the container build and the tofu plan among them. Calling either needs a role ARN,
or a push that happens only on the default branch, and the tree states neither.

`ci.yml` is rewritten whole, so it holds nothing hand-written. A repository that needs a
job the generator cannot derive deletes the marker line at the top to take the file over.
`ci-sync` then refuses the file, and a re-render leaves it alone.

## GitLab

Do not write a caller. `.gitlab-ci.yml` from the `host/gitlab` recipe ends with:

```yaml
include:
  - local: .gitlab/ci/*.yml
```

Each `lang/*` recipe drops `.gitlab/ci/<lang>.yml` and the glob resolves it.

Constraints:

- `*` matches one directory level. `**` recurses.
- Merge order across a glob is not deterministic, so no key may be set by more
  than one recipe.
- Recipes declare their own `stage:`, and `host/gitlab` declares the `stages:`
  list. A stage named by a recipe but absent from that list fails the pipeline.

GitLab jobs install their toolchain through mise rather than setup actions.

## Terraform and OpenTofu

The `iac/terraform` recipe contributes `lint-tofu` and `plan-tofu`. `plan-tofu`
runs per environment through a matrix.

Apply runs only on the default branch, as a manual job. Plan runs on every merge
request. This is what keeps two people from applying at once, which a local
wrapper cannot do.

## Docs

The `docs/deploy-*` recipes contribute their own workflow. GitHub Pages deployment
needs `pages: write` and `id-token: write`, which the gate workflow does not
carry.

Trigger on `docs/site/**` paths. Set `concurrency: group: docs-${{ github.ref }}`
so that two pushes to the same ref serialise and two different refs do not
cancel each other.
