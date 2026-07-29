# CI composition

Each layer contributes reusable workflows. The caller that wires them is written
per repository, because it depends on which layers rendered.

## GitHub

Write `.github/workflows/ci.yml` calling the reusable workflows that the
rendered layers provide.

Job graph:

```
changes ──> lint-<lang>   ─┐
       ├──> test-<lang>   ─┤
       ├──> quality       ─┼──> gate
       └──> security      ─┘
```

Rules:

- `changes` runs first and outputs per-language path filters. Every downstream
  job takes its filter as a condition.
- Lint, test, quality, and security run in parallel. None depends on another.
- `gate` lists every other job in `needs:` and passes `toJSON(needs)` to
  `wc-gate.yml`. `gate` is the only required status check.
- One `lint-<lang>` and one `test-<lang>` pair per rendered `lang/*` layer.
- `quality` and `security` always run, and take no language input. Each is one
  reusable workflow that reads `.github/quality.d/` or `.github/security.d/` and
  builds its own matrix, so the caller passes nothing about languages.

`quality` and `security` need no path filter. Both already skip their
language-dependent jobs when no fragment supplies one, and their language-blind
jobs (the secret scan, the workflow audit, the prose and YAML checks) apply to any
change.

`security` needs `security-events: write` to upload SARIF. The jobs that upload
declare it, but a called workflow cannot hold more than its caller granted, so the
caller must grant it too. Without it the run fails at the upload rather than at the
scan.

Job-level path filtering goes in the caller, never in `on.push.paths`. A
workflow gated at the `on:` level does not run for an unrelated change, and a
required check that never runs leaves the pull request unmergeable.

## GitLab

Write no caller. `.gitlab-ci.yml` from the `host/gitlab` layer ends with:

```yaml
include:
  - local: .gitlab/ci/*.yml
```

Each `lang/*` layer drops `.gitlab/ci/<lang>.yml` and the glob resolves it.

Constraints:

- `*` matches one directory level. `**` recurses.
- Merge order across a glob is not deterministic, so no key may be set by more
  than one layer.
- Layers declare their own `stage:`, and `host/gitlab` declares the `stages:`
  list. A stage named by a layer but absent from that list fails the pipeline.

GitLab jobs install their toolchain through mise rather than setup actions.

## Terraform and OpenTofu

The `iac/terraform` layer contributes `lint-tofu` and `plan-tofu`. `plan-tofu`
runs per environment through a matrix.

Apply runs only on the default branch, as a manual job. Plan runs on every merge
request. This is what keeps two people from applying at once, which a local
wrapper cannot do.

## Docs

The `docs/deploy` layer contributes its own workflow. GitHub Pages deployment
needs `pages: write` and `id-token: write`, which the gate workflow does not
carry.

Trigger on `docs/site/**` paths. Set `concurrency: group: docs-${{ github.ref }}`
so that two pushes to the same ref serialise and two different refs do not
cancel each other.
