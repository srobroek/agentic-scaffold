---
name: project-scaffold-update
description: Add a layer to an existing repository, apply template changes that landed after it was scaffolded, or retrofit the scaffold onto a repository that predates this tool. Use when asked to adopt, retrofit, backport, resync, or catch up a repo to the scaffold.
---

# Project scaffold update

Change a repository that already exists. Which job it is decides everything after:

| Situation | Job |
|---|---|
| repo was scaffolded, wants a layer it does not have | **Adopt a layer** |
| repo was scaffolded, a template changed since | **Apply template changes** |
| repo predates this tool, has no answers files | **Retrofit** |

Use `project-scaffold` instead for a repository that does not exist yet.

## What is not available

`copier update` does not work here. A layer is rendered from a local path, so no `_commit`
is recorded in the answers file, and copier says so outright: `Cannot update because cannot
obtain old template references`. There is no three-way merge and no upstream diff.

What replaces it: re-render the layer with its own recorded answers, then read the git diff.
The repository being committed first is what makes this safe, and it is the only thing that
does.

## Adopt a layer

```bash
just preview <group>/<layer> <dest>   # what it would write, writing nothing
just render  <group>/<layer> <dest>   # write it
```

Preview first, always. `--pretend` under the hood, verified to leave the tree untouched.

Read `docs/layers.md` for the layer's row before rendering. What decides whether one render
is enough:

- **Its `after` list.** A layer declaring `after: lang/*` has to render after the language
  layers, and rendering it early produces a file that reads a directory that was empty at the
  time.
- **What it requires.** `scripts/profiles.py` holds the `REQUIRES` map. `docs/api-refs`
  without `docs/deploy-split` writes a generator whose output nothing ever publishes.

### Then resync the aggregators

A new layer drops fragments into `.just.d/`, `.gitignore.d/`, `.pre-commit.d/`, and
`.mise/conf.d/`. The generated files that fold them in are stale the moment the render
finishes. Measured on a real tree: rendering `lang/rust` into a repo with `workspace/just`
left the justfile import block reading `# No fragments rendered yet.`, and `just just-check`
caught it.

| Fragment directory | Resync with |
|---|---|
| `.just.d/` | `just just-sync` |
| `.pre-commit.d/` | `just hooks-merge` |
| `docs/agents/` | `just steering` |
| `.gitignore.d/` | re-render `base/gitignore` |

`.gitignore` is the odd one. Its folding runs from a copier `_tasks` script inside the
template rather than a recipe in the repository, so there is nothing to run in-tree and the
aggregator layer has to render again.

Then `just check`, which runs every `*-check` recipe and is what catches an aggregator nobody
resynced.

## Apply template changes

Re-render the layer with the answers file it wrote:

```bash
just render <group>/<layer> <dest> .copier-answers.<layer>.yml
```

The answers file records what the layer was asked, so re-rendering reproduces the same
choices against the new template. Do it one layer at a time, and commit between layers: a
single commit spanning six re-rendered layers is unreviewable, and the diff is the only
review this has.

**Local edits to a generated file are lost.** Verified: an `indent_size = 8` override
appended to `.editorconfig` was overwritten with no warning and no prompt, because `render`
passes `--overwrite`. Only a path in the layer's `_skip_if_exists` survives, and `README.md`
under `base/repo` is one that does.

So before re-rendering, run `git log --oneline -- <path>` on what the layer owns: a commit
that is not a render is a hand edit. Move it somewhere the layer does not own. Every
aggregated directory exists for this, and `just just-add` writes a fragment for a
project-specific recipe rather than editing the generated block.

## Retrofit

A repository with no `.copier-answers.*.yml` was never scaffolded. It has its own history,
its own conventions, and files at paths a layer wants.

Report before changing anything. Preview every candidate layer and show the combined file
list, separated into files that do not exist and files that would be overwritten. The second
list is the whole decision, and rendering before showing it destroys the thing the user
needed to see.

Then render in the order a profile would, one layer at a time, committing between them.
Read the closest profile in `profiles/*.yml` for that order rather than deriving it: the
ordering bugs it encodes were found by rendering, not by reading.

Retrofit `base/repo` first or not at all. It carries the precheck that refuses a dirty tree,
which is the guard every later layer depends on.

## Rules

- Commit before rendering. `render` overwrites and leaves no diff to review otherwise.
- Preview before rendering into a repository that already has files.
- One layer per commit. A combined diff hides which template did what.
- Pass the layer's own answers file when re-rendering, or copier re-derives defaults and
  silently changes answers nobody revisited.
- Resync the aggregators after adopting a layer, then run `just check`.
- Never retrofit without showing the overwrite list first.
