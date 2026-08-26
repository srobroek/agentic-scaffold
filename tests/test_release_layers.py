"""release/*: release-please, cocogitto, and the dependency-update tools."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import render_recipe as render

REPO_ROOT = Path(__file__).resolve().parent.parent

RP_ANSWERS = """\
release_type: ""
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
    # An empty answer detects from the tree, and a bare dest carries no marker.
    assert config(release_please)["release-type"] == "simple"
    assert manifest(release_please) == {".": "0.1.0"}


@pytest.mark.parametrize(
    ("marker", "content", "expected"),
    [
        ("rust-toolchain.toml", '[toolchain]\nchannel = "stable"\n', "rust"),
        ("pyproject.toml", '[project]\nname = "d"\nversion = "0"\n', "python"),
        ("package.json", '{"name": "d"}', "node"),
        ("go.mod", "module d\n\ngo 1.26\n", "go"),
    ],
)
def test_the_release_type_is_read_from_the_tree(
    marker: str, content: str, expected: str, tmp_path: Path
) -> None:
    """The tree already says which file carries the version, so nothing asks."""
    dest = git_repo(tmp_path / "rp")
    (dest / marker).write_text(content)

    assert render("release/release-please", dest, RP_ANSWERS).returncode == 0

    assert config(dest)["release-type"] == expected


def test_an_answered_release_type_is_never_rewritten(tmp_path: Path) -> None:
    """A monorepo publishing per-member components answers where the root shape lies."""
    dest = git_repo(tmp_path / "rp")
    (dest / "package.json").write_text('{"name": "d"}')

    answers = RP_ANSWERS.replace('release_type: ""', "release_type: simple")
    assert render("release/release-please", dest, answers).returncode == 0

    assert config(dest)["release-type"] == "simple"


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


def workflow_of(dest: Path) -> dict:
    return yaml.safe_load((dest / ".github" / "workflows" / "release-please.yml").read_text())


def test_without_the_app_the_release_pr_carries_no_checks(release_please: Path) -> None:
    """The default, and the trap it leaves is recorded in the workflow itself.

    A pull request opened with GITHUB_TOKEN triggers no workflow. GitHub refuses this on
    purpose, to stop a workflow from causing its own next run. The release pull request
    therefore reports no checks, and a required check blocks it: measured on this scaffold's own
    repository, where PR #2 came up with zero check runs against a required `gate`.
    """
    steps = workflow_of(release_please)["jobs"]["release-please"]["steps"]
    assert not any("create-github-app-token" in str(s.get("uses", "")) for s in steps)

    body = (release_please / ".github" / "workflows" / "release-please.yml").read_text()
    assert "will carry no checks" in body, "the trap has to be stated where the token is chosen"


def test_the_app_token_makes_the_release_pr_trigger_ci(tmp_path: Path) -> None:
    """An App token is not subject to the no-recursive-trigger rule, which is the only reason
    the mint step exists."""
    dest = tmp_path / "app"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render("release/release-please", dest, RP_ANSWERS + "release_app: true\n")
    assert result.returncode == 0, result.stderr

    steps = workflow_of(dest)["jobs"]["release-please"]["steps"]
    mint = next(s for s in steps if "create-github-app-token" in str(s.get("uses", "")))
    assert mint["id"] == "app-token"
    # The id is not sensitive, and keeping it in `vars` makes a wrong-app failure readable.
    assert mint["with"]["app-id"] == "${{ vars.RELEASE_APP_CLIENT_ID }}"
    assert mint["with"]["private-key"] == "${{ secrets.RELEASE_APP_PRIVATE_KEY }}"

    # The mint has to precede the action, and the action has to actually use the token.
    action = next(s for s in steps if "release-please-action" in str(s.get("uses", "")))
    assert steps.index(mint) < steps.index(action)

    # Scoped, not blanket. An App token defaults to every permission its installation holds,
    # which zizmor reports as `github-app` at HIGH. CI caught this and a local run did not: the
    # audit needs a GitHub token, and without one zizmor quietly drops it.
    assert mint["with"]["permission-contents"] == "write"
    assert mint["with"]["permission-pull-requests"] == "write"

    # No GITHUB_TOKEN fallback. A release pull request opened with that token carries no checks,
    # so falling back would report success while producing a pull request nobody can merge --
    # the failure would surface later, as a blocked PR, with nothing pointing at the cause.
    assert action["with"]["token"] == "${{ steps.app-token.outputs.token }}"
    assert "GITHUB_TOKEN" not in action["with"]["token"]

    # A missing or empty credential fails the run instead. The length check is what catches an
    # empty secret: one was written from an `op read` whose 1Password session had timed out
    # mid-pipe, so the write reported success and stored nothing, and every later run died
    # inside the action with `DataError: Invalid keyData` rather than naming the cause.
    require = next(s for s in steps if s.get("name") == "Require the release app credentials")
    assert steps.index(require) < steps.index(mint)
    # `secrets` is unavailable in a step-level `if`, which actionlint reports, so both are read
    # through env.
    assert "PRIVATE_KEY" in require["env"]
    assert "-lt 1000" in require["run"], "an empty secret has to fail, not just an absent one"
    assert "::error::" in require["run"]
    assert "exit 1" in require["run"]


