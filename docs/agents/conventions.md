# Conventions

Rules a linter does not catch.

## Layers

A layer owns its files and nothing else, so no path is written by more than one layer.

A layer that contributes to a shared configuration file writes a fragment and
lets a native mechanism combine them. `docs/architecture.md` lists the mechanism
per target. Never add a merge script.

Inclusion is decided by which layer renders, not by a conditional in a filename.
A conditional filename is the mechanism that cost an hour to a quote character.

A layer that needs a value another layer owns takes it from the answers file
through `_external_data`, which resolves relative to the destination.

## Questions

A question exists only for something Sjors varies between projects.
`rules/choices.md` is the record of what that is. Anything else is fixed in the
layer or derived by the agent.

Adding a question is a change to `rules/choices.md` first, and to a `copier.yml`
second.

## Scripts

`scripts/` holds two files. `render.py` wraps copier and `index.py` walks
`templates/`. A third script is a sign that something belongs in a layer, a
`just` recipe, or the skill.

Report what happened, not what should have. Name every file written, every task
that ran, and every command that failed with its output.

## Documents

`docs/architecture.md` records decisions and stays current with the code.

A rejected alternative belongs in `docs/architecture.md` under Excluded, with the
measurement that rejected it. It does not belong in prose next to the thing that
won.

## Verification

Claim nothing that has not been run. A version number, a rule count, or a
timing goes in a document only after the command that produced it has been run
on this machine.
