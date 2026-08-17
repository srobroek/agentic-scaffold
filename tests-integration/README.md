# Integration cases

What the profiles and the unit tests together do not cover: a **combination** of layers,
rendered in one tree, then built.

`profiles/*.yml` covers one shape each, and `just profiles-build` proves each renders and
builds. `tests/` covers one layer each, asserting the files it writes. Neither covers what
happens when two layers meet: a monorepo with real members, both hosts in one repository, a
layer adopted after the aggregator that folds it in.

Every defect found while building these layers rendered cleanly first and failed only when a
real tool read the result. These cases exist to put a real tool in front of a combination.

## Running

```bash
just integration              # every case
just integration <name>       # one, by file stem
just integration --list       # what exists
```

Not part of `just check`. A case renders a whole tree and runs its build, which takes minutes
where the unit suite takes seconds. `just check` stays fast enough to run on every edit; this
runs when layer composition changes.

## A case

```yaml
name: monorepo-rust-two-members
summary: One sentence on the interaction under test.

# Why this combination is not already covered. A case that duplicates a profile or a unit
# test is a case that costs minutes and proves nothing.
gap: |
  profiles/rust-lib renders one crate. Nothing renders a workspace with two members whose
  manifests declare a dependency and then asks moon to order the build.

layers: [base/repo, lang/rust]        # in render order
answers: {license: mpl-2.0}           # threaded to every layer

# Run after the layers, before the build. Each is a shell command in the destination.
setup:
  - python3 scripts/add_member.py core rust

build:
  - just just-check

# Optional. Each is a python expression over `tree`, a pathlib.Path at the destination root.
expect:
  - (tree / "crates/core/Cargo.toml").is_file()
```

`layers` renders in the order given, and the order is the point: a case that renders a
contributor after its aggregator should say so in `gap` and assert the staleness, rather than
quietly passing because the aggregator happened to run twice.

## What a case cannot do

The generator does not run, for the same reason `render_profile.py` skips it: `cargo new`,
`uv init`, and `create-better-t-stack` reach the network or need a toolchain the machine may
not carry. A `build` command needing generator output fails for a missing manifest rather than
for anything a layer got wrong. Use `setup` to write the minimum by hand when a build needs it.

A `build` command whose binary is absent is skipped, not failed, and the run says so. A case
that silently checked less than it appears to is worse than one that says it was skipped.
