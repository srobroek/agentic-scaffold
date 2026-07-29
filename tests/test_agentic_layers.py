"""agentic/*: apm.yml, beads bootstrap, and what they contribute to the aggregators."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"
TEMPLATES = REPO_ROOT / "templates"

APM_ANSWERS = """\
project_name: demo
description: A demo project
apm_packages: []
apm_target: "claude,codex"
apm_cli_version: "0.25.0"
"""

BEADS_ANSWERS = """\
bd_prefix: demo
bd_dolt_sync: local-only
bd_auto_export: false
"""


def render(layer: str, dest: Path, answers: str = "") -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(RENDER), layer, str(dest)]
    if answers:
        answers_file = dest.parent / f"{dest.name}-{layer.replace('/', '-')}.yml"
        answers_file.write_text(answers)
        argv += ["--answers", str(answers_file)]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for key, value in (("user.email", "t@e.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(path), "config", key, value], check=True)
    return path


needs_bd = pytest.mark.skipif(shutil.which("bd") is None, reason="bd absent from PATH")


# --- agentic/apm -----------------------------------------------------------


@pytest.fixture
def apm(tmp_path: Path) -> Path:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("agentic/apm", dest, APM_ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def test_apm_yml_parses_and_carries_the_threaded_values(apm: Path) -> None:
    spec = yaml.safe_load((apm / "apm.yml").read_text())
    assert spec["name"] == "demo"
    assert spec["target"] == "claude,codex"
    # `includes: auto` is what makes `apm compile` weave package context into
    # AGENTS.md, which is why docs/agents carries pointers rather than prose.
    assert spec["includes"] == "auto"


def test_an_empty_package_list_is_valid(apm: Path) -> None:
    """A repository can seed the layer and choose packages later.

    bailiff's version carried a validator refusing the empty list, which made the
    layer unusable until someone had picked packages. `agentic/marketplace`
    recommends against the rendered layer set afterwards.
    """
    spec = yaml.safe_load((apm / "apm.yml").read_text())
    assert spec["dependencies"]["apm"] == []


def test_the_packages_are_written_when_supplied(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    locators = [
        "srobroek/agentic-packages/packages/speckit#>=5.0.0 <6.0.0",
        "srobroek/slopvac/packages/write-docs#>=1.0.0 <2.0.0",
    ]
    render(
        "agentic/apm",
        dest,
        APM_ANSWERS.replace("apm_packages: []", "apm_packages:\n" + "".join(f'  - "{p}"\n' for p in locators)),
    )
    assert yaml.safe_load((dest / "apm.yml").read_text())["dependencies"]["apm"] == locators


def test_the_cli_version_is_pinned_in_the_recipes(apm: Path) -> None:
    """An unpinned CLI would change what a re-render installs."""
    body = (apm / ".just.d" / "apm.just").read_text()
    assert "apm-cli==0.25.0" in body
    # just's own interpolation has to survive jinja rendering.
    assert "{{ apm }}" in body


def test_apm_ignores_its_install_tree(apm: Path) -> None:
    assert "apm_modules/" in (apm / ".gitignore.d" / "apm").read_text()


def test_an_existing_apm_yml_is_not_overwritten(apm: Path) -> None:
    """A package list is hand-edited after rendering."""
    manifest = apm / "apm.yml"
    manifest.write_text("name: mine\nversion: 9.9.9\n")

    render("agentic/apm", apm, APM_ANSWERS)

    assert "mine" in manifest.read_text()


# --- agentic/beads ---------------------------------------------------------


@pytest.fixture
def beads(tmp_path: Path) -> Path:
    dest = git_repo(tmp_path / "d")
    result = render("agentic/beads", dest, BEADS_ANSWERS)
    assert result.returncode == 0, result.stdout + result.stderr
    return dest


@needs_bd
def test_beads_initialises_without_touching_the_hooks_path(beads: Path) -> None:
    """`bd init` without --skip-hooks repoints core.hooksPath at .beads/hooks.

    That copy also picks up whatever hook binaries are ambient, which is how a 347MB
    git-defender copy with an unusable arm64 slice ended up blocking every commit.
    quality/hooks reproduces bd's five hooks as prek entries instead.
    """
    assert (beads / ".beads").is_dir()

    result = subprocess.run(
        ["git", "-C", str(beads), "config", "--local", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, f"core.hooksPath was set to {result.stdout.strip()!r}"
    assert not (beads / ".beads" / "hooks").exists()


@needs_bd
def test_the_agent_lifecycle_hooks_are_kept(beads: Path) -> None:
    """These reload beads context after compaction.

    `--skip-agents` would remove them, which is what makes an AGENTS.md carrying no
    beads prose safe. bailiff's version passed that flag unconditionally.
    """
    codex = yaml.safe_load((beads / ".codex" / "hooks.json").read_text())["hooks"]
    for event in ("SessionStart", "UserPromptSubmit", "PreCompact", "PostCompact"):
        assert event in codex, f"codex {event} hook is missing"

    claude = yaml.safe_load((beads / ".claude" / "settings.json").read_text())["hooks"]
    assert "SessionStart" in claude


@needs_bd
def test_bds_ignore_lines_move_into_a_fragment(beads: Path) -> None:
    """base/gitignore rebuilds the root file, so lines left there would be dropped.

    bd appends its block with a header and no end marker, so nothing else could tell
    which lines were its.
    """
    fragment = (beads / ".gitignore.d" / "beads").read_text()
    for pattern in (".dolt/", ".beads-credential-key", ".beads/proxieddb/"):
        assert pattern in fragment

    # And the root file no longer carries bd's block, which would double them up.
    root = beads / ".gitignore"
    if root.is_file():
        assert "added by bd init" not in root.read_text()


@needs_bd
def test_the_ignore_lines_survive_a_gitignore_rebuild(beads: Path) -> None:
    """The end-to-end case the render order exists for."""
    result = render("base/gitignore", beads, 'gitnr_templates: ""\n')
    assert result.returncode == 0, result.stderr

    body = (beads / ".gitignore").read_text()
    for pattern in (".dolt/", ".beads-credential-key"):
        assert pattern in body, f"{pattern} was lost when .gitignore was rebuilt"


@needs_bd
def test_beads_is_idempotent(beads: Path) -> None:
    """`--init-if-missing` exits 0 on a second run rather than aborting."""
    result = render("agentic/beads", beads, BEADS_ANSWERS)
    assert result.returncode == 0, result.stdout + result.stderr


def bd_command() -> list[str]:
    """The exact argv bd_init.py builds, read from the module rather than guessed."""
    import importlib.util

    path = TEMPLATES / "agentic" / "beads" / "tasks" / "bd_init.py"
    spec = importlib.util.spec_from_file_location("bd_init_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured: list[list[str]] = []
    module.run = lambda command, dest, required=True: captured.append(command) or 0
    module.move_gitignore_lines = lambda dest: None
    module.main(["/nonexistent", "--prefix", "x"])
    return captured[0]


def test_the_layer_never_skips_the_agent_hooks() -> None:
    """`--skip-agents` would remove the hooks that reload beads context.

    Checked against the argv the task actually builds: a comment naming the flag as
    rejected must not make this test pass or fail.
    """
    assert "--skip-agents" not in bd_command()

    # And no answer can introduce it, since the flag is not a variable.
    body = yaml.safe_load((TEMPLATES / "agentic" / "beads" / "copier.yml").read_text())
    assert "--skip-agents" not in " ".join(body["_tasks"])


def test_the_layer_always_skips_the_git_hooks() -> None:
    """quality/hooks owns those five events as prek entries."""
    assert "--skip-hooks" in bd_command()


def test_a_non_git_destination_is_refused(tmp_path: Path) -> None:
    """`bd init` reads the repo's git config, so it aborts outside a work tree."""
    dest = tmp_path / "notgit"
    dest.mkdir()

    result = render("agentic/beads", dest, BEADS_ANSWERS)

    assert result.returncode == 3
    assert "not a git repository" in result.stderr


