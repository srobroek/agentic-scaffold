"""agentic/package: the self-publishing marketplace repo.

Where a test needs apm it runs the real CLI against rendered output. Reading a
template proved nothing here either: `apm pack` builds the root catalogs but not the
per-package plugin manifests, `kiro` is a deploy target yet not a marketplace output,
the codex output refuses a package with no category, and `--check-clean` only gates
with `--dry-run`. Each of those rendered and read correctly.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

ANSWERS = """\
project_name: demo-market
package_name: demo-skill
description: A demo skill that demonstrates the agentic package scaffold.
author: Sjors Robroek
owner: srobroek
category: productivity
package_tags: [skill]
marketplace_outputs: claude,codex
deploy_kiro: true
"""

CLAUDE_ONLY = """\
project_name: solo-market
package_name: solo-skill
description: A claude-only package.
author: Sjors Robroek
owner: srobroek
category: workflow
package_tags: [skill]
marketplace_outputs: claude
deploy_kiro: false
"""

needs_apm = pytest.mark.skipif(shutil.which("apm") is None, reason="apm absent from PATH")
needs_just = pytest.mark.skipif(shutil.which("just") is None, reason="just absent from PATH")


def render(layer: str, dest: Path, answers: str = "") -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(RENDER), layer, str(dest)]
    if answers:
        answers_file = dest.parent / f"{dest.name}-{layer.replace('/', '-')}.yml"
        answers_file.write_text(answers)
        argv += ["--answers", str(answers_file)]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def git_repo(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for key, value in (("user.email", "t@e.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(path), "config", key, value], check=True)


def commit(path: Path, message: str = "wip") -> None:
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", message],
        check=False,
        capture_output=True,
    )


def apm(dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["apm", *args], cwd=dest, capture_output=True, text=True, check=False)


@pytest.fixture
def package(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    git_repo(dest)
    result = render("agentic/package", dest, ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


@pytest.fixture
def claude_only(tmp_path: Path) -> Path:
    dest = tmp_path / "claude"
    dest.mkdir()
    git_repo(dest)
    result = render("agentic/package", dest, CLAUDE_ONLY)
    assert result.returncode == 0, result.stderr
    return dest


# --- structure -------------------------------------------------------------


def test_the_root_manifest_is_a_publisher_not_a_consumer(package: Path) -> None:
    """A marketplace block, not a dependencies block. This is what distinguishes it
    from agentic/apm, which writes the same filename for a package consumer."""
    manifest = yaml.safe_load((package / "apm.yml").read_text())
    assert "marketplace" in manifest
    assert "dependencies" not in manifest
    assert manifest["marketplace"]["packages"][0]["source"] == "./packages/demo-skill"


def test_the_package_carries_its_own_manifest_and_skill(package: Path) -> None:
    """Each package needs an apm.yml, or apm pack --check-versions reports no_apm_yml."""
    pkg = package / "packages" / "demo-skill"
    assert (pkg / "apm.yml").is_file()
    skill = pkg / ".apm" / "skills" / "demo-skill" / "SKILL.md"
    assert skill.is_file()
    front = skill.read_text().split("---")[1]
    assert "name: demo-skill" in front


def test_the_per_package_plugin_manifests_are_committed(package: Path) -> None:
    """apm pack writes only the root catalogs, never these.

    Claude's /plugin install reads the per-package manifest at the catalog's source:
    path, so without it a package lists but does not install. Verified against apm
    0.26.0, where apm pack left these absent.
    """
    pkg = package / "packages" / "demo-skill"
    claude = json.loads((pkg / ".claude-plugin" / "plugin.json").read_text())
    assert claude["name"] == "demo-skill"
    assert claude["skills"] == "./.apm/skills"

    codex = json.loads((pkg / ".codex-plugin" / "plugin.json").read_text())
    assert codex["name"] == "demo-skill"


def test_the_tag_pattern_matches_release_please(package: Path) -> None:
    """The marketplace resolves versions against whatever release-please tags.

    include-component-in-tag + tag-separator "--" tag <component>--v<version>, so the
    marketplace tagPattern is '{name}--v{version}'. A mismatch is caught by neither
    apm gate, so the two configs are asserted to agree here.
    """
    rp = json.loads((package / "release-please-config.json").read_text())
    assert rp["include-component-in-tag"] is True
    assert rp["tag-separator"] == "--"

    manifest = yaml.safe_load((package / "apm.yml").read_text())
    assert manifest["marketplace"]["build"]["tagPattern"] == "{name}--v{version}"


def test_the_versions_start_aligned(package: Path) -> None:
    """apm.yml, the package apm.yml, and the release-please manifest all say 0.1.0."""
    root = yaml.safe_load((package / "apm.yml").read_text())
    pkg = yaml.safe_load((package / "packages" / "demo-skill" / "apm.yml").read_text())
    rp_manifest = json.loads((package / ".release-please-manifest.json").read_text())
    assert root["version"] == "0.1.0"
    assert pkg["version"] == "0.1.0"
    assert rp_manifest["packages/demo-skill"] == "0.1.0"


# --- kiro is a target, not an output ---------------------------------------


def test_kiro_is_a_deploy_target_but_not_a_marketplace_output(package: Path) -> None:
    """The two axes the layer exists to keep separate.

    apm 0.26.0 registers only claude and codex marketplace mappers
    (apm_cli/marketplace/output_profiles.py), so `kiro:` under outputs is a hard
    error. It is a valid `apm targets` deploy destination, so the skill still reaches
    Kiro users.
    """
    manifest = yaml.safe_load((package / "apm.yml").read_text())
    assert "kiro" in manifest["targets"], "kiro must be a deploy target"
    assert "kiro" not in manifest["marketplace"]["outputs"], (
        "kiro has no marketplace mapper; apm rejects it under outputs"
    )
    assert set(manifest["marketplace"]["outputs"]) <= {"claude", "codex"}


def test_deploy_kiro_false_drops_the_kiro_target(claude_only: Path) -> None:
    manifest = yaml.safe_load((claude_only / "apm.yml").read_text())
    assert "kiro" not in manifest["targets"]


def test_claude_only_omits_codex_everywhere(claude_only: Path) -> None:
    """No codex output, no codex target, and no empty .codex-plugin directory."""
    manifest = yaml.safe_load((claude_only / "apm.yml").read_text())
    assert list(manifest["marketplace"]["outputs"]) == ["claude"]
    assert "codex" not in manifest["targets"]
    assert not (claude_only / "packages" / "solo-skill" / ".codex-plugin").exists(), (
        "the codex manifest directory should not render for a claude-only marketplace"
    )


def test_category_is_a_required_choice(package: Path) -> None:
    """The codex output refuses a package with no category, so it is asked rather than
    left free-text. Both the marketplace entry and the package apm.yml carry it."""
    manifest = yaml.safe_load((package / "apm.yml").read_text())
    assert manifest["marketplace"]["packages"][0]["category"] == "productivity"
    pkg = yaml.safe_load((package / "packages" / "demo-skill" / "apm.yml").read_text())
    assert pkg["category"] == "productivity"


# --- the real tool ---------------------------------------------------------


@needs_apm
def test_apm_pack_builds_both_catalogs(package: Path) -> None:
    commit(package)
    result = apm(package, "pack", "--offline")
    assert result.returncode == 0, result.stdout + result.stderr

    claude = json.loads((package / ".claude-plugin" / "marketplace.json").read_text())
    assert claude["plugins"][0]["source"] == "./packages/demo-skill"
    assert claude["plugins"][0]["category"] == "productivity"

    codex = json.loads((package / ".agents" / "plugins" / "marketplace.json").read_text())
    # Codex nests the source under a local descriptor rather than a bare string.
    assert codex["plugins"][0]["source"]["path"] == "./packages/demo-skill"


@needs_apm
def test_apm_pack_builds_only_claude_when_codex_is_off(claude_only: Path) -> None:
    commit(claude_only)
    result = apm(claude_only, "pack", "--offline")
    assert result.returncode == 0, result.stdout + result.stderr
    assert (claude_only / ".claude-plugin" / "marketplace.json").is_file()
    assert not (claude_only / ".agents" / "plugins" / "marketplace.json").exists()


@needs_apm
def test_version_alignment_passes_on_the_rendered_repo(package: Path) -> None:
    """--check-versions confirms every version renders under the tag pattern, and no
    package reports no_apm_yml."""
    commit(package)
    result = apm(package, "pack", "--offline", "--check-versions", "--dry-run")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no_apm_yml" not in (result.stdout + result.stderr)
    assert "demo-skill--v0.1.0" in result.stdout


@needs_apm
def test_check_clean_needs_dry_run_to_gate(package: Path) -> None:
    """The trap the recipe encodes.

    On a clean tree the gate passes. Dirtied, `--check-clean --dry-run` exits 4 and
    leaves the file untouched, while `--check-clean` alone regenerates the file first
    and so passes on the very drift it should catch. Verified against apm 0.26.0.
    """
    commit(package)
    assert apm(package, "pack", "--offline").returncode == 0
    commit(package, "generated")

    clean = apm(package, "pack", "--offline", "--check-clean", "--dry-run")
    assert clean.returncode == 0, clean.stdout + clean.stderr

    catalog = package / ".claude-plugin" / "marketplace.json"
    data = json.loads(catalog.read_text())
    data["plugins"][0]["category"] = "TAMPERED"
    catalog.write_text(json.dumps(data, indent=2))

    gated = apm(package, "pack", "--offline", "--check-clean", "--dry-run")
    assert gated.returncode == 4, "the --dry-run gate must fail on drift"
    assert "TAMPERED" in catalog.read_text(), "the gate must not rewrite the file it checks"

    ungated = apm(package, "pack", "--offline", "--check-clean")
    assert ungated.returncode == 0, "without --dry-run the run regenerates and passes"
    assert "TAMPERED" not in catalog.read_text(), "the ungated run overwrote the drift"


# --- fragments and recipes -------------------------------------------------


def test_the_gitignore_fragment_keeps_the_catalogs_but_drops_the_build(package: Path) -> None:
    """apm_modules/ and build/ are artefacts; the committed catalogs are not."""
    fragment = (package / ".gitignore.d" / "package").read_text()
    patterns = [
        line.strip()
        for line in fragment.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert "apm_modules/" in patterns
    assert "build/" in patterns
    # The committed catalogs must not be ignored; comments may mention them.
    assert not any("marketplace.json" in p for p in patterns)


@needs_just
def test_the_recipes_render_with_the_pinned_cli(package: Path) -> None:
    """The `:=` line interpolates the CLI version; the recipe bodies stay raw."""
    render("workspace/just", package)
    fragment = (package / ".just.d" / "package.just").read_text()
    assert "apm-cli@0.26.0" in fragment

    listing = subprocess.run(
        ["just", "--list"], cwd=package, capture_output=True, text=True, check=False
    )
    assert listing.returncode == 0, listing.stderr
    for recipe in ("package-build", "package-check", "package-versions"):
        assert recipe in listing.stdout


def test_the_check_recipe_cannot_repair_what_it_checks(package: Path) -> None:
    """`--check-clean` without `--dry-run` regenerates before diffing, so it overwrites the
    drift it is meant to catch and always passes. Verified against apm 0.26.0: exit 4 with
    the flag on a hand-edited catalog, exit 0 and a silently repaired file without it.
    """
    render("workspace/just", package)
    fragment = (package / ".just.d" / "package.just").read_text()
    for line in fragment.splitlines():
        stripped = line.strip()
        if "--check-clean" in stripped and not stripped.startswith("#"):
            assert "--dry-run" in stripped, f"the gate can repair what it checks: {stripped!r}"


def test_no_catalog_is_written_at_render_time(package: Path) -> None:
    """The catalogs are committed, but `apm pack` needs uvx and may reach the network, so it
    cannot be a copier task. A fresh render therefore has none, and `just package-build`
    produces them.
    """
    assert not (package / ".claude-plugin" / "marketplace.json").exists()
    assert not (package / ".agents" / "plugins" / "marketplace.json").exists()


def test_the_catalogs_are_not_gitignored(package: Path) -> None:
    """They are committed generated artefacts, which is what lets a consumer resolve the
    marketplace from a clone with no build step. agentic-packages and break-stuff both
    track them."""
    fragment = (package / ".gitignore.d" / "package").read_text()
    patterns = [
        line.strip() for line in fragment.splitlines() if line.strip() and not line.startswith("#")
    ]
    assert not any("marketplace.json" in p for p in patterns)
    assert not any(p.startswith(".claude-plugin") for p in patterns)
    # The archive directory is the throwaway part.
    assert "build/" in patterns


@needs_just
def test_every_recipe_has_a_real_description(package: Path) -> None:
    """`just` reads the comment above a recipe as its description, so a stray line of
    rationale becomes one. Three shipped fragments had this before it was caught."""
    render("workspace/just", package)
    listing = subprocess.run(
        ["just", "--list"], cwd=package, capture_output=True, text=True, check=False
    )
    for line in listing.stdout.splitlines():
        if not line.startswith("    ") or "#" not in line:
            continue
        name, _, description = line.strip().partition("#")
        if not name.strip().startswith("marketplace") and name.strip() != "package":
            continue
        text = description.strip()
        assert text and text[0].isupper(), (
            f"{name.strip()!r} description looks like prose: {text!r}"
        )


# --- integration -----------------------------------------------------------


def test_the_fragments_reach_the_aggregating_layers(tmp_path: Path) -> None:
    dest = tmp_path / "agg"
    dest.mkdir()
    git_repo(dest)
    assert render("agentic/package", dest, ANSWERS).returncode == 0
    assert render("workspace/just", dest).returncode == 0
    assert render("base/gitignore", dest).returncode == 0

    assert "import? '.just.d/package.just'" in (dest / "justfile").read_text()
    gitignore = (dest / ".gitignore").read_text()
    assert "apm_modules/" in gitignore
    assert "build/" in gitignore


def test_the_catalog_drift_check_reaches_ci(tmp_path: Path) -> None:
    """The layer ships `package-check` and `package-versions`, and something has to run them.

    Without this the recipes exist and never fire: the catalogs are committed generated
    artefacts, so a package added to apm.yml without a repack leaves them behind and a consumer
    resolving the marketplace from a clone never sees it. The scaffold's own repository shipped
    exactly that hole.

    The host layer's `Generated files current` step is where it belongs, beside `just-check`
    and `gitlab-check`: same class of failure, a generated file that a fragment change made
    stale.
    """
    workflow = (
        REPO_ROOT
        / "templates"
        / "host"
        / "github"
        / "template"
        / ".github"
        / "workflows"
        / "wc-quality.yml.jinja"
    ).read_text()

    assert "just package-check" in workflow
    assert "just package-versions" in workflow
    # Guarded, since a repository without agentic/package has no apm.yml to pack.
    assert "grep -q 'marketplace:' apm.yml" in workflow
    # `--dry-run` lives in the recipe, and the reason is recorded where the guard is.
    assert "load-bearing" in workflow