def test_the_sync_step_amends_the_catalogs_onto_the_release_branch(tmp_path: Path) -> None:
    """The catalogs carry a version per plugin, read from each `<plugin>/.omp-plugin/plugin.json`,
    so a release that bumps one leaves them stale the moment the pull request opens -- measured on
    this scaffold's own PR #2, two differences, one per package. Under the shape the profile
    renders, nothing bumps those manifests, so the step reports "already in sync" and earns its
    keep once release-please's own config names them.
    """
    dest = tmp_path / "sync"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    answers = RP_ANSWERS + "release_app: true\nsync_generated: true\n"
    assert render("release/release-please", dest, answers).returncode == 0

    steps = workflow_of(dest)["jobs"]["release-please"]["steps"]
    sync = next(s for s in steps if "Sync the generated catalogs" in s.get("name", ""))

    # Only when a release pull request exists.
    assert sync["if"] == "${{ steps.release.outputs.pr }}"
    # Step-level `env` evaluates even when `if` is false, so the parse is guarded too: a bare
    # `fromJSON('')` aborts the whole job with "Error reading JToken".
    branch = sync["env"]["RELEASE_BRANCH"]
    assert branch.startswith("${{ steps.release.outputs.pr &&")
    assert branch.rstrip().endswith("|| '' }}")

    assert "just marketplace-build" in sync["run"]
    # Checked rather than assumed. just reports `justfile does not contain recipe` and exits 1,
    # which reads as a broken workflow rather than a layer that never rendered -- this repository
    # hit exactly that, because its own justfile named the check `packages` and shipped no build.
    assert "does not contain recipe" in sync["run"] or "no marketplace-build recipe" in sync["run"]
    # Nothing to amend is a normal outcome, not a failure.
    assert "git diff --quiet" in sync["run"]


def test_the_sync_step_does_not_persist_the_token(tmp_path: Path) -> None:
    """A token left in `.git/config` is what zizmor reports as `artipacked`. It is avoidable
    here, so the layer avoids it rather than suppressing the audit: the credential goes in the
    remote URL, where the runner masks it because it came from a secret."""
    dest = tmp_path / "nopersist"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    answers = RP_ANSWERS + "release_app: true\nsync_generated: true\n"
    assert render("release/release-please", dest, answers).returncode == 0

    steps = workflow_of(dest)["jobs"]["release-please"]["steps"]
    checkout = next(s for s in steps if "actions/checkout" in str(s.get("uses", "")))
    assert checkout["with"]["persist-credentials"] is False
    # The release branch is fetched by name, so a shallow clone will not do.
    assert checkout["with"]["fetch-depth"] == 0

    sync = next(s for s in steps if "Sync the generated catalogs" in s.get("name", ""))
    assert "x-access-token:$GH_TOKEN" in sync["run"]

    # This job pushes onto a branch that will be released, so a poisoned cache entry would
    # reach a published artefact.
    mise = next(s for s in steps if "mise-action" in str(s.get("uses", "")))
    assert mise["with"]["cache"] is False


def test_the_sync_step_is_absent_without_the_app(release_please: Path) -> None:
    """The amending commit has to trigger the required checks, and only an App-token commit
    does. Syncing with GITHUB_TOKEN would push a commit that no check ever sees."""
    steps = workflow_of(release_please)["jobs"]["release-please"]["steps"]
    assert not any("Sync the generated catalogs" in s.get("name", "") for s in steps)
