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

# Lint the scripts and the prose
lint:
    {{ py }} ruff check scripts templates
    {{ py }} ruff format --check scripts templates
    {{ py }} scripts/lint_prose.py

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
check: lint index-check profiles test
    @echo "ok"
