# Gotchas

Failures found by running the tools. Each one produces a wrong result silently or
fails at first use. The layers encode the fix; these files record why the fix
exists.

| Leaf | Covers |
|---|---|
| `tooling.md` | copier, projen, better-t-stack, mise, gitnr |
| `ci.md` | GitHub Actions, GitLab CI |
| `languages.md` | cargo, ruff, golangci-lint, bun |
| `hooks.md` | prek, lefthook, pre-commit |
| `docs.md` | Astro |

Hand-written, with no generated block. `templates/docs/agents/` seeds the
matching leaf in a scaffolded repository.

Add an entry when a tool fails in a way that reading its documentation would not
have predicted. Record the cause, not the symptom alone.
