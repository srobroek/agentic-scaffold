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

### A stage absent from default_install_hook_types is a dead hook

`prek install` writes one shim per entry in `default_install_hook_types`, and
nothing checks that list against the stages the hooks declare. A hook carrying
`stages: [pre-push]` under a config listing only `pre-commit` gets no `pre-push`
shim, so it never runs, and neither install nor commit says anything.

This is why `merge_hooks.py` computes the list from the folded fragments rather
than writing a fixed one: a language layer contributing a `pre-push` hook is the
case a hardcoded list breaks. An unrecognised stage name fails the merge outright,
since a typo would otherwise produce that same silence.

Verified against prek 0.4.11: a config naming six stages installed six shims, one
file per stage under `.git/hooks/`.

### betterleaks 1.7.2 exists, and mise will not install it

`mise latest betterleaks` reports 1.7.1 while GitHub's latest release is v1.7.2.
mise hides a release younger than its `minimum_release_age` and warns rather than
failing, so a config pinning the hidden version fails at install time.

Pin what `mise ls-remote` lists, not what the upstream release page shows.

### A `-system` hook needs its binary, and absence is not a skip

`betterleaks-system` and the other `-system` variants call a binary on `PATH`
rather than installing one. Run before `mise install`, the hook fails with
`No such file or directory (os error 2)` instead of reporting itself skipped, so a
fresh clone sees a hook failure whose cause is not in the message.

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
