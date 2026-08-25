"""lang/api: the OpenAPI contract, its lint, and the breaking-change gate.

Both tools have a default that looks like a gate and is not one. `vacuum lint` exits 0
on warnings unless `--fail-severity` is passed, and a missing description or absent
operationId is reported at warn. `oasdiff breaking` prints every breaking change and
exits 0 unless `--fail-on ERR` is passed. Verified against vacuum 0.30.0 and oasdiff
1.26.1: removing an operation exited 0 bare and 1 with the flag.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import mise_bin
from conftest import render_recipe as render

REPO_ROOT = Path(__file__).resolve().parent.parent

ANSWERS = """\
api_title: Widget API
api_version: "1.0.0"
api_server_url: https://api.example.com
org: Sjors Robroek
repo_url: https://github.com/srobroek/demo
license: Apache-2.0
default_branch: main
"""

# mise installs these outside the PATH a bare subprocess inherits. The two pinned versions are
# named directly, since a test here asserts behaviour specific to them. `just` floats, so it is
# resolved through mise rather than an installs/just/latest path: see conftest.mise_bin.
TOOL_DIRS = [
    Path.home() / ".local/share/mise/installs/vacuum/0.30.0",
    Path.home() / ".local/share/mise/installs/ubi-oasdiff-oasdiff/1.26.1",
    *([mise_bin("just")] if mise_bin("just") else []),
]


def tool(name: str) -> str | None:
    for directory in TOOL_DIRS:
        candidate = directory / name
        if candidate.is_file():
            return str(candidate)
    return shutil.which(name)


needs_vacuum = pytest.mark.skipif(tool("vacuum") is None, reason="vacuum absent")
needs_oasdiff = pytest.mark.skipif(tool("oasdiff") is None, reason="oasdiff absent")
needs_just = pytest.mark.skipif(tool("just") is None, reason="just absent")


def tool_env() -> dict[str, str]:
    import os

    env = dict(os.environ)
    extra = ":".join(str(d) for d in TOOL_DIRS if d.is_dir())
    if extra:
        env["PATH"] = f"{extra}:{env['PATH']}"
    return env


def run(dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args, cwd=dest, capture_output=True, text=True, check=False, env=tool_env()
    )


def git(dest: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=dest, check=True, capture_output=True)


@pytest.fixture
def api(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    for key, value in (("user.email", "t@e.com"), ("user.name", "T")):
        git(dest, "config", key, value)
    result = render("lang/api", dest, ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


@pytest.fixture
def committed(api: Path) -> Path:
    """The contract committed and a baseline ref pointing at it.

    `scaffold render` commits per recipe, so both renders are already in
    history and HEAD holds the contract; only the baseline ref is ours.
    """
    render("workspace/just", api)
    # A real origin/main without a remote, which is what the recipe reads.
    git(api, "update-ref", "refs/remotes/origin/main", "HEAD")
    return api


def replace_health_with(dest: Path, block: str) -> None:
    """Swap the /health path for something else, which removes an operation."""
    spec = dest / "openapi.yaml"
    body = re.sub(r"  /health:.*?(?=\ncomponents:)", block, spec.read_text(), flags=re.S)
    spec.write_text(body)


# --- the contract ----------------------------------------------------------


def test_the_spec_parses_and_carries_the_threaded_values(api: Path) -> None:
    spec = yaml.safe_load((api / "openapi.yaml").read_text())
    assert spec["openapi"].startswith("3.1")
    assert spec["info"]["title"] == "Widget API"
    assert spec["info"]["license"]["name"] == "Apache-2.0"
    assert spec["servers"][0]["url"] == "https://api.example.com"


def test_the_starter_describes_a_real_endpoint(api: Path) -> None:
    """`paths: {}` lints clean while describing nothing, so the first real endpoint has
    no shape to follow."""
    spec = yaml.safe_load((api / "openapi.yaml").read_text())
    assert "/health" in spec["paths"]
    assert spec["paths"]["/health"]["get"]["operationId"] == "getHealth"
    assert "Health" in spec["components"]["schemas"]


def test_every_schema_carries_an_example(api: Path) -> None:
    """vacuum reports a missing example at warn, and the gate fails at warn.

    The starter scored 98/100 with four `missing examples` warnings until these were
    added, so it failed its own gate as rendered.
    """
    spec = yaml.safe_load((api / "openapi.yaml").read_text())
    content = spec["paths"]["/health"]["get"]["responses"]["200"]["content"]["application/json"]
    assert "example" in content
    health = spec["components"]["schemas"]["Health"]
    assert "example" in health
    assert "example" in health["properties"]["status"]


# --- the real tools --------------------------------------------------------


@needs_vacuum
def test_the_rendered_starter_passes_its_own_gate(api: Path) -> None:
    """At the layer's own threshold, not vacuum's default. A scaffold that fails the
    check it ships is a scaffold someone has to fix before the first commit."""
    result = run(api, tool("vacuum"), "lint", "--fail-severity", "warn", "openapi.yaml")
    assert result.returncode == 0, result.stdout[-1500:]


@needs_vacuum
def test_vacuum_alone_would_not_gate_a_warning(api: Path) -> None:
    """The reason --fail-severity is passed everywhere.

    A spec with a warning exits 0 under the default threshold, so a bare `vacuum lint`
    reports contract drift while reporting success.
    """
    spec = api / "openapi.yaml"
    # Rewritten through the parser rather than by regex: an edit that breaks the YAML
    # exits 2 for a load error, which would prove nothing about the threshold.
    document = yaml.safe_load(spec.read_text())
    content = document["paths"]["/health"]["get"]["responses"]["200"]["content"]
    content["application/json"].pop("example", None)
    document["components"]["schemas"]["Health"].pop("example", None)
    document["components"]["schemas"]["Health"]["properties"]["status"].pop("example", None)
    spec.write_text(yaml.safe_dump(document, sort_keys=False))

    lenient = run(api, tool("vacuum"), "lint", "openapi.yaml")
    strict = run(api, tool("vacuum"), "lint", "--fail-severity", "warn", "openapi.yaml")
    # Exit 2 is a load error rather than a finding, so the edit has to stay parseable.
    assert strict.returncode == 1, f"expected a warning, got exit {strict.returncode}"
    assert lenient.returncode == 0, "vacuum's default threshold is error, not warn"


@needs_just
@needs_vacuum
def test_the_lint_recipe_passes_the_threshold(committed: Path) -> None:
    fragment = (committed / ".just.d" / "api.just").read_text()
    assert "--fail-severity" in fragment
    assert run(committed, tool("just"), "api-lint").returncode == 0


@needs_just
@needs_oasdiff
def test_an_unchanged_contract_passes_the_breaking_gate(committed: Path) -> None:
    result = run(committed, tool("just"), "api-breaking")
    assert result.returncode == 0, result.stdout + result.stderr


@needs_just
@needs_oasdiff
def test_removing_an_operation_fails_the_breaking_gate(committed: Path) -> None:
    """The bead's acceptance criterion: a breaking API change fails CI."""
    replace_health_with(
        committed,
        "  /other:\n    get:\n      operationId: other\n      summary: Other\n"
        "      description: Other endpoint.\n      tags: [health]\n"
        '      responses:\n        "200":\n          description: ok.\n',
    )
    result = run(committed, tool("just"), "api-breaking")
    assert result.returncode == 1, result.stdout + result.stderr
    assert "removed" in (result.stdout + result.stderr).lower()


