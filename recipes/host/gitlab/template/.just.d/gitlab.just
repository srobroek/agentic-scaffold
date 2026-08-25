# GitLab recipes, contributed by host/gitlab and imported by the root justfile.

# Rebuild .gitlab-ci.yml's stages list from .gitlab/ci/
[group('gitlab')]
gitlab-sync:
    @uv run --no-project --with pyyaml python3 scripts/gen_gitlab_stages.py .

# A job naming a stage the pipeline does not declare fails the whole pipeline rather
# than skipping, and the include is a glob, so a language layer adopted later can
# leave the list behind. Compared in a copy: a check that rewrites what it checks
# leaves a dirty tree and passes on the rerun.

# Fail when the stages list is stale
[group('gitlab')]
gitlab-check:
    #!/usr/bin/env bash
    set -euo pipefail
    scratch=$(mktemp -d)
    trap 'rm -rf "$scratch"' EXIT
    cp .gitlab-ci.yml "$scratch/.gitlab-ci.yml"
    ln -s "$PWD/.gitlab" "$scratch/.gitlab" 2>/dev/null || true
    uv run --no-project --with pyyaml python3 scripts/gen_gitlab_stages.py "$scratch" >/dev/null
    if ! diff -q .gitlab-ci.yml "$scratch/.gitlab-ci.yml" >/dev/null; then
      echo "stages list is stale; run 'just gitlab-sync'" >&2
      diff .gitlab-ci.yml "$scratch/.gitlab-ci.yml" || true
      exit 1
    fi

# Validating needs the instance: `include:` globs and CI components resolve server
# side, so a local parse cannot tell whether the pipeline is valid.

# Validate the pipeline against the GitLab instance
[group('gitlab')]
gitlab-lint:
    glab ci lint .gitlab-ci.yml
