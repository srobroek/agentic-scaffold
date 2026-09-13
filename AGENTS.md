# project-scaffold

Composable copier recipes plus an agent skill that scaffolds repositories.

## Read for

- The model and fixed decisions: `docs/architecture.md`
- Derived choices: `skills/project-scaffold/references/choices.md`
- CI caller composition: `docs/architecture.md#ci-composition`
- Rendered `docs/agents/` context: `docs/steering.md`
- Recipes and variables: `docs/INDEX.md`, `docs/recipes.md`, and `profiles/*.yml`

## Rules

Never name a recipe from memory; use `docs/INDEX.md`. Never add a question that the choices reference marks fixed or derived. Never hand-edit rendered output: fix the answer or recipe and re-render. A tree that renders is not a project that builds; use `just profiles-build` when validating profiles.

Tracked in Beads with prefix `psc`; `bd ready` lists claimable work.
