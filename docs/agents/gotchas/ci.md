# Gotchas: CI

### GitHub Actions

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
| a matrix job fails with no entries | a matrix built from a discovered list errors on an empty array rather than skipping. Gate the job on a count output |
| a single pull-request template never loads | one file inside `.github/PULL_REQUEST_TEMPLATE/` applies only through a query parameter. Use `.github/PULL_REQUEST_TEMPLATE.md` |
| `lizard -l <name>` reports nothing | an unknown language name exits 0 having analysed nothing |

A bare `on` key parses as boolean `true` under YAML 1.1, so a test reading a
workflow with `yaml.safe_load` finds `True` rather than `"on"`. This costs nothing
in CI, where GitHub does its own parsing, and breaks any check written against the
rendered file.

`lizard` accepts a language it does not know without complaint: `-l notalanguage`
prints no warning and exits 0, so a typo silently removes that language's
complexity gate. `-w` does exit 1 on a real threshold breach, so the gate works
once the name is right. `tests/test_host_layers.py` checks each fragment's name
against lizard's own list.

### GitLab CI

| Failure | Cause |
|---|---|
| the whole pipeline fails, not one job | a job names a stage absent from the top-level `stages:` list. GitLab rejects the pipeline rather than skipping the job |
| `mapping values are not allowed here` | an inline `-d "{extends: relaxed, ...}"` parses as a YAML flow mapping, not a string. Put the command in a block scalar |
| two pipelines run for one push | a branch with an open merge request matches both the branch rule and the merge-request rule. Gate on `$CI_PIPELINE_SOURCE` |

A job naming an undeclared stage takes down every other job with it, which makes the
`stages:` list the same class of hazard as `default_install_hook_types`: a glob
include means a layer adopted later contributes a stage nothing declared.
`gen_gitlab_stages.py` generates the list and refuses an unrecognised stage.

A key opening with a dot is a template rather than a job, and GitLab never runs it, so
a stage named there does not need declaring. Every language fragment carries one, as
`.<lang>-setup`.

The Terraform CI templates were removed in 18.0. The replacement is the
`components/opentofu` component. Components resolve from the instance they run
on, so a self-managed instance needs the component mirrored.

`include: local:` accepts globs. `*` matches one directory level and `**`
recurses. Merge order across a glob is not deterministic.

Plan artifacts published for the merge-request widget are readable by anyone
with the Guest role and are not encrypted. Set `public: false`.
