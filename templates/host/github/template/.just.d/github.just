# Repository governance recipes, contributed by host/github.
#
# Branch protection, required checks, merge types, and repository features are API-only:
# GitHub reads no committed file for any of them, so the files this layer renders
# (CODEOWNERS, the templates, the community health files) are one half and this script is
# the other. rules/choices.md records the split.

# Apply branch protection, the merge configuration, and the feature set
[group('github')]
repo-govern:
    @python3 scripts/repo_govern.py

# Report what differs from the intended governance, changing nothing
[group('github')]
repo-govern-check:
    @python3 scripts/repo_govern.py --check
