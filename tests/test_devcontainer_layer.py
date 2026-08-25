"""workspace/devcontainer: the container a repository is opened in.

devcontainer.json is JSONC, so `json.load` rejects it and proves nothing about whether
the file is valid. Every structural assertion here goes through the real
`@devcontainers/cli read-configuration`, which is the parser an editor uses.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import render_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent

ANSWERS = "project_name: demo\ndocker_in_docker: false\nforward_ports: [3000, 8080]\n"
DIND = "project_name: demo\ndocker_in_docker: true\nforward_ports: []\n"

needs_npx = pytest.mark.skipif(shutil.which("npx") is None, reason="npx absent")


def render(dest: Path, answers: str) -> subprocess.CompletedProcess[str]:
    return render_recipe("workspace/devcontainer", dest, answers)


def configuration(dest: Path) -> dict:
    """Parse through the real CLI, which is the only thing that reads JSONC correctly."""
    result = subprocess.run(
        ["npx", "--yes", "@devcontainers/cli", "read-configuration", "--workspace-folder", "."],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # The CLI prints a banner line before the JSON.
    payload = next(line for line in result.stdout.splitlines() if line.startswith("{"))
    return json.loads(payload)["configuration"]


@pytest.fixture
def devcontainer(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render(dest, ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def test_the_file_renders(devcontainer: Path) -> None:
    assert (devcontainer / ".devcontainer" / "devcontainer.json").is_file()


def test_it_is_jsonc_not_json(devcontainer: Path) -> None:
    """The comments carry the reasoning, and the format permits them.

    Asserted so nobody 'fixes' a parse error by stripping them: a strict json.load
    failing here is expected, and the CLI test below is what proves validity.
    """
    body = (devcontainer / ".devcontainer" / "devcontainer.json").read_text()
    assert "//" in body
    with pytest.raises(json.JSONDecodeError):
        json.loads(body)


@needs_npx
def test_the_real_parser_accepts_it(devcontainer: Path) -> None:
    config = configuration(devcontainer)
    assert config["name"] == "demo"
    assert config["image"].startswith("mcr.microsoft.com/devcontainers/base")


@needs_npx
def test_mise_is_the_only_toolchain_feature(devcontainer: Path) -> None:
    """One toolchain source. A per-language feature would pin a second copy of a
    compiler that could disagree with what .mise/conf.d resolves for CI and a laptop."""
    features = configuration(devcontainer)["features"]
    assert any("features/mise" in name for name in features)
    for language in ("features/go", "features/node", "features/python", "features/rust"):
        assert not any(language in name for name in features), (
            f"{language} duplicates what mise already installs"
        )


@needs_npx
def test_setup_runs_through_the_same_entry_point_as_a_fresh_clone(devcontainer: Path) -> None:
    """`just setup`, not a copy of its steps, so the two cannot drift.

    `mise trust` precedes it because an untrusted config is skipped silently: without
    it `mise install` reports success having installed nothing.
    """
    command = configuration(devcontainer)["postCreateCommand"]
    assert "mise trust" in command
    assert command.index("mise trust") < command.index("mise install")
    assert "just setup" in command


@needs_npx
def test_the_mise_shims_precede_the_system_path(devcontainer: Path) -> None:
    """A tool mise installed otherwise loses to an older copy in the base image."""
    path = configuration(devcontainer)["remoteEnv"]["PATH"]
    assert path.index("mise/shims") < path.index("containerEnv:PATH")


@needs_npx
def test_it_does_not_run_as_root(devcontainer: Path) -> None:
    """Building as root leaves root-owned files in the bind-mounted workspace, which
    the host user then cannot edit."""
    assert configuration(devcontainer)["remoteUser"] == "vscode"


@needs_npx
def test_forwarded_ports_are_rendered(devcontainer: Path) -> None:
    assert configuration(devcontainer)["forwardPorts"] == [3000, 8080]


@needs_npx
def test_no_empty_forward_ports_key(tmp_path: Path) -> None:
    """An empty list renders no key at all rather than `[]`."""
    dest = tmp_path / "dind"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render(dest, DIND).returncode == 0
    assert "forwardPorts" not in configuration(dest)


@needs_npx
def test_docker_in_docker_is_opt_in(tmp_path: Path) -> None:
    """It runs a privileged daemon inside the container, so it is off unless the
    container layer rendered."""
    off = configuration(  # the default fixture answers
        _rendered(tmp_path / "off", ANSWERS)
    )["features"]
    assert not any("docker-in-docker" in name for name in off)

    on = configuration(_rendered(tmp_path / "on", DIND))["features"]
    assert any("docker-in-docker" in name for name in on)


def _rendered(dest: Path, answers: str) -> Path:
    dest.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render(dest, answers).returncode == 0
    return dest
