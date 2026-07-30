"""This repository's own mise.toml: every pin has to be a version that exists.

Written after CI failed on `Failed to install pipx:yamllint@1.38.1` while `just check` passed
locally. yamllint's newest release is 1.38.0; 1.38.1 was never published. The local pass was
an accident: a python install carried an unrelated yamllint 1.37.1 earlier on PATH, so the
recipe ran that one and never noticed mise had installed nothing.

The failure mode is specific to a pinned toolchain. `mise install` is the only step that
validates a version string, it runs before the tests, and a tool reachable from somewhere else
on PATH hides the gap from every recipe downstream.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
MISE = REPO_ROOT / "mise.toml"

needs_mise = pytest.mark.skipif(shutil.which("mise") is None, reason="mise absent")

# Pins mise cannot enumerate, with why. `latest` is not a version to check, and a backend
# whose registry has no ls-remote entry would report every pin as missing.
UNCHECKABLE = {"python", "uv", "just", "prek", "cargo:gitnr"}

# `latest` on purpose. Every other entry in mise.toml's pinned block is a version some test
# asserts behaviour against; trivy's findings come from a vulnerability database rather than
# from its own behaviour, and no test here asserts a specific finding.
DELIBERATELY_LATEST = UNCHECKABLE | {"trivy"}


def pins() -> dict[str, str]:
    return tomllib.loads(MISE.read_text())["tools"]


def test_every_tool_is_pinned_or_deliberately_latest() -> None:
    """A test skips rather than fails when its tool is absent, so an unpinned toolchain means a
    green run that checked less than it appears to."""
    for name, spec in pins().items():
        assert isinstance(spec, str), f"{name} is not a plain version string"
        if spec == "latest":
            assert name in DELIBERATELY_LATEST, (
                f"{name} is `latest`; pin it, or record here why it should float"
            )


@needs_mise
@pytest.mark.slow
def test_every_pinned_version_exists() -> None:
    """`mise ls-remote <tool>` lists what can be installed. A pin absent from that list fails
    the toolchain install in CI, which happens before any test runs and reports as a mise exit
    code rather than as a bad version."""
    missing = []
    for name, spec in pins().items():
        if spec == "latest" or name in UNCHECKABLE:
            continue
        result = subprocess.run(
            ["mise", "ls-remote", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if result.returncode != 0:
            # A backend that cannot enumerate is not evidence the pin is wrong.
            continue
        available = set(result.stdout.split())
        if spec not in available:
            newest = sorted(available)[-3:] if available else []
            missing.append(f"{name}={spec} (available near: {newest})")

    assert not missing, "pinned versions that do not exist: " + "; ".join(missing)


@needs_mise
def test_the_config_linters_resolve_through_mise() -> None:
    """`lint-config` runs these bare, so one reachable from elsewhere on PATH runs instead of
    the pinned one and the pin is never exercised. That is exactly how yamllint 1.38.1 passed
    locally and failed in CI."""
    for tool in ("yamllint", "taplo", "actionlint", "zizmor"):
        result = subprocess.run(
            ["mise", "which", tool],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.skip(f"{tool} not installed yet; `just setup` installs the toolchain")
        assert "/mise/installs/" in result.stdout, (
            f"{tool} resolves to {result.stdout.strip()}, outside mise, so the pin in "
            "mise.toml is not what lint-config runs"
        )
