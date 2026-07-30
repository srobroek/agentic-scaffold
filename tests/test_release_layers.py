"""release/*: release-please, cocogitto, and the dependency-update tools."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

RP_ANSWERS = """\
release_type: rust
initial_version: 0.1.0
default_branch: main
release_packages: []
"""

COG_ANSWERS = "initial_version: 0.1.0\nrelease_scopes: []\n"

DU_ANSWERS = """\
default_branch: main
auto_merge: true
renovate_timezone: "Europe/Amsterdam"
"""

MONOREPO_ANSWERS = 'layout: rust\nproject_name: demo\nmembers: ""\nrust_edition: "2024"\n'


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
    for key, value in (
        ("user.email", "t@e.com"),
        ("user.name", "T"),
        ("commit.gpgsign", "false"),
        ("tag.gpgsign", "false"),
    ):
        subprocess.run(["git", "-C", str(path), "config", key, value], check=True)
    return path


needs_cargo = pytest.mark.skipif(shutil.which("cargo") is None, reason="cargo absent")


# --- release/release-please ------------------------------------------------


@pytest.fixture
def release_please(tmp_path: Path) -> Path:
    dest = git_repo(tmp_path / "rp")
    result = render("release/release-please", dest, RP_ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def config(dest: Path) -> dict:
    return json.loads((dest / "release-please-config.json").read_text())


def manifest(dest: Path) -> dict:
    return json.loads((dest / ".release-please-manifest.json").read_text())


def test_both_release_please_files_are_valid_json(release_please: Path) -> None:
    assert config(release_please)["release-type"] == "rust"
    assert manifest(release_please) == {".": "0.1.0"}


def test_a_single_package_repo_releases_the_root(release_please: Path) -> None:
    """`include-component-in-tag` off means a plain `v1.2.3` rather than `name-v1.2.3`."""
    spec = config(release_please)
    assert spec["packages"] == {".": {}}
    assert spec["include-component-in-tag"] is False


def test_release_packages_render_as_components(tmp_path: Path) -> None:
    dest = git_repo(tmp_path / "rp")
    render(
        "release/release-please",
        dest,
        RP_ANSWERS.replace(
            "release_packages: []",
            'release_packages:\n  - "crates/api"\n  - "crates/core"\n',
        ),
    )
    spec = config(dest)
    assert spec["packages"] == {
        "crates/api": {"component": "api"},
        "crates/core": {"component": "core"},
    }
    # Without this every member's tag would collide on one version number.
    assert spec["include-component-in-tag"] is True
    assert manifest(dest) == {"crates/api": "0.1.0", "crates/core": "0.1.0"}


def test_the_manifest_is_not_overwritten(release_please: Path) -> None:
    """release-please owns the recorded versions after the first release.

    A re-render resetting each one to initial_version would make it re-release
    versions that already shipped.
    """
    path = release_please / ".release-please-manifest.json"
    path.write_text('{\n  ".": "4.5.6"\n}\n')

    render("release/release-please", release_please, RP_ANSWERS)

    assert manifest(release_please) == {".": "4.5.6"}


def test_the_release_workflow_does_not_ride_the_gate(release_please: Path) -> None:
    """It needs contents and pull-requests write, which the gate deliberately lacks."""
    spec = yaml.safe_load(
        (release_please / ".github" / "workflows" / "release-please.yml").read_text()
    )
    if True in spec:  # YAML 1.1 reads a bare `on` as boolean true
        spec["on"] = spec.pop(True)

    assert list(spec["on"]) == ["push"]
    assert spec["permissions"] == {"contents": "read"}
    job = spec["jobs"]["release-please"]
    assert job["permissions"]["contents"] == "write"
    assert job["permissions"]["pull-requests"] == "write"
    assert "timeout-minutes" in job


# --- release/cocogitto -----------------------------------------------------


@pytest.fixture
def cocogitto(tmp_path: Path) -> Path:
    dest = git_repo(tmp_path / "cog")
    result = render("release/cocogitto", dest, COG_ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def test_cog_toml_parses(cocogitto: Path) -> None:
    import tomllib

    spec = tomllib.loads((cocogitto / "cog.toml").read_text())
    assert spec["ignore_merge_commits"] is True
    # One tag per package is what makes a monorepo member releasable on its own.
    assert spec["generate_mono_repository_package_tags"] is True


def test_cog_installs_no_git_hooks(cocogitto: Path) -> None:
    """prek owns .git/hooks/, and two managers writing it means the last one wins."""
    import tomllib

    assert tomllib.loads((cocogitto / "cog.toml").read_text())["git_hooks"] == {}


@pytest.mark.skipif(shutil.which("cog") is None, reason="cog absent from PATH")
def test_cocogitto_accepts_the_config_and_bumps(cocogitto: Path) -> None:
    """The tool's own reader is the authority: an unrecognised key is rejected."""
    (cocogitto / "f.txt").write_text("x\n")
    subprocess.run(["git", "add", "-A"], cwd=cocogitto, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "feat: initial"], cwd=cocogitto, check=True)

    result = subprocess.run(
        ["cog", "bump", "--auto"], cwd=cocogitto, capture_output=True, text=True, check=False
    )

    assert result.returncode == 0, result.stdout + result.stderr
    tags = subprocess.run(
        ["git", "tag"], cwd=cocogitto, capture_output=True, text=True, check=True
    ).stdout
    assert "0.1.0" in tags
    assert (cocogitto / "CHANGELOG.md").is_file()


