set shell := ["bash", "-uc"]

# List project commands.
default:
    @just --list

# Install this repository's tools.
bootstrap:
    mise install
    uv sync

# Run the repository checks.
verify: test
    uv run python -m compileall -q scripts

# Run the test suite.
test:
    uv run pytest -q

# Run the prose gate.
prose:
    uvx --from slopvac==1.0.1 slopvac README.md docs --profile normal

# Validate YAML and GitHub workflows.
lint-config:
    yamllint .github/workflows/ci.yml
    actionlint .github/workflows/*

# Run all local checks.
check: test prose lint-config
    @echo "ok"
