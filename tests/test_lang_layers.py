"""lang/* layers: every language ships the same eight file kinds."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import render_recipe as render

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPES = REPO_ROOT / "recipes" / "lang"

ANSWERS = {
    "rust": 'crate_kind: lib\nrust_edition: "2024"\n',
    "python": 'python_version: "3.13"\npython_layout: src\npython_framework: none\n',
    "go": 'go_module_path: github.com/srobroek/demo\ngo_version: "1.26"\ngo_vendor: false\n',
    "ts": 'node_version: "24"\nts_typeaware: true\n',
}


LANGUAGES = sorted(ANSWERS)


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_language_ships_the_same_file_kinds(language: str, tmp_path: Path) -> None:
    """The shape is what makes adding a language a one-directory change."""
    dest = tmp_path / language
    dest.mkdir()
    result = render(f"lang/{language}", dest, ANSWERS[language])
    assert result.returncode == 0, result.stderr

    for expected in (
        f".gitignore.d/{language}",
        f".pre-commit.d/{language}.yaml",
        f".mise/conf.d/{language}.toml",
        f".just.d/{language}.just",
        f".gitlab/ci/{language}.yml",
        f".github/workflows/wc-lint-{language}.yml",
        f".github/workflows/wc-test-{language}.yml",
        f".github/actions/setup-{language}/action.yml",
        f".github/quality.d/{language}.yml",
        f".github/security.d/{language}.yml",
    ):
        assert (dest / expected).is_file(), f"{language} is missing {expected}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_reusable_workflows_take_a_working_directory(language: str, tmp_path: Path) -> None:
    """Without it a monorepo member cannot be linted where it sits."""
    dest = tmp_path / language
    dest.mkdir()
    render(f"lang/{language}", dest, ANSWERS[language])
    for kind in ("lint", "test"):
        body = (dest / ".github" / "workflows" / f"wc-{kind}-{language}.yml").read_text()
        assert "working-directory" in body
        assert "workflow_call" in body


@pytest.mark.parametrize("language", LANGUAGES)
def test_checkout_does_not_persist_credentials(language: str, tmp_path: Path) -> None:
    """zizmor reports the default, which leaves GITHUB_TOKEN in .git/config."""
    dest = tmp_path / language
    dest.mkdir()
    render(f"lang/{language}", dest, ANSWERS[language])
    for kind in ("lint", "test"):
        body = (dest / ".github" / "workflows" / f"wc-{kind}-{language}.yml").read_text()
        assert "persist-credentials: false" in body


@pytest.mark.parametrize("language", LANGUAGES)
def test_actions_are_pinned_to_a_sha(language: str, tmp_path: Path) -> None:
    """zizmor's unpinned-uses rejects a tag on any action, first-party included."""
    dest = tmp_path / language
    dest.mkdir()
    render(f"lang/{language}", dest, ANSWERS[language])

    for path in (dest / ".github").rglob("*.yml"):
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped.startswith("- uses:"):
                continue
            reference = stripped.removeprefix("- uses:").strip()
            if reference.startswith("./"):
                continue  # a local composite action carries no ref
            _, _, version = reference.partition("@")
            # A pinned line carries a trailing `# vN` comment naming the tag.
            sha = version.split("#", 1)[0].strip()
            assert len(sha) == 40, f"{path.name}: {reference} is not SHA-pinned"
            assert all(c in "0123456789abcdef" for c in sha), f"{path.name}: {sha} is not a hex SHA"


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_security_fragment_declares_codeql_support(language: str, tmp_path: Path) -> None:
    """CodeQL has no Rust extractor, so the fragment must say so rather than guess."""
    dest = tmp_path / language
    dest.mkdir()
    render(f"lang/{language}", dest, ANSWERS[language])
    fragment = yaml.safe_load((dest / ".github" / "security.d" / f"{language}.yml").read_text())
    assert isinstance(fragment["codeql"]["supported"], bool)
    if not fragment["codeql"]["supported"]:
        assert fragment["codeql"].get("reason")


def test_ruff_ignores_use_names_not_codes(tmp_path: Path) -> None:
    """preview = true enables RUF201, which rejects a code in a selector."""
    dest = tmp_path / "python"
    dest.mkdir()
    render("lang/python", dest, ANSWERS["python"])
    body = (dest / "ruff.toml").read_text()
    assert "preview = true" in body

    # Read the selector list, not the file: a comment may name the rejected code.
    selectors = [line for line in body.splitlines() if line.startswith('"tests/**"')]
    assert selectors, "the tests/** ignore is absent"
    assert '"S101"' not in selectors[0], "RUF201 rejects a rule code in a selector"
    assert '"assert"' in selectors[0]


# A layer with its own test file rather than a row in ANSWERS. The parametrised cases here
# assume a compiler and a package manager, which a contract has neither of, so lang/api is
# covered by tests/test_api_layer.py against vacuum and oasdiff instead.
COVERED_ELSEWHERE = {"api": "tests/test_api_layer.py"}

