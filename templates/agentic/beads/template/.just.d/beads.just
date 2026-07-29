# Beads recipes, imported by the root justfile.

# Claimable work, with no active blockers
[group('beads')]
bd-ready:
    bd ready

# What is claimed right now
[group('beads')]
bd-active:
    bd list --status in_progress

# The database travels over refs/dolt/data on the git remote, separate from
# refs/heads/* where the code lives. .beads/issues.jsonl is a passive export rather
# than the wire protocol, so this is what makes issues survive a reclone.
#
# The comment directly above a recipe becomes its `--list` description, so the
# rationale goes here and the description stays on the last line.

# Push the Dolt database to the git remote
[group('beads')]
bd-push:
    bd dolt push

# Pull the Dolt database from the git remote
[group('beads')]
bd-pull:
    bd dolt pull

# Check the database for corruption and fix what is fixable
[group('beads')]
bd-doctor:
    bd doctor
