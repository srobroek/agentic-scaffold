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

### ruff preview turns on lints that reject its own config

`preview = true` is required for the `DOC` rules, and it also enables `RUF201`
(`rule-codes-in-selectors`), new in ruff 0.16. That rule rejects a specific rule
code inside `lint.per-file-ignores`, so `"tests/**" = ["S101"]` fails the very
config that selected it. Use the rule name, `assert`. A group prefix such as `ANN`
is still accepted; only specific codes are rejected.

A wrong selector name is a **warning**, not an error: `Unknown rule selector
'flake8-annotations'` printed while `ruff check` still reported "All checks
passed". Read the warnings, or an ignore silently covers nothing.

`uv init --lib` writes a function into `src/<pkg>/__init__.py`, which
`non-empty-init-module` rejects. Without a per-file ignore the scaffold fails
before a line of real code exists.