# --- AGENTS.md ownership ---------------------------------------------------


@needs_bd
def test_docs_agents_owns_the_index_and_beads_appends_below(tmp_path: Path) -> None:
    """bd's own AGENTS.md is 127 lines of three overlapping beads blocks.

    Left to itself that file becomes what a repository's agents read first, so the
    task passes `--agents-template` pointing at the body docs/agents rendered.
    Verified against bd 1.1.2.
    """
    dest = git_repo(tmp_path / "d")
    assert render("docs/agents", dest, "project_name: demo\n").returncode == 0
    assert render("agentic/beads", dest, BEADS_ANSWERS).returncode == 0

    index = (dest / "AGENTS.md").read_text()
    assert index.startswith("# demo"), "bd's body won"
    assert "## Read for" in index
    # bd still gets its block, appended below the body it was given.
    assert "BEADS" in index


@needs_bd
def test_the_index_recovers_when_beads_rendered_first(tmp_path: Path) -> None:
    """Render order should not be the only thing keeping the body in place."""
    dest = git_repo(tmp_path / "d")
    assert render("agentic/beads", dest, BEADS_ANSWERS).returncode == 0
    assert render("docs/agents", dest, "project_name: demo\n").returncode == 0

    index = (dest / "AGENTS.md").read_text()
    assert index.startswith("# demo")
    # And bd's block is not lost in the recovery.
    assert "BEADS" in index


