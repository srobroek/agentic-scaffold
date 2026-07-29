# Steering index

Working context for this repository. One directory per concern; read the index,
then the leaf.

| Concern | Directory |
|---|---|
| What each quality tool enforces | `quality/` |
| Job graph and merge gates | `ci/` |
| Version source and publish targets | `release/` |
| Test layout and invocation | `testing/` |
| Where docs live and how they deploy | `docs/` |
| Required environment variables | `env/` |
| Error handling, naming, ownership | `../conventions.md` |

Design decisions live outside this directory: `../architecture.md` for the model
and every fixed choice, `../steering.md` for what a scaffolded repository gets,
`../../rules/` for what the agent derives.

<!-- BEGIN GENERATED: index -->
## Commands

| Command | Does |
|---|---|
| `just new <name>` | interview, then render a new project |
| `just add <name> <lang>` | add a package to a monorepo |
| `just preview <layer> <dest>` | render one layer, writing nothing |
| `just index` | regenerate `docs/INDEX.md` from `templates/` |
| `just check` | render every profile and run its build |
| `just docs:agents` | regenerate the generated blocks here |

## Toolchain

Pinned in `mise.toml`. Python for the scripts, `copier` >= 9.16, `just`,
`gitnr`, `prek`.

## Layout

Single package. `templates/` holds the layers, `profiles/` the layer sets,
`rules/` the derivation tables, `scripts/` the renderer and the index generator.

## Structural tool

Neither gitnexus nor repomix is indexed here. Use `rg` and `fd`.
<!-- END GENERATED: index -->
