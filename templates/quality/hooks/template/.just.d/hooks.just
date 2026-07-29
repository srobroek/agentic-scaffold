# Hook recipes, contributed by quality/hooks and imported by the root justfile.

# Rebuild .pre-commit-config.yaml from .pre-commit.d/
[group('hooks')]
hooks-merge:
    @python3 scripts/merge_hooks.py .

# Absolute is required: a linked worktree's .git is a FILE holding a gitdir
# pointer, so a relative `.git/hooks` resolves to <worktree>/.git/hooks, where git
# reports "Not a directory" and the hook then never fires there, silently.
#
# prek also declines to install when core.hooksPath points outside the repository,
# which is what an ambient global setting does. Verified against prek 0.4.11: it
# prints a note and writes no shim, so a fresh clone has no hooks and nothing says
# so at commit time.

# Point core.hooksPath at this checkout, then install the shims
[group('hooks')]
hooks-install: hooks-merge
    @git config --local core.hooksPath \
      "$(git rev-parse --path-format=absolute --git-common-dir)/hooks"
    prek install

# Run every hook over every tracked file, as CI does
[group('hooks')]
hooks-all: hooks-merge
    prek run --all-files

# Run one group: hygiene, security, quality, docs, or beads
[group('hooks')]
hooks-group group: hooks-merge
    prek run --group {{ group }} --all-files
