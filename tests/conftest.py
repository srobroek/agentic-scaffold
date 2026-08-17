"""Shared markers.

Most of this suite runs a real tool against rendered output, which is deliberate: every
defect found while building these layers rendered cleanly first and failed only when the
tool read the result. A handful of those tools are expensive enough to dominate a run, so
they carry `@pytest.mark.slow` and can be skipped while iterating.

`just check` runs everything. `SCAFFOLD_SKIP_SLOW=1 uv run pytest` skips what installs an
npm tree, builds a container image, or compiles a crate.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

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
