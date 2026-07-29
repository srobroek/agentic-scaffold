# Beads recipes, imported by the root justfile.

# --- what to work on -------------------------------------------------------

# Claimable work, with no active blockers
[group('beads')]
bd-ready:
    bd ready

# What is claimed right now
[group('beads')]
bd-active:
    bd list --status in_progress

# Everything still open, blocked included
[group('beads')]
bd-open:
    bd list --status open

# One issue in full, with its dependencies and comments
[group('beads')]
bd-show id:
    bd show {{ id }}

# The context an agent gets at session start
[group('beads')]
bd-prime:
    bd prime

# --- sync ------------------------------------------------------------------
#
# The database travels over refs/dolt/data on the git remote, separate from
# refs/heads/* where the code lives. `.beads/issues.jsonl` is a passive export rather
# than the wire protocol, so a push is what makes issues survive a reclone.
#
# The pre-push hook already runs the push on every git push. These are for pushing
# without one, and for recovering after the hook reported a failure.

# Push the database to the git remote
[group('beads')]
bd-push:
    @bash scripts/bd-dolt-push.sh

# Pull the database from the git remote
[group('beads')]
bd-pull:
    bd dolt pull

# Commit the Dolt writes that `dolt.auto-commit: batch` defers
[group('beads')]
bd-commit:
    bd dolt commit

# --- health ----------------------------------------------------------------

# Check the database for corruption and fix what is fixable
[group('beads')]
bd-doctor:
    bd doctor

# Every worktree shares the primary checkout's `.beads`, so a missing local one is
# not a fault. This is the authoritative answer to which workspace is active.

# Where the active beads workspace is
[group('beads')]
bd-where:
    bd where

# Every effective setting, with the file or database each came from
[group('beads')]
bd-config:
    bd config show
