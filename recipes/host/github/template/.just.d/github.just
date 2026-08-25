# CI and governance recipes, contributed by host/github.
#
# Branch protection, required checks, merge types, and repository features are API-only:
# GitHub reads no committed file for any of them, so the files this layer renders
# (CODEOWNERS, the templates, the community health files) are one half and `repo-govern` is
# the other. rules/choices.md records the split.

# A reusable workflow does not run itself, and which ones exist depends on which layers
# rendered, so the caller is derived from the directory rather than written by hand. Run
# this after adopting a language layer. It refuses a ci.yml carrying no generator marker,
# which is how a repository takes the file over.

# Rebuild .github/workflows/ci.yml from the wc-* workflows beside it
[group('github')]
ci-sync:
    @python3 scripts/gen_caller.py .

# Apply branch protection, the merge configuration, and the feature set
[group('github')]
repo-govern:
    @python3 scripts/repo_govern.py

# Report what differs from the intended governance, changing nothing
[group('github')]
repo-govern-check:
    @python3 scripts/repo_govern.py --check
