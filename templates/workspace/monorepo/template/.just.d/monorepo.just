# Workspace recipes, contributed by workspace/monorepo.
#
# The member path comes from the workspace manifest's own glob, so a recipe here and
# the manifest cannot disagree about where members live.

# SCAFFOLD points at a project-scaffold checkout, which holds the language layers.
# Without it `just add` still runs the language generator and creates the member; the
# layer's tool configs and fragments are what need the templates.
scaffold := env_var_or_default("SCAFFOLD", "")

# Add a workspace member: `just add api-client rust`
[group('workspace')]
add name lang:
    @python3 scripts/add_member.py {{ name }} {{ lang }} \
      {{ if scaffold != "" { "--scaffold " + scaffold } else { "" } }}

# Every member the workspace glob resolves
[group('workspace')]
members:
    #!/usr/bin/env bash
    set -euo pipefail
    python3 - <<'PY'
    import json, pathlib, tomllib

    repo = pathlib.Path(".")
    globs = []
    if (repo / "Cargo.toml").is_file():
        data = tomllib.loads((repo / "Cargo.toml").read_text())
        globs = (data.get("workspace") or {}).get("members") or []
    elif (repo / "pyproject.toml").is_file():
        data = tomllib.loads((repo / "pyproject.toml").read_text())
        globs = ((data.get("tool") or {}).get("uv") or {}).get("workspace", {}).get("members") or []
    elif (repo / "package.json").is_file():
        globs = json.loads((repo / "package.json").read_text()).get("workspaces") or []
    elif (repo / "go.mod").is_file():
        globs = ["cmd/*"]

    for pattern in globs:
        for path in sorted(repo.glob(pattern)):
            if path.is_dir():
                print(path)
    PY
