# project-scaffold

Scaffolds a repository from composable copier recipes, driven by an agent skill.
Renders language tooling, CI, hooks, release automation, docs, and agent steering
into one destination.

## Requirements

| Tool | Purpose |
|---|---|
| `uv` | runs `scripts/scaffold.py` and resolves its dependencies |
| `copier` >= 9.16 | renders each recipe; `uv sync` installs it |
| `git` | the CLI initialises the destination and commits once per recipe |
| `just` | the entry points in this repository's justfile |

A recipe declares the binaries it needs in its own `copier.yml`, and `scaffold
render` names the missing one instead of failing inside copier: `gh` for
`base/license` and `base/gitignore`, `bd` for `agentic/beads`, `node` for
`iac/cdk`.

`base/repo` refuses a destination holding uncommitted changes. copier
overwrites, so there would be no diff left to review.

Language scaffolds call `cargo`, `uv`, `go`, or `bun`. The `ts-app` and `cdk`
profiles call `create-better-t-stack` and `projen` through `bunx`.

## Usage

The skill lives at `skills/project-scaffold/SKILL.md`. With a harness pointed at
`skills/`, ask for a project:

```
set up a new rust library called skymath
```

The skill asks six questions, derives the rest, and renders. The same work
through `just`:

```sh
just plan --profile rust-lib --dest /tmp/skymath --demo   # the file map, writing nothing
just render-profile rust-lib /tmp/skymath                 # render, then run the profile's build
just render lang/rust /tmp/skymath                        # one recipe
just preview lang/rust /tmp/skymath                       # one recipe, writing nothing
just update lang/rust --dest /tmp/skymath                 # re-render at HEAD, merge local drift
just profiles                                             # validate every profile against recipes/
```

`scripts/scaffold.py` is the whole CLI, and it reports itself as `scaffold`. It
never prompts: `--data key=value` and `--data-file <yaml>` carry the answers, and
a missing required answer is a `check-answers` finding.

| Command | Does |
|---|---|
| `list` | every recipe and profile with its summary |
| `check [profile...]` | validates profiles against `recipes/`; exit 1 on a problem |
| `plan` | the file map: one row per path, its owners, and its class; writes nothing |
| `render` | renders into a destination, gated on the plan |
| `check-answers` | every missing required answer at once; exit 1 if any |
| `update <recipe>...` | re-renders at HEAD and merges local drift |

## Recipes

A recipe is one directory holding a `copier.yml` and a `template/`. Adding one is
dropping the directory into `recipes/<group>/<name>/` and naming it in a profile.
The `_scaffold` block in `copier.yml` carries the six keys the CLI reads:
`summary`, `after` for render order, `requires_bin`, `precheck`, `merge` globs,
and `exclusive_group`.

Recipes come from four places through one argument:

| Source | Example |
|---|---|
| an id under `recipes/` | `lang/rust` |
| a local directory | `./path/to/recipe` |
| a git repository | `https://host/user/repo.git` |
| any remote copier template | `gh:user/template` |

| Group | Recipes |
|---|---|
| `base` | `license`, `repo`, `gitignore` |
| `lang` | `python`, `ts`, `go`, `rust`, `api` |
| `host` | `github`, `gitlab` |
| `workspace` | `monorepo`, `just`, `moon`, `devcontainer`, `worktrunk` |
| `quality` | `hooks` |
| `release` | `release-please`, `cocogitto`, `goreleaser`, `dep-updates` |
| `agentic` | `apm`, `package`, `marketplace`, `beads`, `index`, `speckit` |
| `iac` | `terraform`, `cdk` |
| `container` | `image` |
| `docs` | `site`, `agents`, `adr`, `api-refs`, `deploy-sibling`, `deploy-split` |

`docs/INDEX.md` lists all 36 recipes and their variables. Regenerate it with
`just index`.

## The plan decides whether a render runs

`plan` renders each recipe into a scratch directory, so a conditional or
jinja-templated filename is resolved rather than guessed. Every path gets a
class:

