# Environment

<!-- BEGIN GENERATED: env -->
Rendering a layer and running the scripts do not read the environment.
<!-- END GENERATED: env -->

## Read by a rendered project

Names only. A value never enters this file.

| Name | Needed by | Without it |
|---|---|---|
| `GH_TOKEN` | `gh repo create` during scaffolding | remote creation fails; rendering still works |
| `DOCS_DEPLOY_KEY` | the split docs deploy topology | the code repo cannot push to its sibling |