# Which generator each language layer renders over, and how its output is normalised so the
# gate passes before a line of real code exists. Three of the four generators produce a tree
# that FAILS the gate they ship with, each found by running it rather than reading:
#
#   cargo init      rust.missing_docs and clippy.pedantic both fire on the generated pub fn
#                   under CI's -D warnings, so both are left out of the manifest
#   uv init --lib   writes a function into src/<pkg>/__init__.py, which
#                   non-empty-init-module rejects, so a task splits it into core.py
#   bun init        writes index.ts with no trailing newline, which biome's formatter
#                   rejects, so a task runs `biome check --write` once
#   go mod init     the only one that produces a clean tree, so it needs no task
#
# A fifth language will hit its own version of this. The entry is required, and `None` is a
# positive claim that the generator needs nothing rather than an omission.
GENERATOR_NORMALISATION = {
    "rust": "tasks/patch_manifest.py",
    "python": "tasks/split_init.py",
    "ts": "tasks/add_dev_deps.py",
    "go": None,
}


def test_every_language_layer_is_covered_somewhere() -> None:
    """A new lang/* layer is either in ANSWERS or has its own file, or it ships untested."""
    on_disk = {p.parent.name for p in RECIPES.rglob("copier.yml")}
    untested = on_disk - set(ANSWERS) - set(COVERED_ELSEWHERE)
    assert not untested, f"untested language layers: {untested}"

    # A layer claiming coverage elsewhere has to actually have it, or this exemption
    # becomes a way to ship an untested layer.
    for layer, path in COVERED_ELSEWHERE.items():
        assert layer in on_disk, f"{layer} is exempted but no longer exists"
        assert (REPO_ROOT / path).is_file(), f"{layer} claims coverage in {path}, which is absent"


# --- lang/python's __init__ split ------------------------------------------


def uv_init(path: Path) -> None:
    """A real `uv init --lib`, so the test sees what a user would."""
    subprocess.run(
        ["uv", "init", "--lib", "--name", "demo", "-q"],
        cwd=path,
        check=True,
        capture_output=True,
    )


def test_the_init_body_moves_into_core(tmp_path: Path) -> None:
    """`uv init --lib` fills __init__.py, which non-empty-init-module rejects."""
    dest = tmp_path / "d"
    dest.mkdir()
    uv_init(dest)
    assert "def hello" in (dest / "src" / "demo" / "__init__.py").read_text()

    render("lang/python", dest, ANSWERS["python"])

    init = (dest / "src" / "demo" / "__init__.py").read_text()
    core = (dest / "src" / "demo" / "core.py").read_text()
    assert "def hello" not in init
    assert "from demo.core import hello" in init
    assert "def hello" in core


def test_splitting_the_init_is_idempotent(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    uv_init(dest)
    render("lang/python", dest, ANSWERS["python"])
    first = (dest / "src" / "demo" / "__init__.py").read_text()

    render("lang/python", dest, ANSWERS["python"])

    assert (dest / "src" / "demo" / "__init__.py").read_text() == first


def test_an_existing_core_is_not_clobbered(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    uv_init(dest)
    core = dest / "src" / "demo" / "core.py"
    core.write_text('"""Mine."""\n\n\ndef existing() -> None:\n    pass\n')

    result = render("lang/python", dest, ANSWERS["python"])

    assert result.returncode == 0
    assert "existing" in core.read_text()
    assert "already exists" in result.stdout


def test_the_init_ignore_is_gone(tmp_path: Path) -> None:
    """The split removes the need for it, and an unused ignore hides a real finding."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/python", dest, ANSWERS["python"])
    assert "non-empty-init-module" not in (dest / "ruff.toml").read_text()


# --- lang/go ---------------------------------------------------------------


def test_golangci_uses_the_v2_schema(tmp_path: Path) -> None:
    """A v1 config fails outright: "unsupported version of the configuration"."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/go", dest, ANSWERS["go"])
    config = yaml.safe_load((dest / ".golangci.yml").read_text())

    assert config["version"] == "2"
    # v1 put settings at the top level; v2 rejects that key by name.
    assert "linters-settings" not in config
    assert "settings" in config["linters"]


def test_gosec_and_revive_are_enabled(tmp_path: Path) -> None:
    """gosec ships inside golangci-lint and the standard set leaves it off, so a
    config without this line has no security lint at all."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/go", dest, ANSWERS["go"])
    enabled = yaml.safe_load((dest / ".golangci.yml").read_text())["linters"]["enable"]
    assert "gosec" in enabled
    assert "revive" in enabled


def test_vendor_is_ignored_unless_committed(tmp_path: Path) -> None:
    off = tmp_path / "off"
    off.mkdir()
    render("lang/go", off, ANSWERS["go"])
    assert "vendor/" in (off / ".gitignore.d" / "go").read_text()

    on = tmp_path / "on"
    on.mkdir()
    render("lang/go", on, ANSWERS["go"].replace("go_vendor: false", "go_vendor: true"))
    body = (on / ".gitignore.d" / "go").read_text()
    assert not any(line.strip() == "vendor/" for line in body.splitlines())


# --- lang/ts ---------------------------------------------------------------


def test_biome_lints_nothing_oxlint_covers(tmp_path: Path) -> None:
    """Both linting would report one finding twice, with nothing to de-duplicate."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/ts", dest, ANSWERS["ts"])
    rules = json.loads((dest / "biome.json").read_text())["linter"]["rules"]

    # `recommended` is deprecated in biome 2.5; `preset` replaced it.
    assert "recommended" not in rules
    assert rules["preset"] == "none"


