# Gotchas: Hooks

`lefthook install` tries to rewrite files in the configured `core.hooksPath`
directory and fails without write access to it. `--reset-hooks-path` unsets a
repo-local override without restoring it.

`prek install` refuses to run while `core.hooksPath` points outside the
repository, and succeeds once it is set repo-locally.

`prek` skips dot-prefixed directories during discovery, so a `.pre-commit.d/`
fragment directory is invisible to it. It has no `extends` key; unknown keys are
ignored with a warning.

`pre-commit` rejects `repo: builtin` with `Missing required key: rev`, so
builtin hygiene hooks require prek.
