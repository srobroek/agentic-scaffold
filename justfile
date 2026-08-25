set shell := ["bash", "-uc"]

py := "uv run"

# List the recipes
default:
    @just --list

# Install the toolchain, the dependencies, and the hook shims
setup: hooks-path
    mise install
    uv sync
    prek install

# Absolute is required: a linked worktree's .git is a FILE holding a gitdir
# pointer, so a relative `.git/hooks` resolves to <worktree>/.git/hooks and git
# reports "Not a directory", after which the hook never fires there, silently.
#
# --git-common-dir resolves to the primary .git from any worktree, so this runs
# from anywhere. The value never travels: .git/config is untracked, so every
# clone generates its own.

# Point core.hooksPath at the primary checkout, absolutely
[group('setup')]
hooks-path:
    @git config --local core.hooksPath \
      "$(git rev-parse --path-format=absolute --git-common-dir)/hooks"
    @echo "core.hooksPath -> $(git config --local core.hooksPath)"

# Render one recipe into a destination
render recipe dest *args:
    {{ py }} scripts/scaffold.py render {{ recipe }} --dest {{ dest }} {{ args }}

# List what a recipe would write, writing nothing
preview recipe dest *args:
    {{ py }} scripts/scaffold.py render {{ recipe }} --dest {{ dest }} --pretend {{ args }}

# The full file map for a recipe set or profile: owners, merges, conflicts
plan *args:
    {{ py }} scripts/scaffold.py plan {{ args }}

# Re-render recipes at HEAD and 3-way merge local drift
update *args:
    {{ py }} scripts/scaffold.py update {{ args }}

# Report every missing required answer at once
check-answers *args:
    {{ py }} scripts/scaffold.py check-answers {{ args }}

# Regenerate docs/INDEX.md from recipes/
index:
    {{ py }} scripts/index.py

# Fail when docs/INDEX.md is stale
index-check:
    {{ py }} scripts/index.py --check

# recipes/ carries python too: copier tasks and the scripts a recipe ships into
# the generated project. Linting scripts/ alone let an unformatted one through.

# A .jinja file is deliberately not valid YAML, TOML, or JSON: it holds `{% raw %}{{ }}{% endraw %}` and
# `{% raw %}{% if %}{% endraw %}`, and a conditional filename is not a path a parser accepts. So the
# structural linters run over the repository's OWN configuration and skip recipes/,
# which the recipe tests cover instead by rendering and parsing the result.

# Lint the scripts and the prose
lint:
    {{ py }} ruff check scripts recipes
    {{ py }} ruff format --check scripts recipes
    {{ py }} scripts/lint_prose.py

# Lint this repository's own YAML, TOML, JSON, and workflows
lint-config:
    #!/usr/bin/env bash
    set -euo pipefail

    # Without a project .yamllint the defaults flag 80-column lines and a missing document
    # start, neither of which is a rule here.
    files=$(git ls-files '*.yml' '*.yaml' | grep -v '^recipes/' || true)
    if [ -n "$files" ]; then
      echo "$files" | xargs yamllint -f parsable         -d "{extends: relaxed, rules: {line-length: disable, document-start: disable}}"
    fi

    toml=$(git ls-files '*.toml' | grep -v '^recipes/' || true)
    if [ -n "$toml" ]; then
      echo "$toml" | xargs taplo lint
    fi

    # Parsed rather than linted: a JSON syntax error is the only failure mode, and every
    # committed .json here is either generated or a tool's own schema-checked config.
    json=$(git ls-files '*.json' | grep -v '^recipes/' || true)
    if [ -n "$json" ]; then
      echo "$json" | xargs -n1 python3 -c 'import json,sys; json.load(open(sys.argv[1]))'
    fi

    # This repository ships one workflow, and the recipes ship many. actionlint reads only
    # what is rendered here; a recipe's workflow is checked by its tests, which
    # render it and run actionlint against the result.
    if [ -d .github/workflows ]; then
      actionlint
      # zizmor audits for the credential and injection patterns actionlint does not model.
      #
      # NOT --offline. Its network audits are the ones that matter most here: ref-version-mismatch
      # resolves each pinned SHA against the tag its comment claims, and that audit found three
      # pins whose comment lied, including a SHA pointing at v3.0.2 under a `# v4.0.2` comment.
      # An offline run reports none of them. With no token it degrades to the offline set rather
      # than failing, so this works either way.
      #
      # That degradation is quiet, which has bitten once: a local run skipped `github-app` and
      # passed, and CI reported it at HIGH -- an App token inheriting blanket installation
      # permissions. A green local run is therefore weaker evidence than a green CI run. Set
      # GH_TOKEN to get the full set.
      zizmor --min-severity medium .github/workflows
    fi

# Fix what lint can fix
fix:
    {{ py }} ruff check --fix scripts recipes
    {{ py }} ruff format scripts recipes

# Most of the wall clock is waiting on a real toolchain rather than on CPU, and every test
# renders into its own tmp_path sharing no state, so the suite parallelises cleanly.
# Measured on 14 cores: 889s serial against 160s at -n auto, same 543 passing.

# Run the tests
test:
    {{ py }} pytest -q -n auto

# Run the integration cases: recipe combinations rendered, built, asserted
integration *names:
    # Deliberately NOT in `check`. A case renders a whole tree and runs its build, which takes
    # minutes where the unit suite takes seconds, and `check` has to stay fast enough to run on
    # every edit. Run this when recipe composition changes.
    #
    # `just integration --list` names the cases; `--keep` leaves a failing tree on disk.
    {{ py }} tests-integration/run.py {{ names }}

# Run the tests with CI=true, which is what a runner sets
test-ci:
    # Several tools branch on this variable, so a suite that only ever runs without it tests a
    # configuration no runner uses. projen picks `npm ci` over `npm install` when CI is truthy,
    # which errored five CDK tests in GitHub Actions while they passed locally. This recipe
    # reproduces that in one command instead of a push.
    CI=true {{ py }} pytest -q -n auto

# Run the tests serially, for a readable failure or a debugger
test-serial:
    {{ py }} pytest -q

# Skip what installs an npm tree, builds an image, or compiles a crate
test-fast:
    SCAFFOLD_SKIP_SLOW=1 {{ py }} pytest -q -n auto

# Validate every profile against recipes/
profiles:
    {{ py }} scripts/scaffold.py check

# Render one profile into a destination and run its build
render-profile profile dest:
    {{ py }} scripts/scaffold.py render --profile {{ profile }} --dest {{ dest }} --demo --build

# A tree that renders is not a project that builds, which is the failure class every
# porting defect fell into: each rendered cleanly and failed only when the real tool read
# the result. This renders every profile and runs each one's own build.
#
# The generator is not run, so a build here asserts only what the recipes produce.

# Render and build every profile
profiles-build:
    #!/usr/bin/env bash
    set -uo pipefail
    scratch=$(mktemp -d)
    trap 'rm -rf "$scratch"' EXIT
    failed=0
    for path in profiles/*.yml; do
      name=$(basename "$path" .yml)
      if ! {{ py }} scripts/scaffold.py render --profile "$name" --dest "$scratch/$name" --demo --build; then
        failed=$((failed + 1))
      fi
    done
    if [ "$failed" -gt 0 ]; then
      echo "$failed profile(s) failed" >&2
      exit 1
    fi
    echo "every profile rendered and built"

# Everything CI runs
check: lint lint-config index-check profiles test
    @echo "ok"
