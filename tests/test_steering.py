"""docs/agents: the steering generator.

A pure function of the tree, per `docs/steering.md`. Nothing is asked, because an answer
could disagree with the files an agent will actually read, and nothing reaches the network,
so CI can verify the output rather than trust it.

The marker format cost a round trip worth recording: the shipped templates name BOTH
markers, `<!-- END GENERATED: index -->` rather than a bare `<!-- END GENERATED -->`. The
first version matched the bare form, found nothing, and wrote an empty block while
reporting that it had written the file.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import mise_bin

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

AGENTS = "project_name: demo\n"
RUST = 'crate_kind: bin\nrust_edition: "2024"\nlicense: Apache-2.0\n'
PYTHON = 'python_version: "3.13"\npython_layout: src\npython_framework: none\n'

# Resolved through mise. See conftest.mise_bin for why not an installs/<tool>/latest path.
_JUST_BIN = mise_bin("just")
JUST = (_JUST_BIN / "just") if _JUST_BIN else Path("just")
needs_just = pytest.mark.skipif(
    not JUST.is_file() and shutil.which("just") is None, reason="just absent"
)


def render(layer: str, dest: Path, answers: str = "") -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(RENDER), layer, str(dest)]
    if answers:
        answers_file = dest.parent / f"{dest.name}-{layer.replace('/', '-')}.yml"
        answers_file.write_text(answers)
        argv += ["--answers", str(answers_file)]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def generate(dest: Path, *flags: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "scripts/gen_steering.py", ".", *flags],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def steering(tmp_path: Path) -> Path:
    """A repository with steering, one language, and the task surface."""
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("docs/agents", dest, AGENTS).returncode == 0
    assert render("lang/rust", dest, RUST).returncode == 0
    assert render("workspace/just", dest).returncode == 0
    assert generate(dest).returncode == 0
    return dest


def block(dest: Path, relative: str, name: str) -> str:
    body = (dest / "docs" / "agents" / relative).read_text()
    return body.partition(f"<!-- BEGIN GENERATED: {name} -->")[2].partition(
        f"<!-- END GENERATED: {name} -->"
    )[0]


# --- it describes the tree -------------------------------------------------


def test_the_generator_ships_with_the_layer(steering: Path) -> None:
    assert (steering / "scripts" / "gen_steering.py").is_file()


def test_the_index_lists_the_real_task_surface(steering: Path) -> None:
    """Read from the justfile and its fragments rather than asked, so the list cannot
    disagree with what `just --list` shows."""
    content = block(steering, "index.md", "index")
    assert "just" in content
    for recipe in ("rust-lint", "rust-test", "check"):
        assert recipe in content, f"{recipe} is missing from the index"


def test_just_directives_are_not_mistaken_for_recipes(steering: Path) -> None:
    """`set shell := [...]` and `import? '...'` both open a line with a lowercase word, which
    the recipe pattern cannot tell from a recipe name."""
    content = block(steering, "index.md", "index")
    for directive in ("\nset ", " set ", "\nimport ", " import "):
        assert directive not in content, f"{directive.strip()!r} is a directive, not a recipe"


def test_the_toolchain_pins_come_from_the_mise_fragments(steering: Path) -> None:
    """Those fragments are what `mise install` resolves, so they are what an agent needs."""
    content = block(steering, "index.md", "index")
    assert "cargo-nextest" in content or "cargo:cargo-nextest" in content
    assert "just" in content


def test_a_quality_leaf_exists_per_language(steering: Path) -> None:
    assert (steering / "docs" / "agents" / "quality" / "rust.md").is_file()
    assert not (steering / "docs" / "agents" / "quality" / "python.md").exists()

    index = block(steering, "quality/index.md", "quality-index")
    assert "just rust-lint" in index
    assert "python" not in index


def test_adding_a_language_adds_a_file_rather_than_growing_one(steering: Path) -> None:
    """docs/steering.md states this directly: adding a language adds `quality/<lang>.md`
    plus one line in its index, and no existing file grows."""
    before = (steering / "docs" / "agents" / "quality" / "rust.md").read_text()

    assert render("lang/python", steering, PYTHON).returncode == 0
    assert generate(steering).returncode == 0

    leaf = steering / "docs" / "agents" / "quality" / "python.md"
    assert leaf.is_file(), "no leaf was created for the new language"
    assert "just python-lint" in leaf.read_text()
    # The existing leaf is untouched.
    assert (steering / "docs" / "agents" / "quality" / "rust.md").read_text() == before
    # And the index gained the row.
    assert "python" in block(steering, "quality/index.md", "quality-index")


def test_the_release_block_reports_the_real_tag_shape(tmp_path: Path) -> None:
    """release-please's own config decides the tag format, and the marketplace and the
    version guard both resolve against it."""
    dest = tmp_path / "release"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("docs/agents", dest, AGENTS).returncode == 0
    assert (
        render(
            "release/release-please",
            dest,
            "release_type: rust\ninitial_version: 0.1.0\n"
            "default_branch: main\nrelease_packages: []\n",
        ).returncode
        == 0
    )
    assert generate(dest).returncode == 0

    content = block(dest, "release/index.md", "release-index")
    assert "release-please" in content
    assert "v<version>" in content
    # A hand-made tag is what breaks version derivation, so the steering says so.
    assert "never tagged by hand" in content


def test_the_env_block_names_variables_without_values(steering: Path) -> None:
    """A value would be a secret. The point is telling an agent which variables exist."""
    assert (
        render(
            "host/github",
            steering,
            'default_branch: main\njob_timeout_minutes: 15\nsecurity_contact: ""\n'
            'coc_contact: ""\nproject_name: demo\norg: demo\n',
        ).returncode
        == 0
    )
    assert generate(steering).returncode == 0

    content = block(steering, "env/index.md", "env-index")
    # Ambient CI names say nothing about the project and are filtered out.
    assert "GITHUB_TOKEN" not in content
    assert "=" not in content, "a value leaked into the steering"


# --- what it must not touch ------------------------------------------------


def test_conventions_is_never_written(steering: Path) -> None:
    """It carries no marker, and a file with no marker is never written after it is first
    created. That is the whole mechanism keeping the hand-written half."""
    path = steering / "docs" / "agents" / "conventions.md"
    path.write_text(path.read_text() + "\nOur own rule, hand-written.\n")

    assert generate(steering).returncode == 0
    assert "Our own rule, hand-written." in path.read_text()


def test_content_outside_the_markers_survives(steering: Path) -> None:
    path = steering / "docs" / "agents" / "index.md"
    path.write_text(path.read_text() + "\n## Local note\n\nSurvives regeneration.\n")

    assert generate(steering).returncode == 0
    body = path.read_text()
    assert "Survives regeneration." in body
    # And the generated block is still current.
    assert "just" in block(steering, "index.md", "index")


def test_generation_is_idempotent(steering: Path) -> None:
    """A second run must write nothing, or every unrelated commit carries the steering."""
    result = generate(steering)
    assert result.returncode == 0
    assert "wrote 0 of" in result.stdout


# --- the check gate --------------------------------------------------------


def test_check_passes_on_a_current_tree(steering: Path) -> None:
    assert generate(steering, "--check").returncode == 0


def test_check_reports_drift_without_repairing_it(steering: Path) -> None:
    """A gate that fixes what it checks destroys a hand edit and passes on the rerun."""
    path = steering / "docs" / "agents" / "index.md"
    path.write_text(path.read_text().replace("## Commands", "## TAMPERED"))

    result = generate(steering, "--check")
    assert result.returncode == 1
    assert "just steering" in result.stderr
    assert "TAMPERED" in path.read_text(), "--check must not rewrite the tree"


def test_check_catches_a_newly_adopted_language(steering: Path) -> None:
    """The case the gate exists for: a layer adopted without regenerating leaves the
    steering describing a tree that no longer exists."""
    assert render("lang/python", steering, PYTHON).returncode == 0
    result = generate(steering, "--check")
    assert result.returncode == 1


def test_a_tree_without_steering_is_left_alone(tmp_path: Path) -> None:
    """docs/agents may not have rendered, and writing it here would fork what that layer
    owns."""
    dest = tmp_path / "bare"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    (dest / "scripts").mkdir()
    shutil.copy(
        REPO_ROOT / "templates" / "docs" / "agents" / "template" / "scripts" / "gen_steering.py",
        dest / "scripts",
    )
    result = generate(dest)
    assert result.returncode == 0
    assert not (dest / "docs").exists()


@needs_just
def test_the_recipes_render_and_list(steering: Path) -> None:
    fragment = (steering / ".just.d" / "steering.just").read_text()
    assert "steering-check" in fragment

    listing = subprocess.run(
        [str(JUST) if JUST.is_file() else "just", "--list"],
        cwd=steering,
        capture_output=True,
        text=True,
        check=False,
    )
    assert listing.returncode == 0, listing.stderr
    assert "steering" in listing.stdout
