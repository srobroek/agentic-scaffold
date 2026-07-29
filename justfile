set shell := ["bash", "-uc"]

py := "uv run"

# List the recipes
default:
    @just --list

# Install the toolchain and the hook shims
setup:
    mise install
    uv sync
    # ABSOLUTE, not .git/hooks. A linked worktree's .git is a FILE, so a relative
    # hooksPath resolves to <worktree>/.git/hooks and git reports
    # "Not a directory" -- the hook then silently never runs there.
    git config --local core.hooksPath "$(git rev-parse --path-format=absolute --git-common-dir)/hooks"
    prek install
    @echo "hooksPath set to an absolute path, so prek's shims fire in linked worktrees too"

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

# Lint the scripts and the prose
lint:
    {{ py }} ruff check scripts
    {{ py }} ruff format --check scripts
    {{ py }} scripts/lint_prose.py

# Fix what lint can fix
fix:
    {{ py }} ruff check --fix scripts
    {{ py }} ruff format scripts

# Run the tests
test:
    {{ py }} pytest -q

# Everything CI runs
check: lint index-check test
    @echo "ok"
