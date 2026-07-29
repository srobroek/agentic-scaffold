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

### GitLab CI

The Terraform CI templates were removed in 18.0. The replacement is the
`components/opentofu` component. Components resolve from the instance they run
on, so a self-managed instance needs the component mirrored.

`include: local:` accepts globs. `*` matches one directory level and `**`
recurses. Merge order across a glob is not deterministic.

Plan artifacts published for the merge-request widget are readable by anyone
with the Guest role and are not encrypted. Set `public: false`.
