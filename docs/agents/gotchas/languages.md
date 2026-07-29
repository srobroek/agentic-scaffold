# Gotchas: Language tooling

| Tool | Failure |
|---|---|
| `cargo init` | writes no `license` key, so `cargo-deny` fails its licence check against the crate itself |
| golangci-lint v2 | rejects v1's top-level `linters-settings`; settings nest under `linters.settings` |
| golangci-lint | `gosec` ships inside it and is off by default |
| ruff | `DOC` rules are preview-gated and check nothing without `preview = true` |
| ruff | `D` in `select` makes a bare `ruff check` fail, defeating the advisory intent |
| bun | `bun exec` is not a command; use `bunx` |
| gix | needs an explicit `sha1` or `sha256` feature or the build fails |
