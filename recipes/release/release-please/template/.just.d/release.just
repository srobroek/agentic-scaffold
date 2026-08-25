# Release recipes, contributed by release/release-please.

# release-please has no glob support: `packages` takes a literal path per package, and
# its workspace plugins only build a dependency graph over what is already configured.
# `just add` registers a new member at the moment it creates one, so nothing has to
# reconcile the list afterwards.

# What the next release would contain, from the commits since the last tag
[group('release')]
release-preview:
    #!/usr/bin/env bash
    set -euo pipefail
    last=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    if [ -z "$last" ]; then
      echo "no tags yet; every commit is in the first release"
      git log --oneline --no-merges
    else
      echo "commits since $last:"
      git log --oneline --no-merges "$last..HEAD"
    fi

# Which packages release-please tracks
[group('release')]
release-packages:
    @python3 -c "import json; print('\n'.join(json.load(open('release-please-config.json'))['packages']))"
