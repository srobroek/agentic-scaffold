"""agentic/marketplace: reads the finished tree and reports, writing nothing.

The layer's value is an absence, and an absence is invisible in a render log, so the
tests assert it directly: no per-harness configuration file may appear, and the only
thing written is the answers file copier itself creates.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

RUST = 'crate_kind: bin\nrust_edition: "2024"\nlicense: Apache-2.0\n'
TERRAFORM = """\
project_name: demo
environments: [dev, prod]
aws_region: eu-west-1
state_bucket: demo-tofu-state
default_branch: main
"""
INDEX = 'index_languages: ["rust"]\nindex_extra_ignores: []\n'
APM = """\
project_name: demo
description: A demo project
apm_packages:
  - "srobroek/agentic-packages/packages/core#>=1.0.0 <2.0.0"
apm_target: "claude,codex"
apm_cli_version: "0.26.0"
"""

# Every file the layer must never write. Per-harness configuration comes from a
# marketplace, which is machine-global rather than per-repository.
FORBIDDEN = (
    ".claude/settings.json",
    ".mcp.json",
    ".codex/config.toml",
    "marketplace.json",
    ".claude-plugin/marketplace.json",
    "opencode.json",
    ".kiro",
)


def render(layer: str, dest: Path, answers: str = "") -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(RENDER), layer, str(dest)]
    if answers:
        answers_file = dest.parent / f"{dest.name}-{layer.replace('/', '-')}.yml"
        answers_file.write_text(answers)
        argv += ["--answers", str(answers_file)]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


@pytest.fixture
def bare(tmp_path: Path) -> Path:
    dest = tmp_path / "bare"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    return dest


def report(dest: Path) -> str:
    result = render("agentic/marketplace", dest)
    assert result.returncode == 0, result.stderr
    return result.stdout


# --- it writes nothing -----------------------------------------------------


def test_no_per_harness_configuration_is_written(bare: Path) -> None:
    """The acceptance criterion, asserted as an absence."""
    report(bare)
    for name in FORBIDDEN:
        assert not (bare / name).exists(), f"the layer wrote {name}"


def test_only_the_answers_file_is_created(bare: Path) -> None:
    report(bare)
    written = {
        str(path.relative_to(bare))
        for path in bare.rglob("*")
        if path.is_file() and ".git/" not in str(path.relative_to(bare))
    }
    assert written == {".copier-answers.marketplace.yml"}


def test_the_report_says_it_wrote_nothing(bare: Path) -> None:
    """Stated out loud, because an absence cannot be seen in a render log."""
    output = report(bare)
    assert "nothing was written" in output
    assert ".claude/settings.json" in output, "the report names what it did not write"


# --- what it recommends ----------------------------------------------------


def test_the_marketplaces_are_named_with_the_command(bare: Path) -> None:
    """Registration is machine-global, so no template can seed it and the report has to
    give the one-time command."""
    output = report(bare)
    assert "apm marketplace add srobroek/agentic-packages" in output
    assert "apm marketplace add srobroek/slopvac" in output


def test_a_bare_tree_recommends_only_the_universal_packages(bare: Path) -> None:
    output = report(bare)
    assert "packages/write-docs" in output
    assert "packages/core" in output
    # Nothing language-specific, because no language layer rendered.
    assert "language-rust" not in output
    assert "steering-infrastructure" not in output


def test_a_rendered_language_layer_earns_its_packages(bare: Path) -> None:
    assert render("lang/rust", bare, RUST).returncode == 0
    output = report(bare)
    assert "language-rust" in output
    assert "rust-quality" in output
    assert "language-python" not in output


def test_terraform_earns_the_infrastructure_steering(bare: Path) -> None:
    """The layer's own files carry no steering, so the package is what supplies it."""
    assert render("iac/terraform", bare, TERRAFORM).returncode == 0
    assert "steering-infrastructure" in report(bare)


def test_the_index_layer_earns_a_required_package(bare: Path) -> None:
    """token-savings guards a whole-file read of the pack, which costs six context
    windows on a large repository, so the report marks it required rather than suggested.
    """
    assert render("agentic/index", bare, INDEX).returncode == 0
    output = report(bare)
    assert "token-savings" in output
    assert "REQUIRED" in output


def test_detection_reads_the_tree_rather_than_the_answers(bare: Path) -> None:
    """A layer whose files were removed by hand should stop being recommended against.

    The tree is what an agent will find, so it is what the report follows.
    """
    assert render("lang/rust", bare, RUST).returncode == 0
    assert "language-rust" in report(bare)

    (bare / "rust-toolchain.toml").unlink()
    # The answers file still records that lang/rust was rendered.
    assert (bare / ".copier-answers.rust.yml").is_file()
    assert "language-rust" not in report(bare)


def test_a_package_already_in_apm_yml_is_not_repeated(bare: Path) -> None:
    """The report is a list of what to add, so naming what is already there is noise."""
    assert render("agentic/apm", bare, APM).returncode == 0
    output = report(bare)
    assert "already names 1 package(s)" in output
    # `core` is in apm.yml, so it drops out of the add list while write-docs stays.
    add_block = output.partition("Add these")[2]
    assert "packages/core" not in add_block
    assert "write-docs" in add_block


def test_nothing_to_add_is_said_plainly(bare: Path) -> None:
    manifest = """\
project_name: demo
description: A demo project
apm_packages:
  - "srobroek/slopvac/packages/write-docs#>=1.0.0"
  - "srobroek/agentic-packages/packages/core#>=1.0.0"
apm_target: "claude,codex"
apm_cli_version: "0.26.0"
"""
    assert render("agentic/apm", bare, manifest).returncode == 0
    assert "already in apm.yml" in report(bare)


def test_it_runs_after_the_aggregating_layers(bare: Path) -> None:
    """It reads the finished tree, so a recommendation made earlier is about nothing."""
    import yaml

    config = yaml.safe_load(
        (REPO_ROOT / "templates" / "agentic" / "marketplace" / "copier.yml").read_text()
    )
    after = config["_scaffold"]["after"]
    assert "base/gitignore" in after
    assert "workspace/just" in after
