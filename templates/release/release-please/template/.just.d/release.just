# Release recipes, contributed by release/release-please.

# release-please owns the manifest after the first release, so this rewrites the
# packages list alone and leaves every recorded version alone.

# Rebuild the packages list from the workspace manifest
[group('release')]
release-sync:
    @python3 scripts/sync_release_packages.py .

# Fail when the packages list omits a workspace member
[group('release')]
release-check:
    #!/usr/bin/env bash
    set -euo pipefail
    scratch=$(mktemp -d)
    trap 'rm -rf "$scratch"' EXIT
    cp release-please-config.json .release-please-manifest.json "$scratch/"
    for f in Cargo.toml pyproject.toml package.json go.mod; do
      [ -f "$f" ] && cp "$f" "$scratch/"
    done
    for d in crates packages cmd libs apps; do
      [ -d "$d" ] && cp -R "$d" "$scratch/"
    done
    python3 scripts/sync_release_packages.py "$scratch" >/dev/null
    if ! diff -q release-please-config.json "$scratch/release-please-config.json" >/dev/null; then
      echo "release-please packages are stale; run 'just release-sync'" >&2
      diff release-please-config.json "$scratch/release-please-config.json" || true
      exit 1
    fi

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
