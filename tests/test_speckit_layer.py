"""agentic/speckit: declares speckit-conductor and fixes what its setup script cannot.

The package does the scaffolding, so the layer is thin. It exists for three things the
package cannot do from inside an installed skill:

- the setup script appends `specs/**/spec-status.md` to the ROOT .gitignore, which
  base/gitignore rebuilds from .gitignore.d/, so the entry is dropped on the next render
- apm.yml belongs to agentic/apm and carries a _skip_if_exists, so the locator has to be
  added by an idempotent edit rather than by rendering the file
- the script hardcodes twelve extensions and exits 0 when one could not be installed: a
  custom-source failure warns on stderr and continues, so `agent-assign` can be absent
  while setup reports success, and the DAG hard-blocks /speckit.implement without it
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

SPECKIT = "speckit_integration: claude\nspeckit_script_flavor: sh\n"
APM_WITH_PACKAGE = """\
project_name: demo
description: A demo project
apm_packages:
  - "srobroek/agentic-packages/packages/core#>=1.0.0 <2.0.0"
apm_target: "claude,codex"
apm_cli_version: "0.26.0"
"""
APM_EMPTY = """\
project_name: demo
description: A demo project
apm_packages: []
apm_target: "claude,codex"
apm_cli_version: "0.26.0"
"""

JUST = Path.home() / ".local/share/mise/installs/just/latest/just"
needs_just = pytest.mark.skipif(
    not JUST.is_file() and shutil.which("just") is None, reason="just absent"
)


def just_bin() -> str:
    return str(JUST) if JUST.is_file() else "just"


def render(layer: str, dest: Path, answers: str = "") -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(RENDER), layer, str(dest)]
    if answers:
        answers_file = dest.parent / f"{dest.name}-{layer.replace('/', '-')}.yml"
        answers_file.write_text(answers)
        argv += ["--answers", str(answers_file)]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


@pytest.fixture
def speckit(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render("agentic/speckit", dest, SPECKIT)
    assert result.returncode == 0, result.stderr
    return dest


# --- one locator, not three ------------------------------------------------


def test_a_single_locator_is_declared(tmp_path: Path) -> None:
    """`speckit`, `speckit-beads`, and `steering-speckit` were merged upstream and
    extracted to srobroek/speckit-conductor, so the layer names one dependency."""
    dest = tmp_path / "one"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("agentic/apm", dest, APM_EMPTY).returncode == 0
    assert render("agentic/speckit", dest, SPECKIT).returncode == 0

    manifest = yaml.safe_load((dest / "apm.yml").read_text())
    locators = manifest["dependencies"]["apm"]
    assert len(locators) == 1
    assert locators[0].startswith("srobroek/speckit-conductor")
    for retired in ("packages/speckit#", "speckit-beads", "steering-speckit"):
        assert not any(retired in locator for locator in locators)


def test_the_locator_is_pinned(speckit: Path) -> None:
    """apm warns on an unpinned dependency, and an unpinned formula can change the phase
    DAG under a running feature."""
    answers = yaml.safe_load((speckit / ".copier-answers.speckit.yml").read_text())
    assert "#" in answers["speckit_locator"], "the locator carries no version constraint"


def test_an_existing_package_list_is_preserved(tmp_path: Path) -> None:
    """apm.yml belongs to agentic/apm and is skip-guarded, so a package added by hand must
    survive the edit."""
    dest = tmp_path / "keep"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("agentic/apm", dest, APM_WITH_PACKAGE).returncode == 0
    assert render("agentic/speckit", dest, SPECKIT).returncode == 0

    locators = yaml.safe_load((dest / "apm.yml").read_text())["dependencies"]["apm"]
    assert any("packages/core" in locator for locator in locators)
    assert any("speckit-conductor" in locator for locator in locators)


def test_the_empty_list_placeholder_is_replaced(tmp_path: Path) -> None:
    """agentic/apm writes `[]` for an empty list, and a list cannot hold both that and an
    entry."""
    dest = tmp_path / "empty"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("agentic/apm", dest, APM_EMPTY).returncode == 0
    assert render("agentic/speckit", dest, SPECKIT).returncode == 0

    body = (dest / "apm.yml").read_text()
    assert "[]" not in body
    # Still valid YAML with exactly the one entry.
    assert len(yaml.safe_load(body)["dependencies"]["apm"]) == 1


def test_adding_the_locator_is_idempotent(tmp_path: Path) -> None:
    dest = tmp_path / "twice"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("agentic/apm", dest, APM_EMPTY).returncode == 0
    assert render("agentic/speckit", dest, SPECKIT).returncode == 0
    second = render("agentic/speckit", dest, SPECKIT)
    assert second.returncode == 0
    assert "already in apm.yml" in second.stdout

    assert len(yaml.safe_load((dest / "apm.yml").read_text())["dependencies"]["apm"]) == 1


def test_a_missing_apm_yml_is_reported_rather_than_written(speckit: Path) -> None:
    """agentic/apm may not have rendered, and writing a manifest this layer does not own
    would be worse than saying so."""
    assert not (speckit / "apm.yml").exists()
    result = render("agentic/speckit", speckit, SPECKIT)
    assert result.returncode == 0
    assert "no apm.yml" in result.stdout


# --- the gitignore conflict ------------------------------------------------


def test_the_status_artefact_is_carried_as_a_fragment(speckit: Path) -> None:
    """The setup script appends this to the root .gitignore, which base/gitignore rebuilds
    from .gitignore.d/, so an appended line is dropped on the next render."""
    fragment = (speckit / ".gitignore.d" / "speckit").read_text()
    assert "specs/**/spec-status.md" in fragment


def test_the_entry_survives_a_gitignore_rebuild(speckit: Path) -> None:
    """The end-to-end case the fragment exists for."""
    assert render("base/gitignore", speckit, 'gitnr_templates: ""\n').returncode == 0
    assert "specs/**/spec-status.md" in (speckit / ".gitignore").read_text()


# --- the extension set -----------------------------------------------------


def test_the_layer_verifies_what_actually_installed(speckit: Path) -> None:
    """The script exits 0 when a custom-source extension could not be installed: the
    failure warns on stderr and `continue`s. agent-assign is the one that matters, because
    the DAG hard-blocks /speckit.implement without it.
    """
    fragment = (speckit / ".just.d" / "speckit.just").read_text()
    assert "speckit-verify-extensions" in fragment
    # All twelve, or the check passes while the set is incomplete.
    for extension in (
        "agent-assign",
        "cleanup",
        "critique",
        "fix-findings",
        "iterate",
        "qa",
        "retro",
        "review",
        "roadmap",
        "security-review",
        "status-report",
        "tinyspec",
    ):
        assert extension in fragment, f"{extension} is not verified"


@needs_just
def test_the_verify_recipe_fails_when_extensions_are_absent(speckit: Path) -> None:
    """Runs the real recipe against a repository where nothing is installed."""
    assert render("workspace/just", speckit).returncode == 0

    result = subprocess.run(
        [just_bin(), "speckit-verify-extensions"],
        cwd=speckit,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    combined = result.stdout + result.stderr
    # Either specify is absent or the extensions are; both are a failure to provision.
    assert "specify is not installed" in combined or "missing SpecKit extension" in combined


# --- what it does not do ---------------------------------------------------


def test_no_specify_tree_is_rendered(speckit: Path) -> None:
    """The package's own setup skill owns the scaffolding. Rendering a `.specify/` tree
    here would fork what `specify init` produces.
    """
    assert not (speckit / ".specify").exists()
    assert not (speckit / "specs").exists()


def test_no_tasks_md_is_ever_written(speckit: Path) -> None:
    """Task state lives in beads, and the package ships a guard that denies writing one."""
    assert not list(speckit.rglob("tasks.md"))


def test_the_bootstrap_is_not_a_copier_task(speckit: Path) -> None:
    """It runs `specify init`, reaches a catalog over the network for twelve extensions,
    and calls `bd init`, so a render that had otherwise succeeded would fail on it.
    """
    config = yaml.safe_load(
        (REPO_ROOT / "templates" / "agentic" / "speckit" / "copier.yml").read_text()
    )
    tasks = " ".join(config["_tasks"])
    assert "add_locator.py" in tasks
    assert "specify" not in tasks
    assert "bd init" not in tasks


def test_it_renders_after_beads(speckit: Path) -> None:
    """The formula installs into `.beads/formulas/` and the guard is inert without a
    workspace, so a repo with no `.beads/` gets a SpecKit that cannot provision the DAG.
    """
    config = yaml.safe_load(
        (REPO_ROOT / "templates" / "agentic" / "speckit" / "copier.yml").read_text()
    )
    assert "agentic/beads" in config["_scaffold"]["after"]
    assert "agentic/apm" in config["_scaffold"]["after"]
