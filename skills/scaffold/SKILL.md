# Scaffold a repository

Use this procedure for a greenfield repository.

1. Work in a dedicated worktree. Do not scaffold a non-empty directory.
2. Run `python3 scripts/interview.py` and relay each `ask.questions` page.
3. Repeat with `--answers-so-far` until `complete` is true. Use `--page` for long choice lists.
4. Run `python3 scripts/plan.py <template> <destination> --data ...` and show its file map.
5. Ask a human to approve the plan.
6. Run the exact `uvx copier copy` command from the interview output.
7. Commit the generated repository.
8. Run `just bootstrap` and show its output.
9. Run `just verify` and show its output.

The template accepts only an empty directory or a directory containing `.git` and Copier answers. Copier owns its rendered files; `README.md` is repository-owned after creation. Generator-owned files remain untouched. Updates are three-way merges, and unresolved conflict markers fail `update-scaffold`.

The scaffold never runs `bootstrap`, `verify`, or any generated-repository command. The generated repository owns those commands.
