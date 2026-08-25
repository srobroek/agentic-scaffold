"""Shared markers, and the one way this suite reaches the scaffold CLI.

Most of this suite runs a real tool against rendered output, which is deliberate: every
defect found while building these recipes rendered cleanly first and failed only when the
tool read the result. A handful of those tools are expensive enough to dominate a run, so
they carry `@pytest.mark.slow` and can be skipped while iterating.

`just check` runs everything. `SCAFFOLD_SKIP_SLOW=1 uv run pytest` skips what installs an
npm tree, builds a container image, or compiles a crate.

`render_recipe` is the shared render path. Fifteen test modules had their own copy of it,
which is why the CLI rename touched fifteen files instead of one.
"""

from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAFFOLD = REPO_ROOT / "scripts" / "scaffold.py"

SKIP_SLOW = os.environ.get("SCAFFOLD_SKIP_SLOW") == "1"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "slow: shells out to a toolchain that installs, compiles, or builds an image",
    )


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if not SKIP_SLOW:
        return
    skip = pytest.mark.skip(reason="SCAFFOLD_SKIP_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)


def scaffold(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """One `scripts/scaffold.py` invocation, both streams captured, exit code returned.

    Exit codes the CLI promises: 2 usage, 3 a missing binary or a refused precheck,
    4 copier raised, 5 the plan found a conflict.
    """
    return subprocess.run(
        [sys.executable, str(SCAFFOLD), *args],
        capture_output=True,
        text=True,
        check=False,
        env=env,
    )


def render_recipe(
    recipe: str, dest: Path, answers: str = "", *flags: str
) -> subprocess.CompletedProcess[str]:
    """`scaffold render <recipe> --dest <dest>`, answers written beside the destination.

    Beside rather than inside, because an answers file in the destination would render
    into the tree under test. The name carries the recipe, so two recipes into one
    destination keep their own answers.

    An empty `answers` passes no file at all: an empty YAML document parses as None,
    which copier rejects, and a recipe taking no variables needs no answers.
    """
    argv = ["render", recipe, "--dest", str(dest)]
    if answers:
        answers_file = dest.parent / f"{dest.name}-{recipe.replace('/', '-')}.yml"
        answers_file.write_text(answers)
        argv += ["--data-file", str(answers_file)]
    return scaffold(*argv, *flags)


def load_scaffold():
    """`scripts/scaffold.py` as a fresh module object, for tests that read or point its tables.

    Loaded by path rather than through `sys.path`, so no import-order rule has to be
    suppressed, and fresh each call so a test may point `RECIPES` at a probe tree without
    leaking that into the next one.
    """
    spec = importlib.util.spec_from_file_location("scaffold_under_test", SCAFFOLD)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mise_bin(tool: str) -> Path | None:
    """The directory holding the `tool` that mise.toml pins, or None when mise cannot supply it.

    Resolved through `mise which` rather than by joining `installs/<tool>/latest/bin`. That path
    is a symlink to whatever version was installed last, so it pointed at node 25 on the machine
    where mise.toml pinned 24, and on a CI runner it does not exist at all: a test then falls
    back to whatever the runner image ships. Five CDK tests errored in CI that way, on a runner
    npm whose `npm ci` broke projen's generated `install:ci` task, while passing locally against
    a version the pin never named.
    """
    if shutil.which("mise") is None:
        return None
    result = subprocess.run(
        ["mise", "which", tool], capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        return None
    return Path(result.stdout.strip()).parent


def tool_env(*tools: str) -> dict[str, str]:
    """os.environ with each pinned tool's directory prepended to PATH.

    mise installs outside the PATH a bare subprocess inherits, so a test shelling out to npm or
    node needs this to reach the pinned one.
    """
    env = dict(os.environ)
    for tool in tools:
        found = mise_bin(tool)
        if found is not None and found.is_dir():
            env["PATH"] = f"{found}:{env['PATH']}"
    return env
