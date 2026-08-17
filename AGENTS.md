# project-scaffold

Layered copier templates plus an agent skill that scaffolds a repository.

## Read for

| Question | File |
|---|---|
| The model, and every fixed decision | `docs/architecture.md` |
| What to derive instead of asking | `rules/choices.md` |
| Writing the CI caller | `rules/ci-composition.md` |
| What `docs/agents/` holds in a rendered repo | `docs/steering.md` |
| Working context for this repo | `docs/agents/index.md` |
| Which layers exist, and their variables | `docs/INDEX.md` |
| Layer set per profile | `profiles/*.md` |

## Rules

Never name a layer from memory. `docs/INDEX.md` is the list.

Never add a question for something `rules/choices.md` marks fixed or derived.

Never hand-edit rendered output to fix a template. Fix the answer and re-render,
or change the template.

A tree that renders is not a project that builds. `just check` renders every
profile and runs its own build.


## Work

Tracked in beads, prefix `psc`. `bd ready` lists claimable work.
