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

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import mise_bin, render_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent

ANSWERS = 'project_name: demoapp\norg: acme\ngoreleaser_main: "."\n'

GORELEASER = Path.home() / ".local/share/mise/installs/goreleaser/2.17.1/goreleaser"
# Resolved through mise. See conftest.mise_bin for why not an installs/<tool>/latest path.
GO_BIN = mise_bin("go") or Path("/nonexistent")

needs_goreleaser = pytest.mark.skipif(
    not GORELEASER.is_file() and shutil.which("goreleaser") is None,
    reason="goreleaser absent",
)


def goreleaser_bin() -> str:
    return str(GORELEASER) if GORELEASER.is_file() else "goreleaser"


def syft_dir() -> Path | None:
    """syft's own install directory, which holds the binary at its root rather than in bin/."""
    root = Path.home() / ".local/share/mise/installs/syft"
    if not root.is_dir():
        return None
    for candidate in sorted(root.iterdir(), reverse=True):
        if (candidate / "syft").is_file():
            return candidate
    return None


def go_env() -> dict[str, str]:
    env = dict(os.environ)
    if GO_BIN.is_dir():
        env["PATH"] = f"{GO_BIN}:{env['PATH']}"
    # goreleaser's sboms block shells out to syft and does not install it, which is exactly why
    # the workflow carries a download-syft step. A snapshot here fails the same way without it:
    # `exec: "syft": executable file not found in $PATH`, after the archives are already built.
    found = syft_dir()
    if found is not None:
        env["PATH"] = f"{found}:{env['PATH']}"
    return env


def render(dest: Path, answers: str = ANSWERS) -> subprocess.CompletedProcess[str]:
    return render_recipe("release/goreleaser", dest, answers)


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
    if syft_dir() is None and shutil.which("syft") is None:
        pytest.skip("syft absent, and the rendered config catalogues an SBOM per archive")

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

    # One SBOM per archive, named beside it. That naming is what the workflow's pairing check
    # relies on, so it is asserted against the real tool rather than assumed.
    for archive in archives:
        sbom = archive.with_name(f"{archive.name}.sbom.json")
        assert sbom.is_file(), f"no SBOM beside {archive.name}"

    document = json.loads(archives[0].with_name(f"{archives[0].name}.sbom.json").read_text())
    assert document["spdxVersion"] == "SPDX-2.3"
    assert document["packages"], "an SBOM naming no packages describes nothing"


# --- SBOM and provenance ---------------------------------------------------


def gr_workflow(dest: Path) -> dict:
    return yaml.safe_load((dest / ".github" / "workflows" / "goreleaser.yml").read_text())


def test_an_sbom_is_produced_per_archive(goreleaser: Path) -> None:
    """`artifacts: archive`, not `binary`: the archive is what a user downloads, so it is what
    an SBOM should describe. Measured with syft 1.50.0 against the rendered config: four
    archives produced four valid SPDX-2.3 documents, ~3.8KB each, named
    `<archive>.sbom.json` beside their archive."""
    config = yaml.safe_load((goreleaser / ".goreleaser.yaml").read_text())
    assert config["sboms"] == [{"artifacts": "archive"}]


def test_syft_is_installed_before_the_publish(goreleaser: Path) -> None:
    """goreleaser shells out to syft and does not install it, so without this the release
    fails at the cataloguing step with the binaries already built."""
    steps = gr_workflow(goreleaser)["jobs"]["publish"]["steps"]
    syft = next(i for i, s in enumerate(steps) if "download-syft" in str(s.get("uses", "")))
    publish = next(i for i, s in enumerate(steps) if s.get("name") == "Publish")
    assert syft < publish


def test_an_empty_sbom_set_fails_the_release(goreleaser: Path) -> None:
    """An sboms block that produced nothing is a silent downgrade to no SBOM at all, and the
    release would otherwise succeed looking attested. Verified by running the rendered script:
    an empty dist/ exits 1 with the message, a paired archive passes, and an SBOM whose
    subject is missing exits 1 naming the file."""
    steps = gr_workflow(goreleaser)["jobs"]["publish"]["steps"]
    check = next(s for s in steps if s.get("name") == "Check that the SBOMs exist")
    body = check["run"]
    assert "holds no .sbom.json" in body
    assert "no subject artefact for" in body
    # The `+x` form, not a length: under `set -u` an empty array reads as unbound on the
    # runner's bash, which aborted with "unbound variable" before reaching the message.
    assert "${sboms[*]+x}" in body


