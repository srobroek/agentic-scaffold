# Scaffold a repository

Use this procedure for a greenfield repository.

1. Work in a dedicated worktree. Do not scaffold a non-empty directory.
2. Run `uv run <template>/scripts/interview.py --config <template>/copier.yml --source <template> --dest <target> --tag <tag>` from inside the target and relay each `ask.questions` page to the human.
3. Repeat with `--answers-so-far <JSON of every answer so far>` until `complete` is true. When the human picks `More choices`, repeat with the `paging.more` value as `--page`.
4. Run `uv run <template>/scripts/plan.py <template> <target> --data k=v ...` with the `data` list from the interview and show its file map and bootstrap steps.
5. Ask the human to approve the plan.
6. Run the exact `uvx copier copy` command that `--emit-command` prints.
7. Commit the generated repository.
8. Run `just bootstrap` and show its output.
9. Run `just verify` and show its output.

The template accepts only an empty directory or a directory containing `.git` and Copier answers. Copier owns its rendered files; `README.md` is repository-owned after creation. Generator-owned files remain untouched. Updates are three-way merges, and unresolved conflict markers fail `update-scaffold`. When the conflict is in `justfile` itself, `just` cannot parse the file: read Copier's own `unresolved conflict detected` line, resolve the markers with git, then run `just update-scaffold` again.

The scaffold never runs `bootstrap`, `verify`, or any generated-repository command. The generated repository owns those commands.
