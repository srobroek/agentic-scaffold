# project-scaffold

A Copier template for a new repository.

## Requirements

- `uv`
- `copier` 9.18 or newer
- `git`
- `just`
- `mise`

## Use

Run the interview, review the plan, and render into an empty directory:

```sh
uv run scripts/interview.py --config copier.yml --dest /tmp/new-repository
uv run scripts/plan.py . /tmp/new-repository --data name=new-repository --data license=apache-2.0
uvx copier copy --defaults --vcs-ref v1.0.0 --data name=new-repository . /tmp/new-repository
```

The generated repository owns `just bootstrap` and `just verify`. This scaffold does not run generated-repository commands.

## Updating

Tag template changes. In a generated repository, run `just update-scaffold`. The recipe refuses unresolved conflict markers.

## Layout

- `copier.yml` defines answers.
- `template/` contains the single Copier template.
- `scripts/interview.py` presents answers without writing files.
- `scripts/plan.py` previews rendered files and bootstrap steps.
- `skills/scaffold/SKILL.md` describes the agent procedure.

`just update-scaffold` runs `copier update` and fails on unresolved conflict markers. A conflict inside `justfile` stops `just` before the recipe runs; Copier prints `unresolved conflict detected`, and the markers are resolved with git before the next run.
