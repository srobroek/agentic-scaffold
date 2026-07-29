# Environment

<!-- BEGIN GENERATED: env -->
No variable is required to render a layer or run the scripts.
<!-- END GENERATED: env -->

## Needed by what a rendered project does

Names only. A value never enters this file.

| Name | Needed by | Without it |
|---|---|---|
| `GH_TOKEN` | `gh repo create` during scaffolding | remote creation fails; rendering still works |
| `DOCS_DEPLOY_KEY` | the split docs deploy topology | the code repo cannot push to its sibling |
