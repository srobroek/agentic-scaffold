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

### Rust lint levels against `-D warnings`

CI runs `cargo clippy --all-targets --all-features -- -D warnings`, which promotes
every warn to an error. Any warn-level lint in `[lints]` therefore fails the build,
and two of them fire on `cargo init`'s own scaffold.

| Lint | What it rejects in a fresh crate |
|---|---|
| `rust.missing_docs` | `pub fn add` carries no doc comment |
| `clippy.pedantic` | `must_use_candidate` on a two-line function |

Both are left out of the generated manifest. Turn them on per crate once the code
and its docs exist. `unwrap_used` and `expect_used` stay at warn because
`clippy.toml` sets `allow-unwrap-in-tests`, so they do not fire on the test the
scaffold writes.
