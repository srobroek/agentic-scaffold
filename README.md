# project-scaffold

Scaffolds a new repository from layered copier templates, driven by an agent
skill. Renders language tooling, CI, hooks, release automation, docs, and agent
steering into one destination.

## Requirements

| Tool | Purpose |
|---|---|
| `copier` >= 9.16 | renders the layers |
| `just` | task entry points |
| `gitnr` | concatenates `.gitignore` sources |
| `prek` | git hooks |
| `mise` | toolchain pinning |

Language scaffolds call `cargo`, `uv`, `go`, or `bun`. The `ts-app` and `cdk`
profiles call `create-better-t-stack` and `projen` through `bunx`.

## Usage

Install the skill, then ask for a project:

```
set up a new rust library called skymath
```

The skill asks six questions, derives the rest, and renders. To drive it
directly:

```sh
just new skymath              # interview, then render
just add contracts rust       # add a package to a monorepo
just preview lang/rust /tmp/t # render one layer, writing nothing
just check                    # render every profile and run its build
```

## Profiles

| Profile | Produces |
|---|---|
| `agentic-repo` | steering, hooks, CI, release automation, no language layer |
| `rust-lib`, `rust-app` | cargo package or workspace |
| `rust-gui` | `rust-app` plus a Tauri shell at `apps/<name>` |
| `python-lib`, `python-app` | uv project |
| `go-lib`, `go-app` | go module |
| `ts-lib` | bun package |
| `ts-app` | better-t-stack monorepo |
| `ts-tui` | OpenTUI terminal app |
| `cdk` | projen AWS CDK app |
| `terraform` | OpenTofu root modules, one directory per environment |

Each profile takes `single` or `monorepo`.

## Layers

`templates/<group>/<name>/` holds one copier template per tool or concern.

| Group | Layers |
|---|---|
| `base` | README, editorconfig, gitignore |
| `lang` | python, ts, go, rust |
| `host` | github, gitlab |
| `workspace` | moon, taskfile, devcontainer |
| `quality` | hooks, secrets |
| `release` | release-please, cocogitto |
| `agentic` | apm, beads, steering |
| `iac` | terraform |
| `docs` | site, agents, api-refs, deploy |
| `license` | apache-2.0, mpl-2.0, agpl-3.0-only |

`docs/INDEX.md` lists every layer and its variables. Regenerate it with
`just index`.

## Configuration

Answers to the six interview questions:

| Question | Type | Default | Effect |
|---|---|---|---|
| project name and purpose | string | none | package name, description, framework inference |
| language | choice | none | which `lang/*` layer renders |
| layout | `single`, `monorepo`, `polyrepo` | derived | workspace manifest and member paths |
| license | `apache-2.0`, `mpl-2.0`, `agpl-3.0-only` | derived from project kind | `LICENSE`, and crate metadata for rust |
| create remote | boolean | `false` | runs `gh repo create` or `glab repo create` |
| visibility | `private`, `public` | `private` | read back before creating a public repo |

`rules/choices.md` holds the derivation rules. Fixed preferences live in the
layers: `uv`, `bun`, `prek`, `biome`, `oxlint`, `release-please`, `renovate`,
SHA-pinned actions.

## Docs

| Document | Contents |
|---|---|
| `docs/architecture.md` | the model, every fixed decision, and what is excluded |
| `docs/INDEX.md` | generated layer and variable listing |
| `rules/choices.md` | what the agent derives instead of asking |
| `rules/ci-composition.md` | how the GitHub caller workflow is written |
| `profiles/*.md` | layer set and destinations per profile |

## License

Apache-2.0
