"""release/goreleaser: what a tag publishes.

The division of labour is the whole design. release-please computes the next version from
the Conventional Commit subjects, writes the changelog, and pushes the tag. goreleaser reacts
to that tag and attaches the artefacts. Neither knows how to do the other's job, which is why
they are separate layers rather than one.

Verified against goreleaser 2.17.1 rather than read: `checksums` is rejected outright (the
key is `checksum`), and a snapshot build produced four cross-compiled binaries plus a
checksums file from one runner, with the version reaching the binary through ldflags.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

ANSWERS = 'project_name: demoapp\ngoreleaser_main: "."\ngo_version: "1.26"\n'

GORELEASER = Path.home() / ".local/share/mise/installs/goreleaser/2.17.1/goreleaser"
GO_BIN = Path.home() / ".local/share/mise/installs/go/latest/bin"

needs_goreleaser = pytest.mark.skipif(
    not GORELEASER.is_file() and shutil.which("goreleaser") is None,
    reason="goreleaser absent",
)


def goreleaser_bin() -> str:
    return str(GORELEASER) if GORELEASER.is_file() else "goreleaser"


def go_env() -> dict[str, str]:
    env = dict(os.environ)
    if GO_BIN.is_dir():
        env["PATH"] = f"{GO_BIN}:{env['PATH']}"
    return env


def render(dest: Path) -> subprocess.CompletedProcess[str]:
    answers_file = dest.parent / f"{dest.name}-answers.yml"
    answers_file.write_text(ANSWERS)
    return subprocess.run(
        [
            sys.executable,
            str(RENDER),
            "release/goreleaser",
            str(dest),
            "--answers",
            str(answers_file),
        ],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def goreleaser(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    for key, value in (("user.email", "t@e.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(dest), "config", key, value], check=True)
    result = render(dest)
    assert result.returncode == 0, result.stderr
    return dest


@pytest.fixture
def buildable(goreleaser: Path) -> Path:
    """A real Go program plus a remote, both of which goreleaser requires."""
    (goreleaser / "go.mod").write_text("module demoapp\n\ngo 1.24\n")
    (goreleaser / "main.go").write_text(
        'package main\n\nimport "fmt"\n\nvar version = "dev"\n\n'
        'func main() { fmt.Println("demoapp", version) }\n'
    )
    # `scm releases: no remote configured to list refs from` without this.
    subprocess.run(
        [
            "git",
            "-C",
            str(goreleaser),
            "remote",
            "add",
            "origin",
            "https://github.com/srobroek/demoapp.git",
        ],
        check=True,
        capture_output=True,
    )
    subprocess.run(["git", "-C", str(goreleaser), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(goreleaser), "commit", "-q", "-m", "init"],
        check=True,
        capture_output=True,
    )
    return goreleaser


# --- the division of labour ------------------------------------------------


def test_release_please_keeps_the_changelog(goreleaser: Path) -> None:
    """release-please writes CHANGELOG.md from the commit subjects before the tag exists.
    goreleaser generating a second one from the same commits would publish two that disagree
    on formatting."""
    config = yaml.safe_load((goreleaser / ".goreleaser.yaml").read_text())
    assert config["changelog"]["disable"] is True


def test_the_release_is_appended_rather_than_created(goreleaser: Path) -> None:
    """release-please created the release and its notes; this only attaches artefacts."""
    config = yaml.safe_load((goreleaser / ".goreleaser.yaml").read_text())
    assert config["release"]["mode"] == "append"


def test_it_triggers_on_the_tag_rather_than_a_push(goreleaser: Path) -> None:
    """The tag is what release-please pushes, and it is the only signal that a version was
    decided."""
    workflow = yaml.safe_load((goreleaser / ".github" / "workflows" / "goreleaser.yml").read_text())
    assert list(workflow[True]) == ["push"]
    assert workflow[True]["push"]["tags"] == ["v*"]
    # Not on pull_request: a required check that only fires on a tag never reports on one.
    assert "pull_request" not in workflow[True]


# --- the config -----------------------------------------------------------


def test_the_checksum_key_is_singular(goreleaser: Path) -> None:
    """`checksums` is rejected outright: goreleaser reported `field checksums not found in
    type config.Project`, which is how the plural was found."""
    body = (goreleaser / ".goreleaser.yaml").read_text()
    config = yaml.safe_load(body)
    assert "checksum" in config
    assert "checksums" not in config


def test_cgo_is_disabled_so_every_target_cross_compiles(goreleaser: Path) -> None:
    """One runner builds all four targets. A dynamically linked binary would need a runner per
    platform."""
    config = yaml.safe_load((goreleaser / ".goreleaser.yaml").read_text())
    build = config["builds"][0]
    assert "CGO_ENABLED=0" in build["env"]
    assert set(build["goos"]) == {"linux", "darwin"}
    assert set(build["goarch"]) == {"amd64", "arm64"}


def test_the_targets_are_deduplicated(goreleaser: Path) -> None:
    """Four GOOS/GOARCH pairs collapse to two of each, since goreleaser takes them as separate
    lists and multiplies them."""
    config = yaml.safe_load((goreleaser / ".goreleaser.yaml").read_text())
    build = config["builds"][0]
    assert len(build["goos"]) == len(set(build["goos"]))
    assert len(build["goarch"]) == len(set(build["goarch"]))


def test_the_version_is_injected_through_ldflags(goreleaser: Path) -> None:
    """The version comes from the tag goreleaser was invoked on, which is the tag
    release-please pushed. A binary that cannot report its own version is unsupportable."""
    config = yaml.safe_load((goreleaser / ".goreleaser.yaml").read_text())
    flags = " ".join(config["builds"][0]["ldflags"])
    assert "-X main.version=" in flags
    assert "-s -w" in flags, "the symbol table and DWARF are most of a Go binary's size"


def test_the_release_workflow_does_not_cache(goreleaser: Path) -> None:
    """A poisoned cache entry would end up inside a binary users download, which zizmor
    reports as cache-poisoning. A release is infrequent, so a cold download costs seconds
    nobody waits on."""
    workflow = yaml.safe_load((goreleaser / ".github" / "workflows" / "goreleaser.yml").read_text())
    setup = next(
        s for s in workflow["jobs"]["publish"]["steps"] if "setup-go" in str(s.get("uses", ""))
    )
    assert setup["with"]["cache"] is False


def test_the_full_history_is_fetched(goreleaser: Path) -> None:
    """goreleaser derives the version and the previous tag from history, and a shallow clone
    has neither."""
    workflow = yaml.safe_load((goreleaser / ".github" / "workflows" / "goreleaser.yml").read_text())
    checkout = next(
        s for s in workflow["jobs"]["publish"]["steps"] if "checkout" in str(s.get("uses", ""))
    )
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False


def test_the_artefact_directory_is_ignored(goreleaser: Path) -> None:
    patterns = [
        line.strip()
        for line in (goreleaser / ".gitignore.d" / "goreleaser").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    assert "dist/" in patterns


# --- the real tool ---------------------------------------------------------


@needs_goreleaser
def test_goreleaser_accepts_the_rendered_config(buildable: Path) -> None:
    """`goreleaser check` is what caught the plural checksums key."""
    result = subprocess.run(
        [goreleaser_bin(), "check"],
        cwd=buildable,
        capture_output=True,
        text=True,
        check=False,
        env=go_env(),
        timeout=600,
    )
    assert result.returncode == 0, result.stdout[-1500:] + result.stderr[-1500:]


@needs_goreleaser
@pytest.mark.slow
def test_a_snapshot_builds_every_target(buildable: Path) -> None:
    """The bead's criterion: a Go project publishes binaries on tag. A snapshot is that
    without the publish, so it proves the build rather than the upload.
    """
    if shutil.which("go") is None and not (GO_BIN / "go").is_file():
        pytest.skip("go absent")

    result = subprocess.run(
        [goreleaser_bin(), "release", "--snapshot", "--clean", "--skip=publish"],
        cwd=buildable,
        capture_output=True,
        text=True,
        check=False,
        env=go_env(),
        timeout=1200,
    )
    assert result.returncode == 0, result.stdout[-2000:] + result.stderr[-2000:]

    archives = sorted((buildable / "dist").glob("*.tar.gz"))
    assert len(archives) == 4, f"expected four targets, got {[p.name for p in archives]}"
    assert (buildable / "dist" / "checksums.txt").is_file()
