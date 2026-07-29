"""workspace/just: the root justfile and the import block it aggregates."""

from __future__ import annotations

import json
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


# --- workspace/monorepo ----------------------------------------------------

MONOREPO_ANSWERS = {
    "rust": 'layout: rust\nproject_name: demo\nmembers: ""\nrust_edition: "2024"\n',
    "python": 'layout: python\nproject_name: demo\nmembers: ""\npython_version: "3.13"\n',
    "go": 'layout: go\nproject_name: demo\nmembers: ""\ngo_module_path: example.com/demo\ngo_version: "1.26"\n',
    "ts": 'layout: ts\nproject_name: demo\nmembers: ""\n',
}

MANIFEST = {
    "rust": "Cargo.toml",
    "python": "pyproject.toml",
    "go": "go.mod",
    "ts": "package.json",
}


def workspace(tmp_path: Path, layout: str) -> Path:
    dest = tmp_path / "ws"
    dest.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    for key, value in (("user.email", "t@e.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(dest), "config", key, value], check=True)
    result = render("workspace/monorepo", dest, MONOREPO_ANSWERS[layout])
    assert result.returncode == 0, result.stderr
    return dest


@pytest.mark.parametrize("layout", sorted(MONOREPO_ANSWERS))
def test_each_layout_writes_only_its_own_manifest(layout: str, tmp_path: Path) -> None:
    """A conditional filename holding a quote breaks jinja, so the comparison is a
    derived boolean instead."""
    dest = workspace(tmp_path, layout)

    assert (dest / MANIFEST[layout]).is_file()
    for other, name in MANIFEST.items():
        if other != layout:
            assert not (dest / name).exists(), f"{layout} also wrote {name}"


def test_the_member_glob_follows_the_layout(tmp_path: Path) -> None:
    """rust conventionally uses crates/*, python and ts packages/*, go cmd/*."""
    assert 'members = ["crates/*"]' in (
        workspace(tmp_path / "a", "rust") / "Cargo.toml"
    ).read_text()
    assert 'members = ["packages/*"]' in (
        workspace(tmp_path / "b", "python") / "pyproject.toml"
    ).read_text()
    assert '"packages/*"' in (workspace(tmp_path / "c", "ts") / "package.json").read_text()


def test_an_explicit_member_glob_wins(tmp_path: Path) -> None:
    dest = tmp_path / "ws"
    dest.mkdir()
    render(
        "workspace/monorepo",
        dest,
        MONOREPO_ANSWERS["rust"].replace('members: ""', 'members: "libs/*"'),
    )
    assert 'members = ["libs/*"]' in (dest / "Cargo.toml").read_text()


def test_the_python_root_is_not_a_distribution(tmp_path: Path) -> None:
    """Without `[tool.uv] package = false` uv treats the root as a package, and
    `uv sync` fails with "Expected a Python module at: src/<name>/__init__.py"."""
    body = (workspace(tmp_path, "python") / "pyproject.toml").read_text()
    assert "package = false" in body


def test_a_generator_manifest_is_not_replaced(tmp_path: Path) -> None:
    """The generator runs before this layer in a single repo, and its manifest wins."""
    dest = tmp_path / "ws"
    dest.mkdir()
    (dest / "Cargo.toml").write_text('[package]\nname = "mine"\nversion = "0.1.0"\n')

    render("workspace/monorepo", dest, MONOREPO_ANSWERS["rust"])

    assert "mine" in (dest / "Cargo.toml").read_text()


@needs_just
def test_add_refuses_a_name_that_reaches_a_shell(tmp_path: Path) -> None:
    """`name` reaches `uv init --name` and `go mod init`, so it is validated first."""
    dest = workspace(tmp_path, "rust")
    render("workspace/just", dest)

    for bad in ("../escape", "a b", "x;whoami"):
        result = subprocess.run(
            [sys.executable, str(dest / "scripts" / "add_member.py"), bad, "rust"],
            cwd=dest,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode != 0, f"{bad!r} was accepted"
        assert "must start alphanumeric" in result.stderr


@needs_just
def test_add_refuses_an_occupied_member_path(tmp_path: Path) -> None:
    dest = workspace(tmp_path, "rust")
    (dest / "crates" / "taken").mkdir(parents=True)
    (dest / "crates" / "taken" / "keep.txt").write_text("mine\n")

    result = subprocess.run(
        [sys.executable, str(dest / "scripts" / "add_member.py"), "taken", "rust"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "already exists" in result.stderr


@needs_just
def test_add_reads_the_member_path_from_the_manifest(tmp_path: Path) -> None:
    """Deriving it keeps `just add` and the manifest from disagreeing."""
    dest = tmp_path / "ws"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    render(
        "workspace/monorepo",
        dest,
        MONOREPO_ANSWERS["rust"].replace('members: ""', 'members: "libs/*"'),
    )

    result = subprocess.run(
        [sys.executable, str(dest / "scripts" / "add_member.py"), "thing", "rust"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert (dest / "libs" / "thing").is_dir()


@needs_just
@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo absent from PATH")
def test_a_language_layer_lands_in_two_roots(tmp_path: Path) -> None:
    """The case the layer exists for.

    A language layer's tool configs describe the member and stay with it; its
    `.mise/conf.d/`, `.just.d/`, `.gitignore.d/`, and CI fragments are read from the
    repository root by the aggregating layers. copier renders to one destination, so
    the repo-wide directories are moved up afterwards.
    """
    dest = workspace(tmp_path, "rust")
    render("workspace/just", dest)

    result = subprocess.run(
        [
            sys.executable,
            str(dest / "scripts" / "add_member.py"),
            "api",
            "rust",
            "--scaffold",
            str(REPO_ROOT),
        ],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    member = dest / "crates" / "api"
    # Describes the member, so it stays with it.
    for expected in ("Cargo.toml", "clippy.toml", "rustfmt.toml", "deny.toml"):
        assert (member / expected).is_file(), f"{expected} should stay with the member"

    # Read from the repository root, so it moved up.
    for expected in (
        ".mise/conf.d/rust.toml",
        ".just.d/rust.just",
        ".gitignore.d/rust",
        ".github/workflows/wc-lint-rust.yml",
        ".gitlab/ci/rust.yml",
    ):
        assert (dest / expected).is_file(), f"{expected} should be at the repo root"
        assert not (member / expected).exists(), f"{expected} was left in the member"


@needs_just
@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo absent from PATH")
def test_a_second_member_merges_rather_than_replaces(tmp_path: Path) -> None:
    """Two members both contribute a `.mise/conf.d/` entry, so moving the directory
    wholesale would drop the first."""
    dest = workspace(tmp_path, "rust")
    render("workspace/just", dest)

    for name in ("first", "second"):
        result = subprocess.run(
            [
                sys.executable,
                str(dest / "scripts" / "add_member.py"),
                name,
                "rust",
                "--scaffold",
                str(REPO_ROOT),
            ],
            cwd=dest,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stdout + result.stderr

    assert (dest / ".mise" / "conf.d" / "rust.toml").is_file()
    assert (dest / ".just.d" / "rust.just").is_file()
    for name in ("first", "second"):
        assert (dest / "crates" / name / "Cargo.toml").is_file()


@needs_just
@pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo absent from PATH")
def test_a_member_gets_a_real_hook_config(tmp_path: Path) -> None:
    """prek's workspace mode reads `.pre-commit-config.yaml`, one per directory, and
    namespaces the hooks `<dir>:<hook-id>`.

    It skips dot-prefixed directories while discovering, so the `.pre-commit.d/`
    fragment alone is invisible to it and the member's hooks never run.
    """
    dest = workspace(tmp_path, "rust")
    render("workspace/just", dest)

    subprocess.run(
        [
            sys.executable,
            str(dest / "scripts" / "add_member.py"),
            "api",
            "rust",
            "--scaffold",
            str(REPO_ROOT),
        ],
        cwd=dest,
        check=True,
        capture_output=True,
    )

    config = dest / "crates" / "api" / ".pre-commit-config.yaml"
    assert config.is_file(), "the member has no config for prek to union"
    assert "cargo-fmt" in config.read_text()


def add_member(dest: Path, name: str, lang: str = "rust") -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(dest / "scripts" / "add_member.py"), name, lang],
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
    )


RP_ANSWERS = """\
release_type: rust
initial_version: 0.1.0
default_branch: main
release_packages: []
"""


@needs_just
def test_add_registers_the_member_with_release_please(tmp_path: Path) -> None:
    """release-please has no glob support.

    `packages` takes a literal path per package, and its workspace plugins only build a
    dependency graph over what is already configured, so a member absent from the config
    is never versioned, tagged, or written into the changelog. `just add` is the moment
    the member exists, so it registers there rather than through a reconciling script.
    """
    dest = workspace(tmp_path, "rust")
    render("release/release-please", dest, RP_ANSWERS)

    result = add_member(dest, "api")
    assert result.returncode == 0, result.stdout + result.stderr

    config = json.loads((dest / "release-please-config.json").read_text())
    assert "crates/api" in config["packages"]
    assert config["packages"]["crates/api"]["component"] == "api"
    assert config["packages"]["crates/api"]["release-type"] == "rust"
    # Per-package tags, or every member's tag collides on one version number.
    assert config["include-component-in-tag"] is True

    # The root is no longer the thing being released, and its tag would collide.
    assert "." not in config["packages"]


@needs_just
def test_add_keeps_the_versions_release_please_recorded(tmp_path: Path) -> None:
    """Resetting a released package would make release-please re-release it."""
    dest = workspace(tmp_path, "rust")
    render("release/release-please", dest, RP_ANSWERS)
    assert add_member(dest, "api").returncode == 0

    path = dest / ".release-please-manifest.json"
    path.write_text(json.dumps({"crates/api": "2.3.1"}, indent=2) + "\n")

    assert add_member(dest, "core").returncode == 0

    recorded = json.loads(path.read_text())
    assert recorded["crates/api"] == "2.3.1"
    # A new member joins where the others are, so a repo releasing 2.x ships no 0.1.0.
    assert recorded["crates/core"] == "2.3.1"


@needs_just
def test_add_starts_a_new_member_at_the_initial_version_when_versions_disagree(
    tmp_path: Path,
) -> None:
    dest = workspace(tmp_path, "rust")
    render("release/release-please", dest, RP_ANSWERS)
    assert add_member(dest, "api").returncode == 0
    assert add_member(dest, "core").returncode == 0

    path = dest / ".release-please-manifest.json"
    path.write_text(
        json.dumps({"crates/api": "2.3.1", "crates/core": "1.0.0"}, indent=2) + "\n"
    )

    assert add_member(dest, "util").returncode == 0

    assert json.loads(path.read_text())["crates/util"] == "0.1.0"


@needs_just
def test_add_works_without_the_release_layer(tmp_path: Path) -> None:
    """A repository may not release at all, and adding a member still has to work."""
    dest = workspace(tmp_path, "rust")

    result = add_member(dest, "api")

    assert result.returncode == 0, result.stdout + result.stderr
    assert (dest / "crates" / "api").is_dir()
    assert not (dest / "release-please-config.json").exists()


@needs_just
def test_setup_is_the_one_entry_point(rendered: Path) -> None:
    """`wt`'s blocking pre-start runs `just setup` per worktree, and its default answer
    names this recipe, so it has to exist even with no other layer rendered."""
    assert just(rendered, "--show", "setup").returncode == 0

    body = (rendered / "justfile").read_text()
    # mise first: it supplies the interpreters and binaries the later steps call.
    assert "mise install" in body
    for recipe in ("hooks-install", "rtk-setup", "apm-install"):
        assert recipe in body, f"setup never reaches {recipe}"


@needs_just
def test_setup_probes_rather_than_depends(rendered: Path) -> None:
    """Which recipes exist follows from which layers rendered.

    A dependency on one that never rendered is a parse error that breaks every recipe in
    the file, so setup asks `just --show` instead. Here nothing else rendered, so it must
    still run cleanly.
    """
    result = just(rendered, "setup")

    assert result.returncode == 0, result.stdout + result.stderr
    # And it says what it skipped rather than failing silently.
    assert "setup" not in result.stderr or "not on PATH" in result.stderr


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
