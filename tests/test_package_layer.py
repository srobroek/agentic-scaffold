"""agentic/package: the native marketplace repo.

Nothing here reads a template and calls it proved. The catalogs are written at render
time by the generator the layer ships, so the tests run that generator: `--check`
against the committed bytes, a second run for byte-identity, a hand-added plugin, and
the failures that stay silent at install time otherwise -- a capability name no plugin
prefix owns, and a manifest naming something its directory does not.

Where `just` is present the recipes run for real, because the gate a CI workflow calls
has to exist under the name the workflow uses.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
from conftest import render_recipe as render

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPE = REPO_ROOT / "recipes" / "agentic" / "package"

ANSWERS = """\
project_name: demo-market
package_name: demo-skill
description: A demo skill that demonstrates the native marketplace scaffold.
author: Sjors Robroek
owner: srobroek
"""

CATALOGS = (
    ".omp-plugin/marketplace.json",
    ".claude-plugin/marketplace.json",
    ".agents/plugins/marketplace.json",
)

needs_just = pytest.mark.skipif(shutil.which("just") is None, reason="just absent from PATH")


def git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for key, value in (("user.email", "t@e.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(path), "config", key, value], check=True)


def catalog(dest: Path, which: str = CATALOGS[0]) -> dict:
    return json.loads((dest / which).read_text())


def generator(dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    """The shipped generator, run the way `just marketplace-build` runs it."""
    return subprocess.run(
        [sys.executable, "scripts/build_catalog.py", ".", *args],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )


def add_plugin(dest: Path, name: str, **fields: object) -> Path:
    """A plugin added by hand, which is how the repository grows past its starter."""
    plugin = dest / name
    manifest = {"name": name, "description": f"The {name} plugin.", "version": "0.2.0", **fields}
    # Both manifests, like the starter: Claude installs from .claude-plugin's, and the
    # generator refuses a plugin missing it or disagreeing on the version.
    for owner in (".omp-plugin", ".claude-plugin"):
        (plugin / owner).mkdir(parents=True)
        (plugin / owner / "plugin.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return plugin


def add_capability(plugin: Path, kind: str, name: str) -> Path:
    """One capability file, at the path OMP locates it by."""
    if kind == "skills":
        path = plugin / "skills" / name / "SKILL.md"
    else:
        path = plugin / kind / f"{name}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: A capability.\n---\n\nBody.\n")
    return path


@pytest.fixture
def package(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    git_repo(dest)
    result = render("agentic/package", dest, ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


# --- one source, two catalogs ----------------------------------------------


def test_the_repository_serves_omp_and_claude_from_one_source(package: Path) -> None:
    """OMP reads `.omp-plugin/marketplace.json` and falls back to `.claude-plugin/`, so the
    same bytes at both paths make one repository serve both runtimes. Byte equality rather
    than equal payloads: the generator writes one string twice, and a difference would mean
    two writers."""
    first, *rest = (package / name for name in CATALOGS)
    for other in rest:
        assert first.read_bytes() == other.read_bytes(), other
    assert catalog(package)["name"] == "demo-market"
    assert catalog(package)["owner"] == {"name": "Sjors Robroek"}
    assert "native marketplace scaffold" in catalog(package)["metadata"]["description"]


def test_the_catalog_entry_resolves_to_the_plugin_directory(package: Path) -> None:
    """OMP locates every capability under the entry's `source`, so an entry whose source is
    not a directory in the repository lists a plugin that cannot install."""
    entries = catalog(package)["plugins"]
    assert len(entries) == 1
    assert entries[0]["name"] == "demo-skill"
    assert entries[0]["source"] == "./demo-skill"
    assert (package / "demo-skill").is_dir()


def test_the_catalog_carries_the_version_omp_compares(package: Path) -> None:
    """OMP compares `plugins[].version` in the top-level catalog when it decides whether an
    installed plugin can be upgraded, and an entry with no version is invisible to that
    comparer. The plugin owns the number; the catalog repeats it."""
    manifest = json.loads((package / "demo-skill" / ".omp-plugin" / "plugin.json").read_text())
    assert manifest["version"] == "0.1.0"
    assert catalog(package)["plugins"][0]["version"] == manifest["version"]
    assert manifest["name"] == "demo-skill"


# --- the plugin ------------------------------------------------------------


def test_the_plugin_carries_the_omp_recognition_marker(package: Path) -> None:
    """Recognition comes from a package.json holding an `omp` key. Without it `omp plugin
    doctor` reports "not an omp plugin" and the plugin's rules and agents are silently absent
    while its skills still load, which is the loudest failure this file can prevent."""
    payload = json.loads((package / "demo-skill" / "package.json").read_text())
    assert "omp" in payload
    assert payload["name"] == "@srobroek/demo-skill"
    assert payload["private"] is True


def test_the_starter_skill_lands_where_omp_looks(package: Path) -> None:
    """`skills/<name>/SKILL.md`, located without recursion: a skill one level deeper is not
    found, and a catalog entry cannot redirect the lookup."""
    skill = package / "demo-skill" / "skills" / "demo-skill" / "SKILL.md"
    front = skill.read_text().split("---")[1]
    assert "name: demo-skill" in front
    assert "description: A demo skill" in front


def test_nothing_apm_shaped_survives() -> None:
    """The layer published through apm until this rewrite. apm's manifest, its kiro deploy
    target, and the `tagPattern` its marketplace resolved versions against are all gone, and
    a leftover would be a path the native runtimes never read."""
    for path in sorted(RECIPE.rglob("*")):
        if not path.is_file():
            continue
        text = f"{path.relative_to(RECIPE)}\n{path.read_text()}"
        for dead in ("apm", "kiro", "tagPattern", "codex-plugin"):
            assert dead not in text, f"{path.name} still mentions {dead}"


def test_the_layer_leaves_release_please_alone(package: Path) -> None:
    """release/release-please owns both of its files. Two layers writing one config is how a
    re-render silently reset a released version, so this one writes neither."""
    assert not (package / "release-please-config.json").exists()
    assert not (package / ".release-please-manifest.json").exists()


# --- the generator ---------------------------------------------------------


def test_the_render_leaves_the_gate_passing(package: Path) -> None:
    """The catalogs are committed generated artefacts, so a render that produced none would
    ship a marketplace nobody can resolve from a clone, and the profile build's
    `just marketplace-check` would fail on the first render."""
    result = generator(package, "--check")
    assert result.returncode == 0, result.stderr
    assert "match 1 plugin manifest" in result.stdout


def test_a_second_run_is_byte_identical(package: Path) -> None:
    """A generator that iterates a hash map or stamps a time makes every commit carry a
    reference diff, which makes the staleness check meaningless."""
    before = [(package / name).read_bytes() for name in CATALOGS]
    assert generator(package).returncode == 0
    assert [(package / name).read_bytes() for name in CATALOGS] == before


def test_the_check_reports_drift_and_repairs_nothing(package: Path) -> None:
    """A gate that regenerates before diffing overwrites the drift it exists to report, and
    then always passes. `--check` writes nothing, so the tampering survives the run and CI
    is left with a clean tree."""
    stale = package / CATALOGS[0]
    stale.write_text(stale.read_text().replace('"0.1.0"', '"9.9.9"'))

    result = generator(package, "--check")
    assert result.returncode == 1
    assert "stale catalog" in result.stderr
    assert "9.9.9" in stale.read_text(), "the check repaired what it was checking"


def test_a_missing_catalog_counts_as_stale(package: Path) -> None:
    """Both paths are the contract: dropping the Claude copy leaves Claude Code with no
    catalog while OMP still resolves, so the failure would be invisible from OMP."""
    (package / CATALOGS[1]).unlink()
    result = generator(package, "--check")
    assert result.returncode == 1
    assert CATALOGS[1] in result.stderr


def test_the_generator_needs_no_argument(package: Path) -> None:
    """`just marketplace-build` passes `.`, but a person types the script path. The default
    is the parent of scripts/, so the run does not depend on the working directory."""
    result = subprocess.run(
        [sys.executable, str(package / "scripts" / "build_catalog.py"), "--check"],
        cwd=package.parent,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


# --- growing past the starter ---------------------------------------------


def test_a_plugin_added_by_hand_reaches_both_catalogs(package: Path) -> None:
    """The starter is one plugin; a marketplace is many. Adding a manifest is the whole
    registration step, and `category` passes through when a plugin declares one."""
    add_plugin(package, "extra", category="productivity")
    add_capability(package / "extra", "skills", "extra")

    assert generator(package).returncode == 0
    entries = catalog(package)["plugins"]
    assert [entry["name"] for entry in entries] == ["demo-skill", "extra"]
    assert entries[1]["category"] == "productivity"
    assert entries[1]["version"] == "0.2.0"
    assert (package / CATALOGS[0]).read_bytes() == (package / CATALOGS[1]).read_bytes()
    assert (package / CATALOGS[0]).read_bytes() == (package / CATALOGS[2]).read_bytes()


def test_an_unprefixed_capability_is_refused(package: Path) -> None:
    """OMP identifies a capability by its bare name, deduplicates across every configured
    source, and keeps the first match, so a name two plugins share resolves to one and hides
    the other with nothing said at load time. The owning plugin's name as a prefix is what
    keeps them apart, and the generator is where that gets enforced."""
    rule = add_capability(package / "demo-skill", "rules", "quality")
    result = generator(package, "--check")
    assert result.returncode == 1
    assert "not prefixed" in result.stderr

    rule.rename(rule.with_name("demo-skill-quality.md"))
    assert generator(package, "--check").returncode == 0


def test_a_manifest_naming_something_other_than_its_directory_is_refused(package: Path) -> None:
    """`source` is the directory. A manifest naming something else publishes an entry that
    resolves to nothing, and both readings of the disagreement are plausible, so it is
    reported rather than picked."""
    manifest = package / "demo-skill" / ".omp-plugin" / "plugin.json"
    payload = json.loads(manifest.read_text())
    payload["name"] = "elsewhere"
    manifest.write_text(json.dumps(payload, indent=2) + "\n")

    result = generator(package, "--check")
    assert result.returncode == 1
    assert "resolves `source` by directory" in result.stderr


def test_a_manifest_missing_a_field_writes_no_catalog(package: Path) -> None:
    """An entry with no version is invisible to OMP's upgrade comparer, so a manifest that
    cannot produce one stops the build instead of publishing a half entry."""
    manifest = package / "demo-skill" / ".omp-plugin" / "plugin.json"
    payload = json.loads(manifest.read_text())
    del payload["version"]
    manifest.write_text(json.dumps(payload, indent=2) + "\n")
    before = (package / CATALOGS[0]).read_bytes()

    result = generator(package)
    assert result.returncode == 1
    assert "has no version" in result.stderr
    assert (package / CATALOGS[0]).read_bytes() == before


# --- re-render -------------------------------------------------------------


def test_a_re_render_keeps_the_written_plugin_and_syncs_the_catalogs(package: Path) -> None:
    """The skill body and both manifests are the project's once written: a re-render that
    reset a released version or a real skill body would make the layer unusable after the
    first commit. The catalogs are not the project's, so the re-render regenerates them and
    a version bumped by hand reaches them."""
    skill = package / "demo-skill" / "skills" / "demo-skill" / "SKILL.md"
    skill.write_text("---\nname: demo-skill\ndescription: Hand written.\n---\n\nReal body.\n")
    # A release bumps BOTH manifests -- the generator refuses a pair that
    # disagrees, since Claude reads one and OMP the other.
    for owner in (".omp-plugin", ".claude-plugin"):
        manifest = package / "demo-skill" / owner / "plugin.json"
        payload = json.loads(manifest.read_text())
        payload["version"] = "1.4.0"
        manifest.write_text(json.dumps(payload, indent=2) + "\n")

    assert render("agentic/package", package, ANSWERS).returncode == 0

    assert "Real body." in skill.read_text()
    omp_manifest = package / "demo-skill" / ".omp-plugin" / "plugin.json"
    assert json.loads(omp_manifest.read_text())["version"] == "1.4.0"
    assert catalog(package)["plugins"][0]["version"] == "1.4.0"


# --- fragments and recipes -------------------------------------------------


def test_the_fragments_reach_the_aggregating_layers(tmp_path: Path) -> None:
    dest = tmp_path / "agg"
    dest.mkdir()
    git_repo(dest)
    assert render("agentic/package", dest, ANSWERS).returncode == 0
    assert render("workspace/just", dest).returncode == 0
    assert render("base/gitignore", dest).returncode == 0

    assert "import? '.just.d/package.just'" in (dest / "justfile").read_text()
    gitignore = (dest / ".gitignore").read_text()
    # Install state a local marketplace test leaves behind, not the catalogs: those are
    # committed, which is what lets an install resolve from a clone.
    assert "installed_plugins.json" in gitignore
    assert "node_modules/" in gitignore
    assert "marketplace.json" not in gitignore


@needs_just
def test_the_recipes_run_the_generator(package: Path) -> None:
    """The names a CI workflow and the profile build call. `just --list` alone would pass
    against a recipe whose body is broken, so the check runs."""
    assert render("workspace/just", package).returncode == 0
    listing = subprocess.run(
        ["just", "--list"], cwd=package, capture_output=True, text=True, check=False
    )
    assert listing.returncode == 0, listing.stderr
    for recipe in ("marketplace-build", "marketplace-check"):
        assert recipe in listing.stdout

    result = subprocess.run(
        ["just", "marketplace-check"], cwd=package, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr


@needs_just
def test_every_recipe_has_a_real_description(package: Path) -> None:
    """`just` reads the comment above a recipe as its description, so a stray line of
    rationale becomes one. Three shipped fragments had this before it was caught."""
    assert render("workspace/just", package).returncode == 0
    listing = subprocess.run(
        ["just", "--list"], cwd=package, capture_output=True, text=True, check=False
    )
    for line in listing.stdout.splitlines():
        if not line.startswith("    ") or "#" not in line:
            continue
        name, _, description = line.strip().partition("#")
        if not name.strip().startswith("marketplace"):
            continue
        text = description.strip()
        assert text and text[0].isupper(), (
            f"{name.strip()!r} description looks like prose: {text!r}"
        )


def test_the_drift_check_reaches_ci() -> None:
    """A gate nothing runs is a gate that never fires: a plugin added or a version bumped
    without a rebuild leaves the catalogs behind, and an install resolving from a clone never
    sees it. The host layer's `Generated files current` step is where it belongs, beside
    `just-check` and `gitlab-check` -- same class of failure, a generated file a change made
    stale."""
    workflow = (
        REPO_ROOT / "recipes/host/github/template/.github/workflows/wc-quality.yml.jinja"
    ).read_text()

    assert "just marketplace-check" in workflow
    # Guarded on the generator, since a repository without agentic/package has no catalogs.
    assert "if [ -f scripts/build_catalog.py ]" in workflow


def test_a_plugin_without_a_claude_manifest_is_refused(package: Path) -> None:
    """Claude installs from the per-plugin .claude-plugin/plugin.json at the entry's
    source path: without one the plugin lists in the marketplace and then fails to
    install, which is worse than not listing."""
    (package / "demo-skill" / ".claude-plugin" / "plugin.json").unlink()

    result = generator(package)

    assert result.returncode == 1
    assert "no .claude-plugin/plugin.json" in result.stderr


def test_disagreeing_manifest_versions_are_refused(package: Path) -> None:
    """One version per plugin: a manifest pair that disagrees makes the upgrade check
    lie to one runtime or the other."""
    claude = package / "demo-skill" / ".claude-plugin" / "plugin.json"
    claude.write_text(claude.read_text().replace('"0.1.0"', '"0.9.9"'))

    result = generator(package)

    assert result.returncode == 1
    assert "disagree on the version" in result.stderr
