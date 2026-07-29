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

# Run the tests
test:
    {{ py }} pytest -q

# Everything CI runs
check: lint index-check test
    @echo "ok"