def test_claude_md_is_a_relative_symlink(tmp_path: Path) -> None:
    """One file serves both harnesses, and a relative target survives a clone."""
    dest = git_repo(tmp_path / "d")
    render("docs/agents", dest, "project_name: demo\n")

    link = dest / "CLAUDE.md"
    assert link.is_symlink(), "CLAUDE.md is not a symlink"
    assert link.readlink() == Path("AGENTS.md")


def test_the_index_is_a_copy_not_a_symlink(tmp_path: Path) -> None:
    """agentic/beads appends to AGENTS.md, and a symlink would write into the body."""
    dest = git_repo(tmp_path / "d")
    render("docs/agents", dest, "project_name: demo\n")

    assert not (dest / "AGENTS.md").is_symlink()
    assert (dest / "docs" / "agents" / "AGENTS.body.md").is_file()


def test_a_hand_edited_index_survives_a_second_render(tmp_path: Path) -> None:
    dest = git_repo(tmp_path / "d")
    render("docs/agents", dest, "project_name: demo\n")

    index = dest / "AGENTS.md"
    index.write_text(index.read_text() + "\n## Mine\n\nDo not lose this.\n")

    render("docs/agents", dest, "project_name: demo\n")

    assert "Do not lose this." in index.read_text()


# --- what both contribute to the aggregators -------------------------------


@pytest.mark.parametrize("layer", ["agentic/apm", "agentic/beads"])
def test_each_layer_ships_a_just_fragment(layer: str) -> None:
    name = layer.split("/")[1]
    matches = list((TEMPLATES / layer).glob(f"template/.just.d/{name}*.just*"))
    assert matches, f"{layer} ships no .just.d fragment"


def test_a_recipe_description_is_not_a_stray_rationale_line() -> None:
    """just takes the comment directly above a recipe as its `--list` description.

    A rationale block ending just above the recipe silently becomes the description,
    which then reads as a sentence fragment in `just --list`.
    """
    offenders = []
    for fragment in sorted(TEMPLATES.glob("*/*/template/.just.d/*.just*")):
        lines = fragment.read_text().splitlines()
        for index, line in enumerate(lines):
            if not re.match(r"^\[group\(", line):
                continue
            # Walk back over the attribute to the comment that documents the recipe.
            comment = lines[index - 1] if index else ""
            if not comment.lstrip().startswith("#"):
                continue
            text = comment.lstrip("# ").strip()
            # A description is a phrase, not the tail of a sentence.
            if text.endswith(".") or (text and text[0].islower()):
                offenders.append(f"{fragment.name}: {text!r}")
    assert not offenders, "rationale leaked into a recipe description: " + "; ".join(offenders)
