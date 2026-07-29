# {{PROJECT}}

## Read for

| Question | File |
|---|---|
| Commands, toolchain versions, layout | `docs/agents/index.md` |
| Error handling, logging, ownership boundaries | `docs/agents/conventions.md` |
| What each quality tool enforces | `docs/agents/quality/` |
| Job graph, merge gates, local reproduction | `docs/agents/ci/` |
| Version source, tag format, publish targets | `docs/agents/release/index.md` |
| Test layout and how to run one test | `docs/agents/testing/index.md` |
| Where docs live and how they deploy | `docs/agents/docs/index.md` |
| Required environment variables | `docs/agents/env/index.md` |
| A failure that looks like a mystery | `docs/agents/gotchas/` |

Each directory under `docs/agents/` has an `index.md`. Read that first, then the
leaf for the language being touched.

## Rules

Content between `<!-- BEGIN GENERATED: ... -->` markers is derived from
configuration on disk. Change the configuration, then run `just docs:agents`.
Text outside the markers is hand-written and survives regeneration.

Record a failure found by running something in `docs/agents/gotchas/`, with the
cause.

`docs/agents/env/index.md` names variables and never holds values.
