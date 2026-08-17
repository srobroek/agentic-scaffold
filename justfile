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

# Render one layer into a destination
render layer dest *answers:
    {{ py }} scripts/render.py {{ layer }} {{ dest }} {{ answers }}

# List what a layer would write, writing nothing
preview layer dest *answers:
    {{ py }} scripts/render.py {{ layer }} {{ dest }} --pretend {{ answers }}

# Regenerate docs/INDEX.md from templates/
index:
    {{ py }} scripts/index.py

# Fail when docs/INDEX.md is stale
index-check:
    {{ py }} scripts/index.py --check

# templates/ carries python too: copier tasks and the scripts a layer ships into
# the generated project. Linting scripts/ alone let an unformatted one through.

# A .jinja file is deliberately not valid YAML, TOML, or JSON: it holds `{% raw %}{{ }}{% endraw %}` and
# `{% raw %}{% if %}{% endraw %}`, and a conditional filename is not a path a parser accepts. So the
# structural linters run over the repository's OWN configuration and skip templates/,
# which the layer tests cover instead by rendering and parsing the result.

# Lint the scripts and the prose
lint:
    {{ py }} ruff check scripts templates
    {{ py }} ruff format --check scripts templates
    {{ py }} scripts/lint_prose.py

# Lint this repository's own YAML, TOML, JSON, and workflows
lint-config:
    #!/usr/bin/env bash
    set -euo pipefail

    # Without a project .yamllint the defaults flag 80-column lines and a missing document
    # start, neither of which is a rule here.
    files=$(git ls-files '*.yml' '*.yaml' | grep -v '^templates/' || true)
    if [ -n "$files" ]; then
      echo "$files" | xargs yamllint -f parsable         -d "{extends: relaxed, rules: {line-length: disable, document-start: disable}}"
    fi

    toml=$(git ls-files '*.toml' | grep -v '^templates/' || true)
    if [ -n "$toml" ]; then
      echo "$toml" | xargs taplo lint
    fi

    # Parsed rather than linted: a JSON syntax error is the only failure mode, and every
    # committed .json here is either generated or a tool's own schema-checked config.
    json=$(git ls-files '*.json' | grep -v '^templates/' || true)
    if [ -n "$json" ]; then
      echo "$json" | xargs -n1 python3 -c 'import json,sys; json.load(open(sys.argv[1]))'
    fi

    # This repository ships one workflow, and the layers ship many. actionlint reads only
    # what is rendered here; a template's workflow is checked by its layer's tests, which
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
      zizmor --min-severity medium .github/workflows
    fi

# Fix what lint can fix
fix:
    {{ py }} ruff check --fix scripts templates
    {{ py }} ruff format scripts templates

# Most of the wall clock is waiting on a real toolchain rather than on CPU, and every test
# renders into its own tmp_path sharing no state, so the suite parallelises cleanly.
# Measured on 14 cores: 889s serial against 160s at -n auto, same 543 passing.

# Run the tests
test:
    {{ py }} pytest -q -n auto

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

# Validate every profile against templates/
profiles:
    {{ py }} scripts/profiles.py

# Render one profile into a destination and run its build
render-profile profile dest:
    {{ py }} scripts/render_profile.py {{ profile }} {{ dest }} --build

# A tree that renders is not a project that builds, which is the failure class every
# porting defect fell into: each rendered cleanly and failed only when the real tool read
# the result. This renders every profile and runs each one's own build.
#
# The generator is not run, so a build here asserts only what the layers produce.

# Render and build every profile
profiles-build:
    #!/usr/bin/env bash
    set -uo pipefail
    scratch=$(mktemp -d)
    trap 'rm -rf "$scratch"' EXIT
    failed=0
    for path in profiles/*.yml; do
      name=$(basename "$path" .yml)
      if ! {{ py }} scripts/render_profile.py "$name" "$scratch/$name" --build; then
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