def test_biome_owns_formatting_and_assists(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/ts", dest, ANSWERS["ts"])
    config = json.loads((dest / "biome.json").read_text())
    assert config["formatter"]["enabled"] is True
    assert config["assist"]["actions"]["source"]["organizeImports"] == "on"


def test_type_aware_linting_declares_its_package(tmp_path: Path) -> None:
    """oxlint fails with "Failed to find tsgolint executable" without it."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/ts", dest, ANSWERS["ts"])
    assert json.loads((dest / ".oxlintrc.json").read_text())["options"]["typeAware"] is True

    task = (REPO_ROOT / "recipes" / "lang" / "ts" / "tasks" / "add_dev_deps.py").read_text()
    assert "oxlint-tsgolint" in task


def test_type_aware_can_be_turned_off(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    render("lang/ts", dest, ANSWERS["ts"].replace("ts_typeaware: true", "ts_typeaware: false"))
    assert "options" not in json.loads((dest / ".oxlintrc.json").read_text())


def test_a_generated_tsconfig_is_not_overwritten(tmp_path: Path) -> None:
    """bun init and better-t-stack both write one, and theirs wins."""
    dest = tmp_path / "d"
    dest.mkdir()
    (dest / "package.json").write_text('{"name": "demo"}\n')
    (dest / "tsconfig.json").write_text('{"compilerOptions": {"strict": false}}\n')

    render("lang/ts", dest, ANSWERS["ts"])

    assert '"strict": false' in (dest / "tsconfig.json").read_text()


def test_a_language_layer_declares_how_its_generator_output_is_normalised() -> None:
    """A new lang/* layer cannot land without saying what its generator leaves broken.

    Three of the four generators produce a tree that fails the gate the layer ships. That
    was found by running each generator, not by reading its output, and a fifth language
    will have its own version of it. This is the checklist the bead asks for, enforced.
    """
    on_disk = {p.parent.name for p in RECIPES.rglob("copier.yml")}
    # lang/api has no generator: a contract is authored rather than scaffolded.
    languages = on_disk - set(COVERED_ELSEWHERE)

    undeclared = languages - set(GENERATOR_NORMALISATION)
    assert not undeclared, (
        f"these layers declare no generator normalisation: {undeclared}. Run the generator, "
        "run `just check` on its output, and record what had to be fixed."
    )

    for language, task in GENERATOR_NORMALISATION.items():
        if language not in languages:
            continue
        config = yaml.safe_load((RECIPES / language / "copier.yml").read_text())
        tasks = " ".join(config.get("_tasks") or [])
        if task is None:
            # A claim that the generator needs nothing, which only holds while it stays true.
            continue
        assert task in tasks, (
            f"lang/{language} claims {task} normalises its generator output, but its "
            "_tasks do not run it"
        )


def test_a_language_layer_contributes_both_shared_job_fragments() -> None:
    """The host layer's quality and security workflows build their matrices by reading these
    directories at run time, so a language contributes its jobs by dropping a file.

    Absence is stated rather than implied. `codeql.supported: false` is a claim someone made
    about a language CodeQL cannot extract; a missing file is indistinguishable from a layer
    nobody finished. lang/api shipped without a security fragment until this test existed.
    """
    for layer in sorted(RECIPES.iterdir()):
        if not (layer / "copier.yml").is_file():
            continue
        template = layer / "template" / ".github"
        for kind in ("quality.d", "security.d"):
            found = list((template / kind).glob("*.yml")) if (template / kind).is_dir() else []
            assert found, f"lang/{layer.name} contributes no .github/{kind} fragment"

        security = yaml.safe_load(next((template / "security.d").glob("*.yml")).read_text())
        # Every key the discovery step reads has to be present, or a scan is skipped silently
        # rather than declared unsupported.
        assert "codeql" in security, f"lang/{layer.name} does not state its CodeQL support"
        # An omitted opengrep key is indistinguishable from a layer nobody finished, where an
        # empty pack list is a claim that the language has no rules worth running.
        assert "opengrep" in security, f"lang/{layer.name} does not state its opengrep packs"
