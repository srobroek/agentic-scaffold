---
name: project-scaffold-update
description: Add a recipe to an existing repository, apply recipe changes that landed after it was scaffolded, or retrofit the scaffold onto a repository that predates this tool. Use when asked to adopt, retrofit, backport, resync, or catch up a repo to the scaffold.
---

# Project scaffold update

Change a repository that already exists. Which job it is decides everything after:

| Situation | Job |
|---|---|
| scaffolded, wants a recipe it does not have | **Adopt** |
| scaffolded, a recipe changed since | **Apply changes** |
| predates this tool, no `.copier-answers.*.yml` | **Retrofit** |

`project-scaffold` owns a repository that does not exist yet.

Commit the destination first, in every job. copier overwrites, and the git diff is the only
review this has.

## Adopt

```bash
uv run scripts/scaffold.py plan   <group>/<recipe> --dest <dest>   # writes nothing
uv run scripts/scaffold.py render <group>/<recipe> --dest <dest>
```

Read the plan before rendering: the `overwrite` rows are the decision. `just preview` is the
same render under `--pretend`.

What decides whether one render is enough:

- **`_scaffold.after` in the recipe's `copier.yml`.** A recipe declaring `after: lang/*`
  renders after the language recipes. Early, it reads a directory that was empty at the time.
- **The `REQUIRES` map in `scripts/scaffold.py`.** `docs/api-refs` without
  `docs/deploy-split` writes a generator whose output nothing ever publishes.
- **List answers derive from the tree.** `docs/api-refs` takes `api_ref_languages`
  and `container/image` takes `container_language`: read the same markers the
  gitignore fold reads -- rust-toolchain.toml, pyproject.toml, .golangci.yml,
  biome.json -- and pass the value with `--data`. Narrow it only when the
  repository documents or ships fewer languages than it carries.

### Then re-fold the aggregators

A new recipe drops fragments into `.just.d/`, `.gitignore.d/`, `.pre-commit.d/`, and
`.mise/conf.d/`. The generated files that fold them in are stale the moment the render
finishes. Measured: rendering `lang/rust` into a repository carrying `workspace/just` left
the justfile import block reading `# No fragments rendered yet.`, and `just just-check`
caught it.

| Fragment directory | Re-fold with |
|---|---|
| `.just.d/` | `just just-sync` |
| `.pre-commit.d/` | `just hooks-merge` |
| `docs/agents/` | `just steering` |
| `.gitignore.d/` | re-render `base/gitignore` |

`.gitignore` is the odd one. Its fold runs from a copier task inside the recipe rather than
a recipe in the repository, so nothing in-tree runs it and the aggregator renders again.
`mise` reads its directory and needs no fold at all.

Then `just check` in the destination, which runs every `*-check` recipe and is what catches
an aggregator nobody re-folded.

## Apply changes

```bash
uv run scripts/scaffold.py update <group>/<recipe> --dest <dest>
```

It renders the recipe twice, at the `_ref` recorded in `.copier-answers.<recipe>.yml` and
again at HEAD, then 3-way merges the difference over the working tree with
`git merge-file`. A local edit survives where it does not overlap a recipe change. The
answers file comes from HEAD verbatim, because merging YAML mangles it.

| Outcome | Meaning |
|---|---|
| `merged`, `created` | the recipe change landed over local content |
| `CONFLICT` and exit 5 | that file carries conflict markers; a human resolves them |

Never commit over a conflict, and never re-run `update` to clear one: the second run replays
the same ref and merges into the markers. One recipe per commit, so the diff stays readable.

`update` also prints `note: <directory> changed; re-run the <recipe> fold` for every
fragment directory it touched. Do those before `just check`.

An answers file with no `_ref` predates ref recording. Render instead, passing that file as
`--data-file`, and read the diff.

### `--refresh`: re-decide one thing

When a decision changes rather than a recipe, re-grill only the named decisions: that key,
and whatever its answer narrows. Then carry the new value into the update:

```bash
uv run scripts/scaffold.py update base/license --dest <dest> --data license=apache-2.0
```

Leave every other recorded answer alone. Re-running the whole interview re-decides choices
nobody revisited.

## Retrofit

A repository with no `.copier-answers.*.yml` was never scaffolded. It has its own history, its
own conventions, and files where a recipe wants to write. No `_ref` exists for `update` to
replay, so retrofit is `plan` then `render`.

Report before changing anything. Plan every candidate recipe and show the combined list
split into `create` and `overwrite`. The second list is the whole decision, and rendering
before showing it destroys the thing the user needed to see.

Then render in the order a profile would, one recipe per commit. Read the closest
`profiles/*.yml` for that order rather than deriving it: the ordering bugs it encodes were
found by rendering, not by reading.

Retrofit `base/repo` first or not at all. It carries the precheck that refuses a dirty tree,
which every later recipe depends on.

## Rules

- Commit the destination before rendering.
- Plan before rendering into a repository that already has files.
- One recipe per commit.
- Reach for `update` before `render`: `update` merges, `render` overwrites.
- A hand edit to a path a recipe owns is lost on re-render unless the path is under that
  recipe's `_skip_if_exists`, as `README.md` is under `base/repo`. `git log --oneline --
  <path>` shows whether the last commit there was a render or a person. Move such an edit
  into a fragment directory, or into a file of its own through `just just-add`.
- Re-fold the aggregators after adopting a recipe, then run `just check`.
- Show the overwrite list before a retrofit writes anything.
