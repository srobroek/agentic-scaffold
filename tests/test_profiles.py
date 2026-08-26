"""profiles/: the recipe set per shape, and `scaffold check`, which keeps it honest.

The check is not decoration. It caught two real ordering bugs the unit tests could
not: `lang/api` declared `after: host/github` when every other language recipe renders
before the host, and `rust-gui` put `workspace/moon` after `workspace/just`, which left the
justfile's import block missing the moon fragment. The second surfaced only when a rendered
profile ran `just just-check`.

A profile still names its recipes under the key `layers`.
"""

from __future__ import annotations

import fnmatch
import os
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import load_scaffold, scaffold

REPO_ROOT = Path(__file__).resolve().parent.parent
PROFILES = REPO_ROOT / "profiles"
RECIPES = REPO_ROOT / "recipes"

# The REQUIRES table lives in the CLI and is validated against there. A copy here drifts.
CLI = load_scaffold()

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
        assert (RECIPES / layer / "copier.yml").is_file(), f"{layer} has no copier.yml"


@pytest.mark.parametrize("path", profile_paths(), ids=ids(profile_paths()))
def test_the_order_respects_each_layer_declared_after(path: Path) -> None:
    """A layer's own `_scaffold.after` is the authority.

    This is what caught `lang/api` declaring `after: host/github` while the host layer
    declares `after: lang/*`, which is a cycle no profile could satisfy.
    """
    layers = load(path)["layers"]
    position = {layer: index for index, layer in enumerate(layers)}

    for layer in layers:
        config = yaml.safe_load((RECIPES / layer / "copier.yml").read_text()) or {}
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
            template = RECIPES / layer / "template"
            if not (template / directory).is_dir():
                continue
            assert position[layer] < position[aggregator], (
                f"{layer} contributes a {directory} fragment but renders after {aggregator}"
            )


@pytest.mark.parametrize("path", profile_paths(), ids=ids(profile_paths()))
def test_a_layer_that_needs_another_gets_it(path: Path) -> None:
    """`after` orders two layers a profile already named, and says nothing about one being
    absent. docs/api-refs renders scripts under docs/site and generates pages the code repo
    has to push, so without docs/site it writes into a directory no build reads, and under
    docs/deploy-sibling the build runs where the extractors cannot."""
    layers = set(load(path)["layers"])
    for layer, needed in CLI.REQUIRES.items():
        if layer not in layers:
            continue
        assert set(needed) <= layers, f"{path.stem}: {layer} without {set(needed) - layers}"


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


def test_the_check_agrees() -> None:
    """What `just check` runs, against the committed set."""
    result = scaffold("check")
    assert result.returncode == 0, result.stdout + result.stderr


def check_against(directory: Path) -> subprocess.CompletedProcess[str]:
    """Run `scaffold check` with PROFILES pointed at a copy.

    The failure-path tests used to write a `zz-test-*.yml` into the real profiles/
    directory, which made them fail under `-n auto`: one worker saw another worker's
    fixture, and `test_a_build_asserts_only_what_layers_produce` read it as a real profile.
    A shared mutable directory is not a fixture.
    """
    return scaffold("check", env={**os.environ, "SCAFFOLD_PROFILES": str(directory)})


def copied_profiles(tmp_path: Path, extra: dict[str, str]) -> Path:
    directory = tmp_path / "profiles"
    directory.mkdir()
    for path in profile_paths():
        (directory / path.name).write_text(path.read_text())
    for name, body in extra.items():
        (directory / name).write_text(body)
    return directory


def test_the_check_rejects_an_unknown_layer(tmp_path: Path) -> None:
    """A check that passes everything is not a check, so the failure path is
    exercised rather than assumed."""
    directory = copied_profiles(
        tmp_path,
        {
            "zz-invalid.yml": "name: zz-invalid\nsummary: probe\ngenerator: none\n"
            "layers:\n  - base/repo\n  - nope/missing\nbuild:\n  - true\n"
        },
    )
    result = check_against(directory)
    assert result.returncode == 1
    assert "nope/missing" in result.stderr


def test_the_check_rejects_a_bad_order(tmp_path: Path) -> None:
    """base/gitignore aggregates .gitignore.d, and lang/rust contributes to it."""
    directory = copied_profiles(
        tmp_path,
        {
            "zz-order.yml": "name: zz-order\nsummary: probe\ngenerator: none\n"
            "layers:\n  - base/repo\n  - base/gitignore\n  - lang/rust\nbuild:\n  - true\n"
        },
    )
    result = check_against(directory)
    assert result.returncode == 1
    assert "base/gitignore" in result.stderr


def test_the_check_rejects_a_missing_requirement(tmp_path: Path) -> None:
    """No committed profile selects docs/api-refs yet, so the rule holds vacuously across the
    set and this is the only thing proving it fires at all."""
    directory = copied_profiles(
        tmp_path,
        {
            "zz-needs.yml": "name: zz-needs\nsummary: probe\ngenerator: none\n"
            "layers:\n  - base/repo\n  - docs/site\n  - docs/api-refs\nbuild:\n  - true\n"
        },
    )
    result = check_against(directory)
    assert result.returncode == 1
    assert "docs/deploy-split" in result.stderr


def test_the_check_rejects_two_recipes_in_one_exclusive_group(tmp_path: Path) -> None:
    """No committed profile names two recipes in one group, so the rule holds vacuously
    across the set. Two fixture recipes are what prove the declaration is load-bearing
    rather than a comment.

    The fixtures need their own `recipes/` and their own `profiles/`: the probe layers do
    not exist in the real tree, and the real profiles name nothing that exists in the probe
    tree, so pointing one override without the other reports unknown layers instead.
    """
    recipes = tmp_path / "recipes"
    for name in ("one", "two"):
        directory = recipes / "probe" / name
        (directory / "template").mkdir(parents=True)
        (directory / "copier.yml").write_text(
            "_subdirectory: template\n_scaffold:\n  summary: probe\n  exclusive_group: probe\n"
        )
    profiles = tmp_path / "profiles"
    profiles.mkdir()
    (profiles / "zz-both.yml").write_text(
        "name: zz-both\nsummary: probe\ngenerator: none\n"
        "layers:\n  - probe/one\n  - probe/two\nbuild:\n  - true\n"
    )

    result = scaffold(
        "check",
        env={
            **os.environ,
            "SCAFFOLD_PROFILES": str(profiles),
            "SCAFFOLD_RECIPES": str(recipes),
        },
    )

    assert result.returncode == 1
    assert "exclusive_group 'probe'" in result.stderr


def test_the_largest_shape_needs_no_language_layer() -> None:
    """agentic-repo covers 17 of 54 surveyed repositories and is the shape the old catalog
    had no name for: its product is skills and agents rather than code."""
    profile = load(PROFILES / "agentic-repo.yml")
    assert not any(layer.startswith("lang/") for layer in profile["layers"])
    assert "agentic/package" in profile["layers"]


def test_a_build_asserts_only_what_layers_produce() -> None:
    """`scaffold render --profile` does not run the generator, so a command needing generator
    output would fail for a missing manifest rather than for anything a layer got wrong."""
    forbidden = ("cargo build", "go build", "bun install", "uv sync", "npx projen")
    for path in profile_paths():
        for command in load(path)["build"]:
            for banned in forbidden:
                assert banned not in command, (
                    f"{path.stem}: `{command}` needs generator output, which the check "
                    "does not produce"
                )
