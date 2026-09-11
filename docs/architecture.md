# Architecture

This repository is one Copier template repository. It creates a new repository from an empty directory or a directory containing only `.git`. The generated repository owns `just bootstrap` and `just verify`; the scaffold executes neither command.

## Ownership

- Copier-owned files are updated by `copier update`.
- `README.md` is repository-owned after creation through `_skip_if_exists`.
- Generator-owned files are untouched.

The template has no managed blocks, merge engine, run markers, or stage pipeline. Each rendered path is a whole file.

## Answers and updates

`copier.yml` contains the questions. `scripts/interview.py` presents them without writing files. `scripts/plan.py` renders into a temporary directory and reports the resulting file map and bootstrap commands. The plan refuses a non-greenfield target.

Updates use Copier's tagged source and three-way merge. `update-scaffold` runs `uvx copier update --defaults --conflict inline` and fails when `<<<<<<<` markers remain.

Conditional paths are controlled by `hooks`, `agentic`, `beads`, and `visibility`. Language is recorded for a later step and does not render language-specific files in this step.
