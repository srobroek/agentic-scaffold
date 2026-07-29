# Python recipes, imported by the root justfile.

# Format, lint, type-check, and test
[group('python')]
python: python-fmt python-lint python-types python-test

# Format
[group('python')]
python-fmt:
    uv run ruff format .

# Lint
[group('python')]
python-lint:
    uv run ruff check .

# Docstring presence, advisory. ruff has no per-rule severity, so D cannot sit in
# the config without gating a bare `ruff check`
[group('python')]
python-docs:
    uv run ruff check --select D --exit-zero .

# Type check
[group('python')]
python-types:
    uv run ty check

# Test
[group('python')]
python-test:
    uv run pytest

# Unused and undeclared dependencies
[group('python')]
python-deps:
    uv run deptry .

# Coverage
[group('python')]
python-cov:
    uv run pytest --cov --cov-report=term-missing --cov-report=lcov

# Test against every supported interpreter
[group('python')]
python-matrix:
    uv run nox
