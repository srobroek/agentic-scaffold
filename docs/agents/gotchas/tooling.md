# Gotchas: Scaffolding tools

### copier

| Failure | Cause |
|---|---|
| `found character '%' that cannot start any token` | `copier.yml` parses as YAML before jinja renders it. A top-level `{% set %}` fails. Use an inline expression inside a value |
| `SyntaxError` pointing at an unrelated line | a conditional filename containing a quote breaks jinja compilation, because the filename is embedded in generated Python. Use a derived boolean carrying `when: false` |
| a `yaml`-typed answer rejects its own default | a jinja list renders as a Python repr with single quotes. Append `| tojson` |
| a conditional path renders partially | each path segment needs its own guard |
| `.DS_Store` appears in a rendered project | `_subdirectory` stops copier applying its own `DEFAULT_EXCLUDE`. Pass `--exclude` explicitly |

`_external_data` resolves relative to the destination, so a layer can read a
sibling's answers file. A missing file warns and falls back to the default.

`DEFAULT_EXCLUDE` stops applying once `_subdirectory` is set, verified against
copier 9.17.0 with a template holding nothing but `_subdirectory: template` and a
planted `.DS_Store`. Every layer here sets `_subdirectory`, so every layer was
affected.

The failure hides twice. `.DS_Store` is gitignored, so a template directory
carrying one shows nothing in `git status`, and the file surfaces only in a
rendered project. Finder writes one into any directory it displays.

`--exclude` replaces the default set rather than adding to it, so `render.py`
repeats all eight defaults alongside `.DS_Store` and `._*`.
`tests/test_render_excludes.py` plants an artifact and asserts it does not render.

### projen

`projen new` produces a project that cannot synthesise. It pins
`typescript: "*"`, which resolves to TypeScript 7, and `ts-node` fails against
it with `TypeError: Cannot read properties of undefined (reading 'fileExists')`.
The failure is identical on Node 22 and 24.

`runner: typescript.TypeScriptRunner.tsx()` fixes it, but the synth that would
write that task is the one that fails. Install `tsx` and run
`npx tsx .projenrc.ts` once directly.

`projenrcTsRunner` is not an option name and is ignored without warning. The
option is `runner`.

`.projen/tasks.json` and 16 other files are mode `444`.

### better-t-stack

`--yes` rejects any stack flag. `addonOptions` has no flag form. Use
`create-json`.

Requesting `biome` and `oxlint` together writes only `biome.json`; oxlint is
dropped with no warning. They are alternative toolchains, and `oxlint` alone
brings `oxfmt` with it.

Its tauri addon puts `src-tauri` inside the web app with no Cargo workspace.
A Rust-first project wants the reverse: a workspace member at
`apps/<name>/src-tauri` using `edition.workspace = true`.

`skills` writes nothing when no frontend is selected. `mcp` writes MCP
configuration for three editors.

### Toolchain

`gitnr` writes to a path that must already exist; `-s` writes `.gitignore` in
the working directory.

A `mise.toml` key holding a colon, such as `pipx:structkit`, must be quoted or
every `mise install` fails.

### repomix

`--compress` cut 21 percent on a 4,107-file Rust and TypeScript repository, not
the 70 percent its documentation claims. Tree-sitter only compresses languages it
has a grammar for, and markdown plus JSON were 59 percent of the bytes and passed
through untouched.

| Extension | Change under `--compress` |
|---|---|
| `.md`, `.json` | 0 percent |
| `.rs` | -26 percent |
| `.ts` | -42 percent |
| `.tsx` | -65 percent |
| `.py` | -68 percent |
| `.mjs` | -80 percent |

197 of those 4,107 files came out **larger**. One 672-line Rust file grew from
24,523 to 28,548 characters, because doc comments are duplicated around the
`⋮----` elision markers and signatures are emitted more than once: 38 `pub fn`
occurrences compressed against 27 uncompressed. Comment-dense Rust is hit
hardest.

`--include` is the better lever. Packing code alone gave 2,009,042 tokens against
10,365,446 for the whole tree, an 81 percent reduction, with no duplication.

A pack is also cheap: 1.4s for 1,269 files, 3.6s for 4,107. Anything built on the
assumption that a pack is expensive, such as gating it behind a clean-tree check
and a detached re-exec, is solving a problem that is not there.

repomix does not cache. Running it twice with identical arguments took 1.83s then
1.35s for the same token count, so a second pack costs the same as the first.

`repomix --skill-generate` writes accurate `references/*.md` and a `SKILL.md`
whose usage examples are invented. On a repository holding only `src/lib.ts`,
`package.json`, and `README.md`, the generated `SKILL.md` told the reader to look
at `src/index.ts (42 lines)`, `src/utils/helpers.ts (128 lines)`, and
`function calculateTotal`. None of them existed. What carries real values is the
frontmatter name, the description, and the H1. Review or replace `SKILL.md`
rather than trusting it.

`--skill-generate` also prompts for an output path. Pass `--skill-output <path>`
and `-f` together or a hook hangs waiting on the prompt.

### bash on macOS

macOS ships bash 3.2, where `mapfile` and `readarray` do not exist. A script using
either prints `mapfile: command not found` and then, under `set -u`, dies on the
unbound array it never filled. With `set -uo pipefail` but no `-e` the script
still exits 0, so a wrapper looked like it passed while linting nothing.

Use `while IFS= read -r line; do ... done < <(...)` instead, and give any wrapper
a test asserting its exit code rather than trusting its output.

### worktrunk copy-ignored

An exclude beats an include. Verified by listing `target/` and `.venv/` in both
`.worktreeinclude` and `[step.copy-ignored] exclude`: a dry-run into a second
worktree copied only `.env`.

Project and user excludes combine, so a path the user config excludes cannot be
brought back by a project `.worktreeinclude`. The default user config excludes
`.venv/`, `venv/`, `target/`, and `.cargo/config.toml`, which are the paths most
worth copying, so naming them in `.worktreeinclude` achieves nothing.

`--require-include` makes the whole step a no-op without a `.worktreeinclude`, and
the user config passes it. A repository with no such file starts every worktree
cold.

Only a gitignored path is copied, judged from the destination worktree's own
`.gitignore`. A branch created before an ignore rule was committed does not see it, so
the copy silently skips the file. Symptom: a dry-run reports one entry where three
were expected. Commit the ignore rules before branching.