def test_the_provenance_covers_every_published_file(goreleaser: Path) -> None:
    """Including the SBOMs. They are release assets, so a consumer who trusts the provenance
    of an archive should be able to trust the document describing it."""
    steps = gr_workflow(goreleaser)["jobs"]["publish"]["steps"]
    attest = next(s for s in steps if "attest-build-provenance" in str(s.get("uses", "")))
    subjects = attest["with"]["subject-path"].split()
    assert "dist/*.tar.gz" in subjects
    assert "dist/*.zip" in subjects
    assert "dist/*.sbom.json" in subjects
    assert "dist/checksums.txt" in subjects


def test_the_provenance_follows_the_publish(goreleaser: Path) -> None:
    """The subject is a digest, and a digest exists only once the artefact does. Attesting a
    path that has not been built produces a bundle for a file nobody downloads."""
    steps = gr_workflow(goreleaser)["jobs"]["publish"]["steps"]
    publish = next(i for i, s in enumerate(steps) if s.get("name") == "Publish")
    attest = next(
        i for i, s in enumerate(steps) if "attest-build-provenance" in str(s.get("uses", ""))
    )
    assert attest > publish


def test_there_is_no_separate_sbom_attestation(goreleaser: Path) -> None:
    """`actions/attest-sbom` warns it is deprecated in favour of `actions/attest`, and both
    take `sbom-path` as ONE file capped at 16MB while goreleaser writes one per archive. A
    composite action cannot loop, so covering four archives would need a matrix job, which
    means uploading and re-downloading dist/ to attest what this job already holds."""
    uses = [str(s.get("uses", "")) for s in gr_workflow(goreleaser)["jobs"]["publish"]["steps"]]
    assert not any("attest-sbom" in u or "actions/attest@" in u for u in uses)


def test_the_attestation_permissions_are_granted(goreleaser: Path) -> None:
    """id-token mints the short-lived signing certificate from the workflow's OIDC token, and
    attestations writes the bundle to the repository's store."""
    permissions = gr_workflow(goreleaser)["jobs"]["publish"]["permissions"]
    assert permissions["id-token"] == "write"
    assert permissions["attestations"] == "write"


def test_the_sbom_can_be_turned_off(tmp_path: Path) -> None:
    """Nothing else in the layer depends on it, so off means no syft step, no attestation, and
    neither extra permission requested."""
    dest = tmp_path / "off"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render(dest, ANSWERS + "goreleaser_sbom: false\n")
    assert result.returncode == 0, result.stderr

    config = yaml.safe_load((dest / ".goreleaser.yaml").read_text())
    assert "sboms" not in config

    job = gr_workflow(dest)["jobs"]["publish"]
    assert job["permissions"] == {"contents": "write"}
    assert not any("attest" in str(s.get("uses", "")) for s in job["steps"])
    assert not any("syft" in str(s.get("uses", "")) for s in job["steps"])


@needs_goreleaser
@pytest.mark.slow
def test_goreleaser_accepts_the_config_with_sboms(buildable: Path) -> None:
    """`goreleaser check` against the rendered config, SBOMs included."""
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


def test_mise_supplies_syft_when_sboms_are_on(goreleaser: Path) -> None:
    """A local `just release-snapshot` runs goreleaser without the workflow's install step, so
    without this it fails at the cataloguing stage with the archives already built. Reproduced
    exactly that way while writing these tests."""
    import tomllib

    fragment = goreleaser / ".mise" / "conf.d" / "goreleaser.toml"
    tools = tomllib.loads(fragment.read_text())["tools"]
    assert tools["syft"]
    assert tools["goreleaser"]


def test_mise_omits_syft_when_sboms_are_off(tmp_path: Path) -> None:
    import tomllib

    dest = tmp_path / "nosbom"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render(dest, ANSWERS + "goreleaser_sbom: false\n")
    assert result.returncode == 0, result.stderr

    tools = tomllib.loads((dest / ".mise" / "conf.d" / "goreleaser.toml").read_text())["tools"]
    assert "syft" not in tools
