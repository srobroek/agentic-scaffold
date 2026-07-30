"""profiles/: the layer set per shape, and the validator that keeps it honest.

The validator is not decoration. It caught two real ordering bugs the unit tests could
not: `lang/api` declared `after: host/github` when every other language layer renders
before the host, and `rust-gui` put `workspace/moon` after `workspace/just`, which left the
justfile's import block missing the moon fragment. The second surfaced only when a rendered
profile ran `just just-check`.
"""

from __future__ import annotations

import fnmatch
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES = REPO_ROOT / "profiles"
TEMPLATES = REPO_ROOT / "templates"
VALIDATOR = REPO_ROOT / "scripts" / "profiles.py"

# Named in docs/architecture.md's generator table. A profile missing here is a shape the
# architecture claims to support and does not.
EXPECTED = {
    "agentic-repo",
    "rust-lib",
    "rust-app",
    "rust-gui",
    "python-lib",
    "python-app",
    "go-lib",
    "go-app",
    "ts-lib",
    "ts-app",
    "ts-tui",
    "terraform",
    "cdk",
}


def profile_paths() -> list[Path]:
    return sorted(PROFILES.glob("*.yml"))


def load(path: Path) -> dict:
    return yaml.safe_load(path.read_text()) or {}


def ids(paths: list[Path]) -> list[str]:
    return [path.stem for path in paths]


@pytest.mark.parametrize("path", profile_paths(), ids=ids(profile_paths()))
def test_a_profile_parses_and_carries_every_key(path: Path) -> None:
    profile = load(path)
    for key in ("name", "summary", "generator", "layers", "build"):
        assert key in profile, f"no `{key}`"
    assert profile["name"] == path.stem
    assert profile["layers"], "an empty layer set renders nothing"
    assert profile["build"], "an empty build proves nothing"


@pytest.mark.parametrize("path", profile_paths(), ids=ids(profile_paths()))
def test_every_named_layer_exists(path: Path) -> None:
    """A profile names layers by path, so a renamed layer leaves it pointing at nothing."""
    for layer in load(path)["layers"]:
        assert (TEMPLATES / layer / "copier.yml").is_file(), f"{layer} has no copier.yml"


@pytest.mark.parametrize("path", profile_paths(), ids=ids(profile_paths()))
def test_the_order_respects_each_layer_declared_after(path: Path) -> None:
    """A layer's own `_scaffold.after` is the authority.

    This is what caught `lang/api` declaring `after: host/github` while the host layer
    declares `after: lang/*`, which is a cycle no profile could satisfy.
    """
    layers = load(path)["layers"]
    position = {layer: index for index, layer in enumerate(layers)}

    for layer in layers:
        config = yaml.safe_load((TEMPLATES / layer / "copier.yml").read_text()) or {}
        for pattern in (config.get("_scaffold") or {}).get("after") or []:
            for earlier in layers:
                if earlier == layer or not fnmatch.fnmatch(earlier, pattern):
                    continue
                assert position[earlier] < position[layer], (
                    f"{layer} renders before {earlier}, but declares `after: {pattern}`"
                )


@pytest.mark.parametrize("path", profile_paths(), ids=ids(profile_paths()))
def test_a_fragment_contributor_precedes_the_aggregator(path: Path) -> None:
    """`workspace/just` writes its import block from `.just.d/`, and `base/gitignore`
    rebuilds `.gitignore` from `.gitignore.d/`, so a contributor rendering afterwards leaves
    a generated file stale. rust-gui shipped with moon after just, and `just just-check`
    failed on the rendered tree.
    """
    layers = load(path)["layers"]
    position = {layer: index for index, layer in enumerate(layers)}

    for aggregator, directory in (
        ("workspace/just", ".just.d"),
        ("base/gitignore", ".gitignore.d"),
    ):
        if aggregator not in position:
            continue
        for layer in layers:
            if layer == aggregator:
                continue
            template = TEMPLATES / layer / "template"
            if not (template / directory).is_dir():
                continue
            assert position[layer] < position[aggregator], (
                f"{layer} contributes a {directory} fragment but renders after {aggregator}"
            )


@pytest.mark.parametrize("path", profile_paths(), ids=ids(profile_paths()))
def test_a_profile_owns_one_apm_yml(path: Path) -> None:
    """`agentic/apm` writes a consumer's manifest and `agentic/package` a publisher's, both
    at the same path, so a repository takes one."""
    layers = set(load(path)["layers"])
    assert not {"agentic/apm", "agentic/package"} <= layers


def test_every_architecture_shape_has_a_profile() -> None:
    """docs/architecture.md's generator table is the list, so a shape it names and this set
    omits is a shape the architecture claims and cannot render."""
    assert {path.stem for path in profile_paths()} == EXPECTED


def test_the_monorepo_axis_renders_the_root_manifest_first() -> None:
    """`cargo init .` writes a `[package]` root, after which workspace/monorepo skips the
    manifest it finds and no `[workspace]` section is ever written, so the repository
    silently is not a workspace."""
    for path in profile_paths():
        layers = load(path)["layers"]
        if "workspace/monorepo" not in layers:
            continue
        root = layers.index("workspace/monorepo")
        for index, layer in enumerate(layers):
            if layer.startswith("lang/"):
                assert index > root, f"{path.stem}: {layer} renders before the workspace root"


def test_the_validator_agrees(tmp_path: Path) -> None:
    """The script `just check` runs, against the committed set."""
    result = subprocess.run(
        [sys.executable, str(VALIDATOR)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_the_validator_rejects_an_unknown_layer(tmp_path: Path) -> None:
    """A validator that passes everything is not a validator, so the failure path is
    exercised rather than assumed."""
    broken = PROFILES / "zz-test-invalid.yml"
    broken.write_text(
        "name: zz-test-invalid\nsummary: probe\ngenerator: none\n"
        "layers:\n  - base/repo\n  - nope/missing\nbuild:\n  - true\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 1
        assert "nope/missing" in result.stderr
    finally:
        broken.unlink()


def test_the_validator_rejects_a_bad_order() -> None:
    broken = PROFILES / "zz-test-order.yml"
    # base/gitignore aggregates, and lang/rust contributes, so this order is wrong.
    broken.write_text(
        "name: zz-test-order\nsummary: probe\ngenerator: none\n"
        "layers:\n  - base/repo\n  - base/gitignore\n  - lang/rust\nbuild:\n  - true\n"
    )
    try:
        result = subprocess.run(
            [sys.executable, str(VALIDATOR)], capture_output=True, text=True, check=False
        )
        assert result.returncode == 1
        assert "base/gitignore" in result.stderr
    finally:
        broken.unlink()


def test_the_largest_shape_needs_no_language_layer() -> None:
    """agentic-repo covers 17 of 54 surveyed repositories and is the shape the old catalog
    had no name for: its product is skills and agents rather than code."""
    profile = load(PROFILES / "agentic-repo.yml")
    assert not any(layer.startswith("lang/") for layer in profile["layers"])
    assert "agentic/package" in profile["layers"]


def test_a_build_asserts_only_what_layers_produce() -> None:
    """render_profile.py does not run the generator, so a command needing generator output
    would fail for a missing manifest rather than for anything a layer got wrong."""
    forbidden = ("cargo build", "go build", "bun install", "uv sync", "npx projen")
    for path in profile_paths():
        for command in load(path)["build"]:
            for banned in forbidden:
                assert banned not in command, (
                    f"{path.stem}: `{command}` needs generator output, which the check "
                    "does not produce"
                )
