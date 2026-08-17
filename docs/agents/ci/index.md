# CI

<!-- BEGIN GENERATED: ci -->
No workflows exist yet. `psc-196` adds the check target CI runs.
<!-- END GENERATED: ci -->

## Shape to build

`psc-196` builds one quality job running `prek run --all-files`, the prose gate, and
`just check`. The steering drift check (`just steering-check`) runs inside
that job rather than a workflow of its own.

See `../../rules/ci-composition.md` for what a scaffolded repository gets, which
is a different thing from what this repository runs.
