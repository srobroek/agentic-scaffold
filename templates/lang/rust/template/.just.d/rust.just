# Rust recipes, imported by the root justfile.

# Format, lint, and test the rust code
[group('rust')]
rust: rust-fmt rust-lint rust-test

# Format
[group('rust')]
rust-fmt:
    cargo fmt --all

# Clippy with warnings as errors
[group('rust')]
rust-lint:
    cargo clippy --all-targets --all-features -- -D warnings

# Test through nextest
[group('rust')]
rust-test:
    cargo nextest run --all-features

# Supply chain: advisories, licences, bans, sources
[group('rust')]
rust-deny:
    cargo deny check

# Unused dependencies
[group('rust')]
rust-machete:
    cargo machete

# Coverage
[group('rust')]
rust-cov:
    cargo llvm-cov nextest --all-features --lcov --output-path lcov.info
