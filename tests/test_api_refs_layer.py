"""docs/api-refs: the reference harness, not someone else's extractors.

The prior art in prompting-press is 2,622 lines across three extractors, carrying 35
project-specific references and hardcoded `packages/python` paths, and its rust extractor pins
`nightly-2026-05-15` because rustdoc's JSON schema is unstable and nightly-only. Porting that
verbatim would ship one project's layout and one project's toolchain pin as everyone's.

So the layer ships the orchestrator, the freshness gate, the recipes, and one documented stub
per language emitting valid empty IR. That is the same split every other layer uses:
`iac/terraform` ships a starter module rather than someone's infrastructure.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import mise_bin

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

ANSWERS = 'api_ref_languages: ["rust", "python", "ts"]\napi_ref_section: reference\n'
# Resolved through mise rather than an installs/node/latest path. See conftest.mise_bin.
NODE_BIN = mise_bin("node")

needs_node = pytest.mark.skipif(
    shutil.which("node") is None and (NODE_BIN is None or not (NODE_BIN / "node").is_file()),
    reason="node absent",
)


def node_env() -> dict[str, str]:
    env = dict(os.environ)
    if NODE_BIN is not None and NODE_BIN.is_dir():
        env["PATH"] = f"{NODE_BIN}:{env['PATH']}"
    return env


def render(dest: Path, answers: str = ANSWERS) -> subprocess.CompletedProcess[str]:
    answers_file = dest.parent / f"{dest.name}-answers.yml"
    answers_file.write_text(answers)
    return subprocess.run(
        [sys.executable, str(RENDER), "docs/api-refs", str(dest), "--answers", str(answers_file)],
        capture_output=True,
        text=True,
        check=False,
    )


def run(dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=dest, capture_output=True, text=True, check=False, env=node_env(), timeout=300
    )


@pytest.fixture
def api_refs(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render(dest)
    assert result.returncode == 0, result.stderr
    (dest / "docs" / "site" / "src" / "content" / "docs").mkdir(parents=True, exist_ok=True)
    return dest


def page(dest: Path, language: str) -> Path:
    return dest / "docs" / "site" / "src" / "content" / "docs" / "reference" / f"{language}.mdx"


# --- what renders ----------------------------------------------------------


def test_the_harness_renders(api_refs: Path) -> None:
    scripts = api_refs / "docs" / "site" / "scripts"
    assert (scripts / "gen-api-refs.mjs").is_file()
    assert (scripts / "check-api-refs-fresh.sh").is_file()
    assert (scripts / "check-api-refs-fresh.sh").stat().st_mode & 0o111


def test_only_the_selected_languages_get_an_extractor(tmp_path: Path) -> None:
    """A language whose layer never rendered has no source to extract from."""
    dest = tmp_path / "two"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render(dest, 'api_ref_languages: ["rust"]\napi_ref_section: reference\n').returncode == 0

    scripts = dest / "docs" / "site" / "scripts"
    assert (scripts / "extract-rust-api.mjs").is_file()
    assert not (scripts / "extract-python-api.py").exists()
    assert not (scripts / "extract-ts-api.mjs").exists()


def test_each_stub_records_its_language_constraint(api_refs: Path) -> None:
    """The constraint is the expensive part of writing a real extractor, and each is different.

    rustdoc's JSON is nightly-only and its schema changes between nightlies, which is why the
    scaffold ships no pin: the right nightly is whichever one the extractor was written
    against.
    """
    scripts = api_refs / "docs" / "site" / "scripts"

    rust = (scripts / "extract-rust-api.mjs").read_text()
    assert "nightly" in rust
    assert "UNSTABLE" in rust or "unstable" in rust
    # No pin shipped: a scaffold cannot know which nightly a future extractor needs.
    assert "nightly-2026" not in rust

    python = (scripts / "extract-python-api.py").read_text()
    assert "griffe" in python
    # Reads statically, so a module with an import-time side effect cannot run during a build.
    assert "import" in python and "side effect" in python

    ts = (scripts / "extract-ts-api.mjs").read_text()
    assert "typedoc" in ts
    assert "excludeInternal" in ts


# --- the IR contract -------------------------------------------------------


@needs_node
def test_every_stub_emits_valid_ir(api_refs: Path) -> None:
    """A stub that emits nothing usable makes the harness untestable until someone writes a
    real extractor, which is exactly when a broken harness is most expensive."""
    scripts = api_refs / "docs" / "site" / "scripts"

    for language, argv in (
        ("rust", ("node", str(scripts / "extract-rust-api.mjs"))),
        ("ts", ("node", str(scripts / "extract-ts-api.mjs"))),
        ("python", (sys.executable, str(scripts / "extract-python-api.py"))),
    ):
        result = run(api_refs, *argv)
        assert result.returncode == 0, result.stderr
        ir = json.loads(result.stdout)
        assert ir["language"] == language
        assert ir["groups"] == []


@needs_node
def test_the_orchestrator_writes_a_page_per_extractor(api_refs: Path) -> None:
    result = run(api_refs, "node", "docs/site/scripts/gen-api-refs.mjs")
    assert result.returncode == 0, result.stdout + result.stderr

    for language in ("rust", "python", "ts"):
        body = page(api_refs, language).read_text()
        assert body.startswith("---"), "frontmatter must open the file"
        # A reader who finds a stale page needs to know it is derived rather than authored.
        assert "Generated by docs/site/scripts/gen-api-refs.mjs" in body


@needs_node
def test_an_undocumented_symbol_fails_rather_than_rendering_blank(api_refs: Path) -> None:
    """A reference page with blank descriptions reads as complete while documenting nothing."""
    extractor = api_refs / "docs" / "site" / "scripts" / "extract-rust-api.mjs"
    extractor.write_text(
        "const ir = { language: 'rust', groups: [{ title: 'Parsing', symbols: ["
        "{ name: 'parse', signature: 'pub fn parse()', doc: 'Parses.' },"
        "{ name: 'bare', signature: 'pub fn bare()', doc: '' }]}]};\n"
        "process.stdout.write(JSON.stringify(ir));\n"
    )
    result = run(api_refs, "node", "docs/site/scripts/gen-api-refs.mjs")
    assert result.returncode == 1
    # Named, so the fix is obvious.
    assert "Parsing/bare" in result.stderr


@needs_node
def test_a_stray_print_is_reported_as_such(api_refs: Path) -> None:
    """The usual way an extractor breaks, and a bare JSON parse error would not say so."""
    extractor = api_refs / "docs" / "site" / "scripts" / "extract-rust-api.mjs"
    extractor.write_text("console.log('debugging');\nprocess.stdout.write('{}');\n")

    result = run(api_refs, "node", "docs/site/scripts/gen-api-refs.mjs")
    assert result.returncode == 1
    assert "did not emit JSON" in result.stderr


# --- the freshness gate ----------------------------------------------------


@needs_node
def test_check_passes_on_a_current_tree(api_refs: Path) -> None:
    assert run(api_refs, "node", "docs/site/scripts/gen-api-refs.mjs").returncode == 0
    assert run(api_refs, "node", "docs/site/scripts/gen-api-refs.mjs", "--check").returncode == 0


@needs_node
def test_check_reports_a_stale_page_without_repairing_it(api_refs: Path) -> None:
    """A gate that fixes what it checks leaves a dirty tree and passes on the rerun."""
    assert run(api_refs, "node", "docs/site/scripts/gen-api-refs.mjs").returncode == 0

    target = page(api_refs, "rust")
    target.write_text(target.read_text().replace("rust API", "TAMPERED"))

    result = run(api_refs, "node", "docs/site/scripts/gen-api-refs.mjs", "--check")
    assert result.returncode == 1
    assert "reference/rust.mdx" in result.stderr
    assert "just api-refs" in result.stderr
    assert "TAMPERED" in target.read_text(), "--check must not rewrite the tree"


@needs_node
def test_the_gate_checks_determinism_too(api_refs: Path) -> None:
    """A renderer that iterates a hash map or embeds a timestamp produces a different page each
    run, which makes every commit carry a reference diff and the staleness check meaningless.
    """
    assert run(api_refs, "node", "docs/site/scripts/gen-api-refs.mjs").returncode == 0

    result = run(api_refs, "bash", "docs/site/scripts/check-api-refs-fresh.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "determinism" in result.stdout


@needs_node
def test_a_repo_with_no_extractor_yet_passes_the_gate(tmp_path: Path) -> None:
    """The state between selecting this layer and writing the first extractor.

    The determinism step diffed a page directory that no render had created, which reported a
    nondeterministic generator. That is both wrong and unfixable: there is nothing to make
    deterministic.
    """
    dest = tmp_path / "bare"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render(dest, "api_ref_languages: []\napi_ref_section: reference\n").returncode == 0

    result = run(dest, "bash", "docs/site/scripts/check-api-refs-fresh.sh")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "not deterministic" not in result.stderr


# --- the recipes -----------------------------------------------------------


def test_the_recipes_render(api_refs: Path) -> None:
    fragment = (api_refs / ".just.d" / "api-refs.just").read_text()
    assert "api-refs:" in fragment
    assert "api-refs-check:" in fragment
    # just's own parameter survived rendering.
    assert "api-refs-ir lang:" in fragment
    assert 'api_ref_section := "reference"' in fragment
