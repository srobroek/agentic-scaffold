# TypeScript recipes, imported by the root justfile.

# Format, lint, type-check, and test
[group('ts')]
ts: ts-fmt ts-lint ts-types ts-test

# Format and organise imports. biome owns this half of the split
[group('ts')]
ts-fmt:
    bunx biome check --write .

# Lint. oxlint owns this half: 59 of typescript-eslint's 61 type-aware rules
# against biome's 4 outside nursery
[group('ts')]
ts-lint:
    bunx oxlint

# Type check
[group('ts')]
ts-types:
    bunx tsc --noEmit

# Test
[group('ts')]
ts-test:
    bun test

# Unused files, exports, and dependencies
[group('ts')]
ts-dead:
    bunx knip

# Coverage
[group('ts')]
ts-cov:
    bun test --coverage
