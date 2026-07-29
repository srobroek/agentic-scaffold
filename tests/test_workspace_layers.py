"""workspace/just: the root justfile and the import block it aggregates."""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"
TEMPLATES = REPO_ROOT / "templates"

LANG_ANSWERS = {
    "rust": 'crate_kind: lib\nrust_edition: "2024"\n',
    "python": 'python_version: "3.13"\npython_layout: src\npython_framework: none\n',
    "go": 'go_module_path: github.com/srobroek/demo\ngo_version: "1.26"\ngo_vendor: false\n',
    "ts": 'node_version: "24"\nts_typeaware: true\n',
}


def render(layer: str, dest: Path, answers: str = "") -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(RENDER), layer, str(dest)]
    if answers:
        answers_file = dest.parent / f"{dest.name}-{layer.replace('/', '-')}.yml"
        answers_file.write_text(answers)
        argv += ["--answers", str(answers_file)]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


def just(dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["just", *args], cwd=dest, capture_output=True, text=True, check=False
    )


needs_just = pytest.mark.skipif(shutil.which("just") is None, reason="just absent from PATH")


@pytest.fixture
def rendered(tmp_path: Path) -> Path:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("workspace/just", dest)
    assert result.returncode == 0, result.stderr
    return dest


def imports(dest: Path) -> list[str]:
    return re.findall(r"^import\?? '(.+)'$", (dest / "justfile").read_text(), re.M)


# --- the fragment contract -------------------------------------------------


def test_no_two_fragments_declare_the_same_recipe() -> None:
    """Every fragment shares one flat namespace, and a collision is a hard error.

    Verified against just 1.50.0: a name defined twice fails with "first defined on
    line N is redefined", and it takes down every recipe in the file rather than
    only the pair. Prefixing each recipe with its layer name is what prevents it.
    """
    seen: dict[str, str] = {}
    collisions = []
    for fragment in sorted(TEMPLATES.glob("*/*/template/.just.d/*.just*")):
        for name in re.findall(r"^([a-z][a-z0-9-]*)(?:\s+\w+)*:", fragment.read_text(), re.M):
            owner = str(fragment.relative_to(TEMPLATES))
            if name in seen:
                collisions.append(f"{name!r} in both {seen[name]} and {owner}")
            seen[name] = owner
    assert not collisions, "colliding recipe names: " + "; ".join(collisions)


def test_every_fragment_recipe_carries_a_group() -> None:
    """`just --list` is the discovery surface, and an ungrouped recipe floats loose."""
    for fragment in sorted(TEMPLATES.glob("*/*/template/.just.d/*.just*")):
        body = fragment.read_text()
        recipes = re.findall(r"^([a-z][a-z0-9-]*)(?:\s+\w+)*:", body, re.M)
        groups = body.count("[group(")
        assert groups >= len(recipes), (
            f"{fragment.name} has {len(recipes)} recipes but {groups} group attributes"
        )


# --- the generated import block --------------------------------------------


def test_the_import_block_is_empty_before_any_fragment(rendered: Path) -> None:
    assert imports(rendered) == []
    assert "BEGIN GENERATED: imports" in (rendered / "justfile").read_text()