| Class | Meaning |
|---|---|
| `create` | one owner, and the destination does not hold the path |
| `overwrite` | one owner, and the destination holds a different file |
| `skip` | a later owner declares the path under `_skip_if_exists`; the first owner wins |
| `fragment` | under a fold directory, where an aggregator merges it |
| `answers` | a `.copier-answers.<name>.yml` the CLI owns |
| `conflict` | two owners and no declared resolution |

Two recipes owning one path is refused. `plan` exits 5 naming both owners, and
`render` runs the same plan and stops before writing:

```
conflicts:
  README.md: owned by base/repo and /tmp/dup-recipe

refusing: two recipes own the same file. Drop one, or declare
`_skip_if_exists` in the later recipe so the first owner wins.
```

Fragments are the exception. `.gitignore.d/`, `.just.d/`, `.mise/conf.d/`,
`.pre-commit.d/`, `.github/quality.d/`, `.github/security.d/`, and `.gitlab/ci/`
hold one file per contributing recipe, and an aggregator folds each directory
into the real config file. A recipe adds its own merged paths with
`_scaffold.merge` globs. Two recipes writing the *same* fragment path still
conflict.

## Update a rendered repository

`copier update` cannot run here: a recipe rendered from a local path records no
`_commit`, which is the ref `copier update` replays from. `render` records the
scaffold repository's HEAD as `_ref` in each answers file instead. `update` reads
that back, renders the recipe twice, and merges the difference over local edits
with `git merge-file`:

```sh
just update lang/rust --dest ~/code/skymath
```

Hand edits survive where they do not overlap a template change. A true overlap
gets conflict markers and exit 5. `update` prints which aggregator fold to re-run
when it touched a fragment directory.

## Profiles

| Profile | Produces |
|---|---|
| `agentic-repo` | steering, hooks, CI, release automation, no language recipe |
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

## Configuration

Answers to the six interview questions:

| Question | Type | Default | Effect |
|---|---|---|---|
| project name and purpose | string | none | package name, description, framework inference |
| language | choice | none | which `lang/*` recipe renders |
| layout | `single`, `monorepo`, `polyrepo` | derived | workspace manifest and member paths |
| license | `apache-2.0`, `mpl-2.0`, `agpl-3.0-only` | derived from project kind | `LICENSE`, and crate metadata for rust |
| create remote | boolean | `false` | runs `gh repo create` or `glab repo create` |
| visibility | `private`, `public` | `private` | read back before creating a public repo |

`rules/choices.md` holds the derivation rules. Fixed preferences live in the
recipes: `uv`, `bun`, `prek`, `biome`, `oxlint`, `release-please`, `renovate`,
SHA-pinned actions.

## Removed

`packages/`, the root APM manifest, the marketplace catalogs, and the four
per-package plugin manifests are deleted. Nothing here registers as an apm
marketplace.

| Deleted | Replaced by |
|---|---|
| two APM packages under `packages/` | `skills/<name>/SKILL.md`, plain markdown |
| four per-package plugin manifests | one root manifest whose `skills` key is `./skills` |
| the claude and codex marketplace catalogs | nothing: a harness points at `skills/` |
| `copier update` | `scaffold update`, on the `_ref` each render records |

Ten files carried the version, and three values were live at once: 0.2.2, 0.2.0,
and 0.1.0. `release-please` rewrote the manifest on each release, and its YAML
writer dropped every comment in it. A script then ran to restore them.

## Docs

| Document | Contents |
|---|---|
| `docs/architecture.md` | the model, every fixed decision, and what is excluded |
| `docs/recipes.md` | what each recipe writes, and why it writes it that way |
| `docs/INDEX.md` | generated recipe and variable listing |
| `rules/choices.md` | what the agent derives instead of asking |
| `rules/ci-composition.md` | how the GitHub caller workflow is written |
| `profiles/README.md` | the profile format, and the shape each one covers |

## License

Apache-2.0
