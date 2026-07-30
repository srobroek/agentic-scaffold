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

import pytest

SKIP_SLOW = os.environ.get("SCAFFOLD_SKIP_SLOW") == "1"


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "slow: shells out to a toolchain that installs, compiles, or builds an image",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if not SKIP_SLOW:
        return
    skip = pytest.mark.skip(reason="SCAFFOLD_SKIP_SLOW=1")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