def test_every_fragment_becomes_an_optional_import(tmp_path: Path) -> None:
    """The optional form is load-bearing.

    A hard `import` of a missing file is a parse error that breaks every recipe in
    the justfile, so a fragment deleted by hand would take down `just` entirely
    rather than only its own recipes.
    """
    dest = tmp_path / "d"
    dest.mkdir()
    render("workspace/just", dest)
    (dest / ".just.d").mkdir(exist_ok=True)
    for name in ("alpha", "beta"):
        (dest / ".just.d" / f"{name}.just").write_text(
            f"[group('{name}')]\n{name}-x:\n    @echo {name}\n"
        )

    result = subprocess.run(
        [sys.executable, str(dest / "scripts" / "gen_justfile.py"), str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert imports(dest) == [".just.d/alpha.just", ".just.d/beta.just"]
    for line in (dest / "justfile").read_text().splitlines():
        if line.startswith("import"):
            assert line.startswith("import?"), f"hard import: {line!r}"


def test_the_block_is_rebuilt_deterministically(rendered: Path) -> None:
    """Fragments sort by name, so a re-render never churns the file."""
    (rendered / ".just.d").mkdir(exist_ok=True)
    for name in ("zebra", "alpha", "middle"):
        (rendered / ".just.d" / f"{name}.just").write_text(f"{name}-x:\n    @echo {name}\n")

    script = rendered / "scripts" / "gen_justfile.py"
    subprocess.run([sys.executable, str(script), str(rendered)], check=True, capture_output=True)
    first = (rendered / "justfile").read_text()
    subprocess.run([sys.executable, str(script), str(rendered)], check=True, capture_output=True)

    assert (rendered / "justfile").read_text() == first
    assert imports(rendered) == [
        ".just.d/alpha.just",
        ".just.d/middle.just",
        ".just.d/zebra.just",
    ]


def test_content_outside_the_markers_survives(rendered: Path) -> None:
    """A hand-written recipe in the root justfile is not the generator's to lose."""
    justfile = rendered / "justfile"
    justfile.write_text(justfile.read_text() + "\n# mine\nmine:\n    @echo mine\n")

    subprocess.run(
        [sys.executable, str(rendered / "scripts" / "gen_justfile.py"), str(rendered)],
        check=True,
        capture_output=True,
    )

    assert "mine:" in justfile.read_text()


def test_a_justfile_without_markers_is_refused(rendered: Path) -> None:
    """Guessing where the block goes would corrupt a hand-written justfile."""
    (rendered / "justfile").write_text("default:\n    @echo hi\n")

    result = subprocess.run(
        [sys.executable, str(rendered / "scripts" / "gen_justfile.py"), str(rendered)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 3
    assert "markers" in result.stderr


# --- the real tool ---------------------------------------------------------


@needs_just
def test_the_rendered_justfile_parses(rendered: Path) -> None:
    """With no fragments at all: a fresh scaffold must not be broken on arrival."""
    result = just(rendered, "--list")
    assert result.returncode == 0, result.stderr


@needs_just
def test_no_aggregate_declares_a_dependency_that_may_not_exist(rendered: Path) -> None:
    """`check` probes `hooks-all` rather than depending on it.

    A dependency on a recipe no fragment provided is a parse error that breaks every
    recipe in the file, and quality/hooks may not have rendered.
    """
    result = just(rendered, "--list")
    assert result.returncode == 0, result.stderr
    assert "unknown dependency" not in result.stderr


@needs_just
@pytest.mark.parametrize("language", sorted(LANG_ANSWERS))
def test_a_language_layers_recipes_reach_the_root(language: str, tmp_path: Path) -> None:
    """The whole point: a language's recipes arrive by rendering its layer."""
    dest = tmp_path / "d"
    dest.mkdir()
    render(f"lang/{language}", dest, LANG_ANSWERS[language])
    render("workspace/just", dest)

    listed = just(dest, "--list")
    assert listed.returncode == 0, listed.stderr
    assert f"[{language}]" in listed.stdout
    # The umbrella recipe per language, which `check` dispatches to.
    assert just(dest, "--show", language).returncode == 0


@needs_just
def test_check_dispatches_to_whichever_languages_rendered(tmp_path: Path) -> None:
    """One language renders, one recipe runs. Adding a layer needs no edit here."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/go", dest, LANG_ANSWERS["go"])
    render("workspace/just", dest)

    assert just(dest, "--show", "go").returncode == 0
    # python never rendered, so nothing dispatches to it.
    assert just(dest, "--show", "python").returncode != 0


@needs_just
def test_each_runs_one_phase_across_the_languages_present(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/go", dest, LANG_ANSWERS["go"])
    render("lang/rust", dest, LANG_ANSWERS["rust"])
    render("workspace/just", dest)

    for phase in ("fmt", "lint", "test"):
        assert just(dest, "--show", f"go-{phase}").returncode == 0
        assert just(dest, "--show", f"rust-{phase}").returncode == 0

    # A phase no language provides fails rather than passing silently.
    result = just(dest, "each", "nonsense")
    assert result.returncode != 0
    assert "no recipe matches" in result.stdout + result.stderr


@needs_just
def test_just_add_writes_a_fragment_and_syncs(rendered: Path) -> None:
    result = just(rendered, "just-add", "deploy")
    assert result.returncode == 0, result.stderr

    fragment = rendered / ".just.d" / "deploy.just"
    assert fragment.is_file()
    assert "[group('deploy')]" in fragment.read_text()
    assert ".just.d/deploy.just" in imports(rendered)
    # The new recipe is reachable, not just written.
    assert just(rendered, "--show", "deploy-example").returncode == 0


@needs_just
def test_just_add_refuses_to_overwrite(rendered: Path) -> None:
    assert just(rendered, "just-add", "deploy").returncode == 0
    result = just(rendered, "just-add", "deploy")
    assert result.returncode != 0
    assert "already exists" in result.stdout + result.stderr


@needs_just
def test_just_check_reports_a_stale_block_without_rewriting_it(rendered: Path) -> None:
    """A check that fixes what it checks leaves a dirty tree, and the rerun passes.

    That makes a CI failure non-reproducible, so the comparison happens in a copy.
    """
    (rendered / ".just.d").mkdir(exist_ok=True)
    (rendered / ".just.d" / "late.just").write_text("late-x:\n    @echo late\n")
    before = (rendered / "justfile").read_text()

    result = just(rendered, "just-check")

    assert result.returncode != 0
    assert "stale" in result.stdout + result.stderr
    assert (rendered / "justfile").read_text() == before, "just-check rewrote the justfile"


@needs_just
def test_just_check_passes_once_synced(rendered: Path) -> None:
    (rendered / ".just.d").mkdir(exist_ok=True)
    (rendered / ".just.d" / "late.just").write_text("late-x:\n    @echo late\n")

    assert just(rendered, "just-sync").returncode == 0
    assert just(rendered, "just-check").returncode == 0


@needs_just
def test_the_shell_setting_avoids_bash_3_2_traps(rendered: Path) -> None:
    """macOS ships bash 3.2, where `mapfile` reports success while doing nothing."""
    body = (rendered / "justfile").read_text()
    assert 'set shell := ["bash", "-uc"]' in body

    # Comments explaining the trap are fine; a recipe body using either is not.
    code = [
        line
        for line in body.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    for builtin in ("mapfile", "readarray"):
        assert not any(builtin in line for line in code), f"{builtin} is bash 4 only"
