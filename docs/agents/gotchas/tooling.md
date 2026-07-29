# Gotchas: Scaffolding tools

### copier

| Failure | Cause |
|---|---|
| `found character '%' that cannot start any token` | `copier.yml` parses as YAML before jinja renders it. A top-level `{% set %}` fails. Use an inline expression inside a value |
| `SyntaxError` pointing at an unrelated line | a conditional filename containing a quote breaks jinja compilation, because the filename is embedded in generated Python. Use a derived boolean carrying `when: false` |
| a `yaml`-typed answer rejects its own default | a jinja list renders as a Python repr with single quotes. Append `| tojson` |
| a conditional path renders partially | each path segment needs its own guard |

`_external_data` resolves relative to the destination, so a layer can read a
sibling's answers file. A missing file warns and falls back to the default.

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
