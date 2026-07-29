# Quality

What runs against this repository, and what it enforces.

<!-- BEGIN GENERATED: quality-index -->
| Tool | Scope | Command |
|---|---|---|
| prek | staged files | `prek run` |
| ruff | the scripts | `uv run ruff check` |
| slop-lint | markdown under `docs/` and `rules/` | see below |
<!-- END GENERATED: quality-index -->

## Prose

Every markdown file passes the `review-docs` gate before it is merged. Internal
genre for `docs/` and `rules/`, consumer genre for `README.md`.

The available linters disagree on dash style: one rejects a unicode em dash and
the other rejects `--`. Write neither. Use a comma, a colon, or two sentences.

## Templates

A template is not linted as prose. Its rendered output is what matters, and
`just check` builds it.
