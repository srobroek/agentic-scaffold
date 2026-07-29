# Steering index

One directory per concern. Read the index, then the leaf for the language being
touched.

| Concern | Directory |
|---|---|
| What each quality tool enforces | `quality/` |
| Job graph and merge gates | `ci/` |
| Version source and publish targets | `release/` |
| Test layout and invocation | `testing/` |
| Where docs live and how they deploy | `docs/` |
| Required environment variables | `env/` |
| Failures found by running a tool | `gotchas/` |
| Error handling, naming, ownership | `conventions.md` |

<!-- BEGIN GENERATED: index -->
<!-- END GENERATED: index -->

## Using the recipes

Add a package with `just add <name> <lang>`. Creating a member directory by hand
skips the workspace-manifest registration and the fragment wiring.

Run `just docs:agents` after changing any configuration a generated block reads.
CI fails on drift.

Run `just check` before claiming a change works. A tree that renders is not a
project that builds.