@needs_just
@needs_oasdiff
def test_an_additive_change_passes(committed: Path) -> None:
    """A new endpoint breaks no consumer, so the gate must not fire on it."""
    spec = committed / "openapi.yaml"
    spec.write_text(
        spec.read_text().replace(
            "components:",
            "  /extra:\n    get:\n      operationId: getExtra\n      summary: Extra\n"
            "      description: An added endpoint.\n      tags: [health]\n"
            '      responses:\n        "200":\n          description: ok.\n'
            "          content:\n            application/json:\n"
            "              schema:\n                type: object\n"
            "                description: Empty payload.\n"
            "                example: {}\n\ncomponents:",
            1,
        )
    )
    result = run(committed, tool("just"), "api-breaking")
    assert result.returncode == 0, result.stdout + result.stderr


@needs_just
@needs_oasdiff
def test_a_missing_baseline_does_not_block(api: Path) -> None:
    """A first commit on a fresh branch has no baseline, and a gate that fails there
    blocks the commit that introduces the contract."""
    render("workspace/just", api)
    result = run(api, tool("just"), "api-breaking")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "no baseline" in (result.stdout + result.stderr).lower()


# --- fragments and CI ------------------------------------------------------


def test_the_breaking_check_passes_fail_on_err(api: Path) -> None:
    """Without it oasdiff prints every breaking change and still exits 0."""
    assert "--fail-on ERR" in (api / ".just.d" / "api.just").read_text()


def test_oasdiff_is_installed_through_ubi(api: Path) -> None:
    """The aqua registry carries no oasdiff entry, so `aqua:oasdiff/oasdiff` resolves
    nothing."""
    pin = (api / ".mise" / "conf.d" / "api.toml").read_text()
    assert '"ubi:oasdiff/oasdiff"' in pin
    assert "vacuum" in pin


def test_only_the_lint_runs_at_commit_time(api: Path) -> None:
    """The breaking check needs a baseline ref, and a commit on a fresh branch has no
    merge base yet, so it belongs in CI where the pull request defines one."""
    fragment = yaml.safe_load((api / ".pre-commit.d" / "api.yaml").read_text())
    ids = {hook["id"] for repo in fragment["repos"] for hook in repo["hooks"]}
    assert ids == {"vacuum"}


def test_the_breaking_job_fetches_the_full_history(api: Path) -> None:
    """The check reads the spec out of the baseline ref, and a depth-1 clone has no such
    object."""
    workflow = yaml.safe_load((api / ".github" / "workflows" / "wc-lint-api.yml").read_text())
    steps = workflow["jobs"]["breaking"]["steps"]
    checkout = next(s for s in steps if "checkout" in str(s.get("uses", "")))
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False


def test_the_gitlab_fragment_is_namespaced(api: Path) -> None:
    """Merge order across the include glob is not deterministic, so no two fragments may
    set the same key."""
    fragment = yaml.safe_load((api / ".gitlab" / "ci" / "api.yml").read_text())
    for name in fragment:
        assert name.lstrip(".").startswith("api"), f"{name} is not namespaced"
    assert fragment["api-breaking"]["variables"]["GIT_DEPTH"] == "0"
