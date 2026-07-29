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

### hooksPath must be absolute, or hooks skip every worktree

`git config core.hooksPath .git/hooks` works in the primary checkout and fails
silently in a linked worktree. A worktree's `.git` is a file holding
`gitdir: <primary>/.git/worktrees/<name>`, so the relative path resolves to
`<worktree>/.git/hooks` and git reports `Invalid path ...: Not a directory`.

The commit then succeeds with no hook and no warning. Verified: a `prek` hook that
prints `probe....Passed` in the primary printed nothing in a worktree, and the
commit went through.

Set it absolute, from anywhere in the repository:

```sh
git config --local core.hooksPath \
  "$(git rev-parse --path-format=absolute --git-common-dir)/hooks"
```

`--git-common-dir` resolves to the primary `.git` from anywhere in the repository,
so that line works run from any worktree.

The absolute value does not travel, because `.git/config` is never tracked
(`git ls-files .git/config` returns nothing). What is committed is the `just setup`
recipe, which is location-independent; each clone generates its own path. A
colleague cloning elsewhere runs `just setup` and gets theirs.

No relative form works. Git resolves a relative `hooksPath` against the working
directory rather than `$GIT_DIR`, and it expands `~` but not environment
variables: `$GIT_COMMON_DIR/hooks` stays literal. `hooksPath` is a local value in
the shared `.git/config`, so one `just setup` in the primary covers every worktree
and none needs its own `prek install`.
