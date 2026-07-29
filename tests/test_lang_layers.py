"""lang/* layers: every language ships the same eight file kinds."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"
TEMPLATES = REPO_ROOT / "templates" / "lang"

ANSWERS = {
    "rust": 'crate_kind: lib\nrust_edition: "2024"\n',
    "python": 'python_version: "3.13"\npython_layout: src\npython_framework: none\n',
    "go": 'go_module_path: github.com/srobroek/demo\ngo_version: "1.26"\ngo_vendor: false\n',
}


def render(layer: str, dest: Path, answers: str) -> subprocess.CompletedProcess[str]:
    answers_file = dest.parent / f"{dest.name}-answers.yml"
    answers_file.write_text(answers)
    return subprocess.run(
        [sys.executable, str(RENDER), layer, str(dest), "--answers", str(answers_file)],
        capture_output=True,
        text=True,
        check=False,
    )


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
def test_the_reusable_workflows_take_a_working_directory(
    language: str, tmp_path: Path
) -> None:
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
            assert all(c in "0123456789abcdef" for c in sha), (
                f"{path.name}: {sha} is not a hex SHA"
            )


@pytest.mark.parametrize("language", LANGUAGES)
def test_the_security_fragment_declares_codeql_support(
    language: str, tmp_path: Path
) -> None:
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
    selectors = [
        line for line in body.splitlines() if line.startswith('"tests/**"')
    ]
    assert selectors, "the tests/** ignore is absent"
    assert '"S101"' not in selectors[0], "RUF201 rejects a rule code in a selector"
    assert '"assert"' in selectors[0]


def test_every_language_layer_is_covered_here() -> None:
    """A new lang/* layer must be added to ANSWERS, or it ships untested."""
    on_disk = {p.parent.name for p in TEMPLATES.rglob("copier.yml")}
    assert on_disk == set(ANSWERS), f"untested language layers: {on_disk - set(ANSWERS)}"


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
