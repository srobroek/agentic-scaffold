# cocogitto recipes, imported by the root justfile.

# What the next bump would be, from the commits since the last tag
[group('release')]
cog-preview:
    cog bump --auto --dry-run

# Bump, write the changelog, and tag from the commits since the last tag
[group('release')]
cog-bump:
    cog bump --auto

# Verify every commit since the last tag parses as a Conventional Commit
[group('release')]
cog-check:
    cog check

# `--at` takes a tag, not a revision: `--at HEAD` fails with "invalid commit range
# pattern". Bare `cog changelog` covers the commits since the last tag, which is what
# the next release would carry.

# The changelog entry the next release would carry
[group('release')]
cog-changelog:
    cog changelog