# --- release/dep-updates ---------------------------------------------------


@pytest.fixture
def dep_updates(tmp_path: Path) -> Path:
    dest = tmp_path / "du"
    dest.mkdir()
    result = render("release/dep-updates", dest, DU_ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def test_both_tools_render(dep_updates: Path) -> None:
    """Not a choice between them: renovate takes the language ecosystems, dependabot
    the actions, because its metadata action is what auto-merge reads."""
    assert (dep_updates / "renovate.json").is_file()
    assert (dep_updates / ".github" / "dependabot.yml").is_file()


def test_nothing_is_updated_twice(dep_updates: Path) -> None:
    """Both tools claiming github-actions would open two pull requests per bump."""
    renovate = json.loads((dep_updates / "renovate.json").read_text())
    assert "github-actions" not in renovate["enabledManagers"]

    disabled = [
        rule for rule in renovate["packageRules"] if rule.get("matchManagers") == ["github-actions"]
    ]
    assert disabled and disabled[0]["enabled"] is False

    dependabot = yaml.safe_load((dep_updates / ".github" / "dependabot.yml").read_text())
    assert [u["package-ecosystem"] for u in dependabot["updates"]] == ["github-actions"]


def test_the_renovate_managers_cover_the_language_layers(dep_updates: Path) -> None:
    """A manager left out silently updates nothing.

    Verified against renovate's manager list: `pep621` covers a uv `pyproject.toml`,
    and there is no `uv` manager.
    """
    managers = json.loads((dep_updates / "renovate.json").read_text())["enabledManagers"]
    for expected in ("cargo", "gomod", "npm", "bun", "pep621", "mise", "pre-commit"):
        assert expected in managers, f"{expected} is not enabled"
    assert "uv" not in managers, "uv is not a renovate manager"


def test_a_timezone_is_set(dep_updates: Path) -> None:
    """Without one renovate reads a schedule in UTC, so the window is off by hours."""
    assert json.loads((dep_updates / "renovate.json").read_text())["timezone"]


def test_auto_merge_is_not_spoofable(dep_updates: Path) -> None:
    """`github.actor` can be spoofed by pushing to a branch dependabot opened.

    zizmor reports the actor form as `bot-conditions`, at high confidence. The pull
    request's author cannot be spoofed.
    """
    workflow = dep_updates / ".github" / "workflows" / "dependabot-auto-merge.yml"
    spec = yaml.safe_load(workflow.read_text())
    if True in spec:
        spec["on"] = spec.pop(True)

    condition = spec["jobs"]["auto-merge"]["if"]
    assert "pull_request.user.login" in condition
    assert "github.actor" not in condition

    # pull_request_target runs with a writable token in the base repo's context, and
    # nothing here needs the pull request's code.
    assert list(spec["on"]) == ["pull_request"]


def test_a_major_update_waits_for_a_person(dep_updates: Path) -> None:
    workflow = (dep_updates / ".github" / "workflows" / "dependabot-auto-merge.yml").read_text()
    assert "semver-patch" in workflow
    assert "semver-minor" in workflow
    assert "semver-major" not in workflow


def test_auto_merge_can_be_turned_off(tmp_path: Path) -> None:
    dest = tmp_path / "du"
    dest.mkdir()
    render("release/dep-updates", dest, DU_ANSWERS.replace("auto_merge: true", "auto_merge: false"))

    assert (dest / "renovate.json").is_file()
    assert not (dest / ".github" / "workflows" / "dependabot-auto-merge.yml").exists()


@pytest.mark.parametrize("tool", ["actionlint", "zizmor"])
def test_the_release_workflows_pass_their_own_linters(
    tool: str, dep_updates: Path, tmp_path: Path
) -> None:
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} absent from PATH")

    render("release/release-please", dep_updates, RP_ANSWERS)
    workflows = dep_updates / ".github" / "workflows"
    argv = {
        "actionlint": [tool, *sorted(str(p) for p in workflows.glob("*.yml"))],
        "zizmor": [tool, "--min-severity", "medium", str(workflows)],
    }[tool]

    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr
