"""host/* layers: language-blind CI and the governance surface."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"
LANG_TEMPLATES = REPO_ROOT / "templates" / "lang"

ANSWERS = """\
project_name: demo
org: srobroek
default_branch: main
job_timeout_minutes: 15
security_contact: ""
coc_contact: ""
"""

# A language layer to render alongside a host layer, so the fragment-driven parts
# have something real to fold in.
ANSWERS_GO = 'go_module_path: github.com/srobroek/demo\ngo_version: "1.26"\ngo_vendor: false\n'


def render(layer: str, dest: Path, answers: str) -> subprocess.CompletedProcess[str]:
    answers_file = dest.parent / f"{dest.name}-answers.yml"
    answers_file.write_text(answers)
    return subprocess.run(
        [sys.executable, str(RENDER), layer, str(dest), "--answers", str(answers_file)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def rendered(tmp_path: Path) -> Path:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("host/github", dest, ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def workflow(dest: Path, name: str) -> dict:
    spec = yaml.safe_load((dest / ".github" / "workflows" / f"{name}.yml").read_text())
    # YAML 1.1 reads a bare `on` as boolean true, so the trigger key arrives as
    # True rather than the string. Normalising here keeps every assertion readable.
    if True in spec:
        spec["on"] = spec.pop(True)
    return spec


# --- the CI inversion ------------------------------------------------------


def test_the_host_layer_runs_no_language_tooling(rendered: Path) -> None:
    """The inversion's whole point: the host layer knows nothing about languages.

    Language tooling here means a step belonging in a lang/* layer leaked in, and
    the repository then runs CI for a language it may not have.

    This checks the tools rather than the language names. A bare name appears
    legitimately: `python3` is the scripting interpreter the discovery steps use,
    and the comments explain why CodeQL and lizard cannot live here at all.
    """
    # Each entry is a tool that only makes sense for one language. Matched on word
    # boundaries: `ruff` is a substring of `trufflehog`, and `go` of `google`.
    tooling = [
        "cargo",
        "clippy",
        "rustfmt",
        "nextest",
        "ruff",
        "pytest",
        "uv sync",
        "biome",
        "oxlint",
        "tsc",
        "bun",
        "golangci-lint",
        "gofmt",
        "govulncheck",
    ]

    offenders = []
    for path in sorted((rendered / ".github").rglob("*")):
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            # Rationale is prose, and the design reasons name the tools they exclude.
            if line.lstrip().startswith("#"):
                continue
            for tool in tooling:
                if re.search(rf"(?<![\w-]){re.escape(tool)}(?![\w-])", line, re.IGNORECASE):
                    offenders.append(f"{path.relative_to(rendered)}:{lineno} runs {tool!r}")
    assert not offenders, "language tooling in the host layer: " + "; ".join(offenders)


def test_every_language_fragment_kind_is_consumed(rendered: Path) -> None:
    """The contribution points only work if the host layer actually reads them.

    A lang/* layer dropping a fragment nothing folds in produces CI that silently
    omits that language's scans.
    """
    languages = sorted(p.name for p in LANG_TEMPLATES.iterdir() if p.is_dir())
    assert languages, "no lang/* layers found, so this test proves nothing"

    quality = yaml.dump(workflow(rendered, "wc-quality"))
    security = yaml.dump(workflow(rendered, "wc-security"))
    assert ".github/quality.d" in quality
    assert ".github/security.d" in security

    # Every key a rendered fragment sets has to be read by the workflow that folds
    # that directory in, or the fragment is inert.
    for language in languages:
        for kind, body in (("quality", quality), ("security", security)):
            fragment = (
                LANG_TEMPLATES / language / "template" / ".github" / f"{kind}.d" / f"{language}.yml"
            )
            if not fragment.is_file():
                continue
            for key in yaml.safe_load(fragment.read_text()) or {}:
                assert key in body, f"{kind}.d/{language}.yml sets {key!r}, which nothing reads"


def test_the_gate_is_the_only_required_check(rendered: Path) -> None:
    """One required check that depends on every job.

    A second required check means adding a job needs a branch-protection change,
    and a required check that never runs leaves a pull request unmergeable.
    """
    gate = workflow(rendered, "wc-gate")
    assert list(gate["jobs"]) == ["gate"]
    # The gate judges the caller's needs context rather than re-running anything.
    assert "needs" in gate["on"]["workflow_call"]["inputs"]
    assert "./.github/actions/ci-gate" in yaml.dump(gate)


def test_no_workflow_filters_at_the_on_level(rendered: Path) -> None:
    """Path filtering belongs in the caller at job level.

    A workflow gated at `on:` does not run for an unrelated change, and a required
    check that never runs leaves the pull request unmergeable forever.
    """
    for name in ("wc-changes", "wc-gate", "wc-quality", "wc-security"):
        spec = workflow(rendered, name)
        # workflow_call takes no paths key at all, so a reusable workflow cannot
        # gate itself even by accident. The filter spec travels as an input instead.
        assert list(spec["on"]) == ["workflow_call"], f"{name} triggers on more than a call"
        for trigger, config in spec["on"].items():
            if isinstance(config, dict):
                assert "paths" not in config, f"{name} filters paths under {trigger}"
                assert "paths-ignore" not in config


def test_the_aggregating_jobs_discover_their_matrix(rendered: Path) -> None:
    """The matrix is read from the fragment directories, not written in by hand.

    This is what lets a new lang/* layer contribute its own jobs without editing
    the host layer.
    """
    quality = workflow(rendered, "wc-quality")
    assert ".github/quality.d" in yaml.dump(quality)
    assert quality["jobs"]["complexity"]["needs"] == "discover"

    security = workflow(rendered, "wc-security")
    assert ".github/security.d" in yaml.dump(security)
    for job in ("codeql", "osv", "trivy"):
        assert security["jobs"][job]["needs"] == "discover"


def test_every_lizard_language_is_one_lizard_knows() -> None:
    """A name lizard does not know exits 0 having analysed nothing.

    Verified against lizard 1.17: `-l notalanguage` prints no warning and exits 0,
    so a typo in a fragment silently removes that language's complexity gate rather
    than failing the run. Nothing downstream would report it.
    """
    known = {
        "c",
        "cpp",
        "java",
        "csharp",
        "javascript",
        "js",
        "python",
        "objectivec",
        "objective-c",
        "objc",
        "ttcn",
        "ttcn3",
        "ruby",
        "php",
        "swift",
        "scala",
        "GDScript",
        "go",
        "lua",
        "rust",
        "typescript",
        "ts",
        "fortran",
        "kotlin",
        "solidity",
        "erlang",
        "zig",
        "tsx",
        "jsx",
        "vue",
        "vuejs",
        "perl",
        "st",
        "r",
        "R",
        "plsql",
        "pl/sql",
    }
    for fragment in sorted(LANG_TEMPLATES.glob("*/template/.github/quality.d/*.yml")):
        lizard = (yaml.safe_load(fragment.read_text()) or {}).get("lizard") or {}
        language = lizard.get("language")
        if language is None:
            continue
        assert language in known, (
            f"{fragment.relative_to(LANG_TEMPLATES)} names {language!r}, "
            "which lizard would silently ignore"
        )


def test_a_discovered_matrix_job_is_guarded_by_a_count(rendered: Path) -> None:
    """A matrix of zero entries is a workflow error rather than a skip.

    A docs-only repository renders no lang/* layer, so every fragment directory is
    empty and each of these jobs must skip instead of failing the run.
    """
    quality = workflow(rendered, "wc-quality")
    assert quality["jobs"]["complexity"]["if"] == "needs.discover.outputs.any == 'true'"

    security = workflow(rendered, "wc-security")
    for job, flag in (("codeql", "any_codeql"), ("osv", "any_osv"), ("trivy", "any_trivy")):
        assert security["jobs"][job]["if"] == f"needs.discover.outputs.{flag} == 'true'"


def test_the_quality_job_runs_the_whole_hook_set(rendered: Path) -> None:
    """The only layer that actually enforces the hooks.

    A local hook is advisory: `--no-verify` defeats it, and a fresh clone has no
    shims until someone runs `just setup`. `--all-files` rather than a diff range,
    or a hook bypassed when the file was committed stays bypassed forever.
    """
    steps = yaml.dump(workflow(rendered, "wc-quality")["jobs"]["quality"]["steps"])
    assert "prek run --all-files" in steps
    # quality/hooks may not have rendered, so the step tolerates a missing config
    # rather than failing a repository that has no hooks.
    assert ".pre-commit-config.yaml" in steps


def test_the_secret_scan_always_runs(rendered: Path) -> None:
    """It needs no language knowledge, so no fragment gates it."""
    secrets = workflow(rendered, "wc-security")["jobs"]["secrets"]
    assert "if" not in secrets
    # A secret is usually in an older commit, which a shallow clone never fetches.
    assert secrets["steps"][0]["with"]["fetch-depth"] == 0


@pytest.mark.parametrize(
    ("needs", "blocked"),
    [
        ({"quality": "success", "security": "success"}, False),
        # The case the whole design exists for: a language job skipped by a path
        # filter must not block a docs-only pull request.
        ({"lint-rust": "skipped", "quality": "success"}, False),
        ({"quality": "failure", "security": "success"}, True),
        ({"test-rust": "cancelled"}, True),
    ],
)
def test_the_gate_blocks_on_failure_and_not_on_a_skip(
    needs: dict, blocked: bool, rendered: Path, tmp_path: Path
) -> None:
    """The gate's verdict is what branch protection acts on.

    Extracted from the composite action so the real script runs rather than a copy
    of it: a reimplementation here could pass while the action was wrong.
    """
    action = yaml.safe_load(
        (rendered / ".github" / "actions" / "ci-gate" / "action.yml").read_text()
    )
    script = action["runs"]["steps"][0]["run"]

    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        check=False,
        env={
            "PATH": "/usr/bin:/bin:/usr/local/bin",
            "NEEDS": json.dumps({k: {"result": v} for k, v in needs.items()}),
        },
    )

    assert (result.returncode != 0) is blocked, result.stdout + result.stderr
    if blocked:
        # A failure has to name the job, or the only signal is a red gate.
        assert any(job in result.stdout for job in needs)


# --- hardening ------------------------------------------------------------


def test_checkout_never_persists_credentials(rendered: Path) -> None:
    """zizmor reports the default, which leaves GITHUB_TOKEN in .git/config."""
    for name in ("wc-changes", "wc-gate", "wc-quality", "wc-security"):
        spec = workflow(rendered, name)
        for job_name, job in spec["jobs"].items():
            for step in job["steps"]:
                if "actions/checkout" in str(step.get("uses", "")):
                    assert step["with"]["persist-credentials"] is False, (
                        f"{name}:{job_name} persists credentials"
                    )


def test_every_job_carries_a_timeout(rendered: Path) -> None:
    """GitHub defaults to 360 minutes, so a hung job burns six runner hours."""
    for name in ("wc-changes", "wc-gate", "wc-quality", "wc-security"):
        for job_name, job in workflow(rendered, name)["jobs"].items():
            assert "timeout-minutes" in job, f"{name}:{job_name} has no timeout"


def test_the_timeout_is_threaded_from_the_answer(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    render(
        "host/github", dest, ANSWERS.replace("job_timeout_minutes: 15", "job_timeout_minutes: 7")
    )
    assert workflow(dest, "wc-gate")["jobs"]["gate"]["timeout-minutes"] == 7


def test_every_action_is_pinned_to_a_sha(rendered: Path) -> None:
    """A tag is mutable, so a moved tag would change what CI runs."""
    for name in ("wc-changes", "wc-gate", "wc-quality", "wc-security"):
        for job in workflow(rendered, name)["jobs"].values():
            for step in job["steps"]:
                uses = str(step.get("uses", ""))
                if not uses or uses.startswith("./"):
                    continue
                ref = uses.split("@")[-1]
                assert len(ref) == 40 and all(c in "0123456789abcdef" for c in ref), (
                    f"{uses} is not pinned to a full SHA"
                )


@pytest.mark.parametrize("tool", ["actionlint", "zizmor"])
def test_the_rendered_workflows_pass_their_own_linters(tool: str, rendered: Path) -> None:
    """The generated CI has to survive the checks it tells a project to run.

    Skipped rather than failed when the tool is absent: the tools are installed
    through mise in CI, and a missing binary locally is not a defect in the layer.
    """
    if shutil.which(tool) is None:
        pytest.skip(f"{tool} absent from PATH")

    workflows = rendered / ".github" / "workflows"
    argv = {
        "actionlint": [tool, *sorted(str(p) for p in workflows.glob("*.yml"))],
        # zizmor audits for the credential and injection patterns actionlint does
        # not model. Its network audits need a token and skip without one.
        "zizmor": [tool, "--min-severity", "medium", str(workflows)],
    }[tool]

    result = subprocess.run(argv, capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stdout + result.stderr


# --- host/gitlab ----------------------------------------------------------

GITLAB_ANSWERS = """\
gitlab_host: gitlab.com
security_contact: ""
coc_contact: ""
default_branch: main
job_timeout_minutes: 15
project_name: demo
org: srobroek
"""


@pytest.fixture
def gitlab(tmp_path: Path) -> Path:
    dest = tmp_path / "gl"
    dest.mkdir()
    result = render("host/gitlab", dest, GITLAB_ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def pipeline(dest: Path) -> dict:
    return yaml.safe_load((dest / ".gitlab-ci.yml").read_text())


def test_the_pipeline_needs_no_caller(gitlab: Path) -> None:
    """Unlike GitHub, the glob include resolves whichever fragments rendered."""
    spec = pipeline(gitlab)
    assert spec["include"] == [{"local": ".gitlab/ci/*.yml"}]


def test_the_gitlab_layer_runs_no_language_tooling(gitlab: Path) -> None:
    """Each lang/* layer supplies its own .gitlab/ci fragment."""
    tooling = [
        "cargo",
        "clippy",
        "rustfmt",
        "nextest",
        "ruff",
        "pytest",
        "biome",
        "oxlint",
        "tsc",
        "bun",
        "golangci-lint",
        "gofmt",
        "govulncheck",
    ]
    offenders = []
    for path in sorted(gitlab.rglob("*")):
        if not path.is_file():
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            for tool in tooling:
                if re.search(rf"(?<![\w-]){re.escape(tool)}(?![\w-])", line, re.IGNORECASE):
                    offenders.append(f"{path.name}:{lineno} runs {tool!r}")
    assert not offenders, "language tooling in the host layer: " + "; ".join(offenders)


def test_every_declared_stage_reaches_the_stages_list(gitlab: Path) -> None:
    """GitLab fails the whole pipeline on a job naming an undeclared stage.

    It does not skip the job, so the list has to cover every fragment. The include is
    a glob, which is why the list is generated rather than written by hand.
    """
    render("lang/go", gitlab, ANSWERS_GO)
    subprocess.run(
        [sys.executable, str(gitlab / "scripts" / "gen_gitlab_stages.py"), str(gitlab)],
        check=True,
        capture_output=True,
    )

    spec = pipeline(gitlab)
    merged: dict = {}
    for fragment in sorted((gitlab / ".gitlab" / "ci").glob("*.yml")):
        merged.update(yaml.safe_load(fragment.read_text()) or {})
    merged.update({k: v for k, v in spec.items() if isinstance(v, dict)})

    reserved = {"default", "workflow", "variables", "include"}
    for name, job in merged.items():
        if name.startswith(".") or name in reserved or not isinstance(job, dict):
            continue
        if stage := job.get("stage"):
            assert stage in spec["stages"], f"job {name!r} names undeclared stage {stage!r}"


def test_the_stages_are_in_pipeline_order(gitlab: Path) -> None:
    """`stages:` defines what runs before what, so alphabetical would be wrong."""
    render("lang/go", gitlab, ANSWERS_GO)
    subprocess.run(
        [sys.executable, str(gitlab / "scripts" / "gen_gitlab_stages.py"), str(gitlab)],
        check=True,
        capture_output=True,
    )
    assert pipeline(gitlab)["stages"] == ["quality", "lint", "test", "security"]


def test_the_host_stages_apply_with_no_language_layer(gitlab: Path) -> None:
    """This layer's own jobs sit in quality and security.

    A pipeline whose only jobs name stages the list omits fails rather than skipping,
    so those two are unconditional.
    """
    assert pipeline(gitlab)["stages"] == ["quality", "security"]


def test_an_unknown_stage_is_refused(gitlab: Path) -> None:
    """A typo would otherwise reach the pipeline and fail every job in it."""
    (gitlab / ".gitlab" / "ci").mkdir(parents=True, exist_ok=True)
    (gitlab / ".gitlab" / "ci" / "bad.yml").write_text(
        "bad-job:\n  stage: notastage\n  script:\n    - true\n"
    )

    result = subprocess.run(
        [sys.executable, str(gitlab / "scripts" / "gen_gitlab_stages.py"), str(gitlab)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "notastage" in result.stderr
    # The message has to say what a valid stage is, or it just says no.
    assert "quality" in result.stderr


def test_a_template_key_is_not_mistaken_for_a_job(gitlab: Path) -> None:
    """A key opening with a dot is a template, and GitLab never runs it."""
    (gitlab / ".gitlab" / "ci").mkdir(parents=True, exist_ok=True)
    (gitlab / ".gitlab" / "ci" / "tpl.yml").write_text(
        ".hidden-setup:\n  stage: notastage\n  script:\n    - true\n"
    )

    result = subprocess.run(
        [sys.executable, str(gitlab / "scripts" / "gen_gitlab_stages.py"), str(gitlab)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_the_pipeline_does_not_run_twice_for_one_push(gitlab: Path) -> None:
    """Without the branch condition a push to a branch with an open MR runs two."""
    rules = pipeline(gitlab)["workflow"]["rules"]
    assert any("merge_request_event" in str(rule) for rule in rules)
    assert any("CI_COMMIT_BRANCH" in str(rule) for rule in rules)


def test_the_secret_scan_reads_full_history(gitlab: Path) -> None:
    """A secret usually sits in an older commit, which a shallow clone never fetches."""
    spec = pipeline(gitlab)
    assert spec["variables"]["GIT_DEPTH"] == "50"
    assert spec["secret-scan"]["variables"]["GIT_DEPTH"] == "0"


def test_the_jobs_carry_a_timeout(gitlab: Path) -> None:
    """GitLab takes its default from the runner, not the job."""
    assert pipeline(gitlab)["default"]["timeout"] == "15m"


def test_the_generated_pipeline_is_valid_yaml(gitlab: Path) -> None:
    """An inline `{extends: relaxed, ...}` parses as a flow mapping, not a string.

    That is what broke the first version of the yamllint step, so the argument sits
    inside a block scalar.
    """
    if shutil.which("yamllint") is None:
        pytest.skip("yamllint absent from PATH")

    result = subprocess.run(
        [
            "yamllint",
            "-f",
            "parsable",
            "-d",
            "{extends: relaxed, rules: {line-length: disable, document-start: disable}}",
            str(gitlab / ".gitlab-ci.yml"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout


def test_gitlab_governance_uses_gitlab_terminology(gitlab: Path) -> None:
    """ "Pull request" is GitHub's term, and a contributor reads these literally."""
    contributing = (gitlab / "CONTRIBUTING.md").read_text()
    assert "merge request" in contributing.lower()
    assert "pull request" not in contributing.lower()

    # GitLab has no private vulnerability reporting form; a confidential issue is
    # the private channel a project has without extra configuration.
    security = (gitlab / "SECURITY.md").read_text()
    assert "confidential issue" in security.lower()


def test_the_gitlab_governance_surface_renders(gitlab: Path) -> None:
    for expected in (
        ".gitlab/CODEOWNERS",
        ".gitlab/issue_templates/bug_report.md",
        ".gitlab/issue_templates/feature_request.md",
        ".gitlab/merge_request_templates/default.md",
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
    ):
        assert (gitlab / expected).is_file(), f"missing {expected}"


def test_both_hosts_coexist_and_the_first_owns_the_shared_files(tmp_path: Path) -> None:
    """A repository mirrored to both forges renders both layers.

    `SECURITY.md`, `CONTRIBUTING.md`, and `CODE_OF_CONDUCT.md` are not host-specific
    paths, so both layers would write them. `_skip_if_exists` gives them to whichever
    rendered first rather than leaving the second layer's wording to win silently;
    the host-specific trees stay separate either way.
    """
    dest = tmp_path / "both"
    dest.mkdir()
    assert render("host/github", dest, ANSWERS).returncode == 0
    assert render("host/gitlab", dest, GITLAB_ANSWERS).returncode == 0

    # Each host's own tree is untouched by the other.
    assert (dest / ".github" / "workflows" / "wc-gate.yml").is_file()
    assert (dest / ".gitlab-ci.yml").is_file()
    assert (dest / ".github" / "PULL_REQUEST_TEMPLATE.md").is_file()
    assert (dest / ".gitlab" / "merge_request_templates" / "default.md").is_file()

    # github rendered first, so its CONTRIBUTING survived rather than being replaced.
    assert "pull request" in (dest / "CONTRIBUTING.md").read_text().lower()


def test_an_absent_owner_writes_no_wildcard_rule_on_gitlab(tmp_path: Path) -> None:
    dest = tmp_path / "gl"
    dest.mkdir()
    render("host/gitlab", dest, GITLAB_ANSWERS.replace("org: srobroek", 'org: ""'))
    body = (dest / ".gitlab" / "CODEOWNERS").read_text()
    assert "*  @\n" not in body


# --- governance -----------------------------------------------------------


def test_the_governance_surface_renders(rendered: Path) -> None:
    for expected in (
        "SECURITY.md",
        "CONTRIBUTING.md",
        "CODE_OF_CONDUCT.md",
        ".github/CODEOWNERS",
        ".github/PULL_REQUEST_TEMPLATE.md",
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
    ):
        assert (rendered / expected).is_file(), f"missing {expected}"


def test_an_empty_contact_names_the_fallback_that_exists(rendered: Path) -> None:
    """An unset contact must not leave prose pointing at nothing.

    GitHub's private reporting form needs enabling once, so SECURITY.md says so
    rather than assuming it is there.
    """
    security = (rendered / "SECURITY.md").read_text()
    assert "private vulnerability reporting" in security
    assert "Settings, Code security" in security

    # A code of conduct with no reporting channel asks people to trust a process
    # that does not exist, so the placeholder has to be loud.
    coc = (rendered / "CODE_OF_CONDUCT.md").read_text()
    assert "Fill in a contact address" in coc


def test_a_contact_replaces_the_fallback(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    render(
        "host/github",
        dest,
        ANSWERS.replace('security_contact: ""', "security_contact: s@example.com").replace(
            'coc_contact: ""', "coc_contact: c@example.com"
        ),
    )
    assert "s@example.com" in (dest / "SECURITY.md").read_text()
    assert "c@example.com" in (dest / "CODE_OF_CONDUCT.md").read_text()
    assert "Fill in a contact address" not in (dest / "CODE_OF_CONDUCT.md").read_text()


def test_a_pull_request_template_sits_where_github_reads_one(rendered: Path) -> None:
    """A single template inside PULL_REQUEST_TEMPLATE/ never loads by default.

    That directory form applies only per-template through a query parameter, so one
    file there is silently inert.
    """
    assert (rendered / ".github" / "PULL_REQUEST_TEMPLATE.md").is_file()
    assert not (rendered / ".github" / "PULL_REQUEST_TEMPLATE").is_dir()


def test_an_absent_owner_writes_no_wildcard_rule(tmp_path: Path) -> None:
    """`*  @` is a parse error GitHub reports on every pull request."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("host/github", dest, ANSWERS.replace("org: srobroek", 'org: ""'))
    body = (dest / ".github" / "CODEOWNERS").read_text()
    assert "*  @\n" not in body
    for line in body.splitlines():
        assert line.startswith("#") or not line.strip()


def test_hand_edited_governance_survives_a_second_render(tmp_path: Path) -> None:
    """A contact address and a project rule are edited after rendering."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("host/github", dest, ANSWERS)

    contributing = dest / "CONTRIBUTING.md"
    contributing.write_text("# Mine\n\nDo not lose this.\n")
    owners = dest / ".github" / "CODEOWNERS"
    owners.write_text("*  @someone-else\n")

    result = render("host/github", dest, ANSWERS)

    assert result.returncode == 0, result.stderr
    assert "Do not lose this." in contributing.read_text()
    assert "@someone-else" in owners.read_text()


def test_contributing_names_the_real_commands(rendered: Path) -> None:
    """CONTRIBUTING drifts into fiction as soon as it names a command that is gone."""
    body = (rendered / "CONTRIBUTING.md").read_text()
    assert "just setup" in body
    assert "just check" in body


# --- the enforcing copies --------------------------------------------------


def test_the_commit_range_is_checked_in_ci(rendered: Path) -> None:
    """A commit-message hook runs at `commit-msg`, which `--no-verify` defeats, and it sees
    only the message being written. Neither property survives a pull request: a bypassed
    commit stays bypassed, and a branch carries several messages.

    This job is inside wc-quality.yml, so the gate already needs it through `quality`.
    """
    workflow = yaml.safe_load((rendered / ".github" / "workflows" / "wc-quality.yml").read_text())
    assert "commits" in workflow["jobs"], "nothing validates the commit range"

    job = workflow["jobs"]["commits"]
    # Only a pull request defines a range; guessing one on a push checks nothing or
    # everything.
    assert "pull_request" in job["if"]

    checkout = next(s for s in job["steps"] if "checkout" in str(s.get("uses", "")))
    # The range resolves from the merge base, which a shallow clone does not contain.
    assert checkout["with"]["fetch-depth"] == 0
    assert checkout["with"]["persist-credentials"] is False


def test_the_range_check_skips_merge_commits(rendered: Path) -> None:
    """A merge subject is generated by the forge rather than written by a person."""
    workflow = yaml.safe_load((rendered / ".github" / "workflows" / "wc-quality.yml").read_text())
    script = "\n".join(str(step.get("run", "")) for step in workflow["jobs"]["commits"]["steps"])
    assert "--no-merges" in script


def test_a_hand_made_version_tag_is_caught(rendered: Path) -> None:
    """release-please derives the next version from tags, so a hand-made one makes it
    compute the wrong version. Checked in CI because a tag is pushed rather than committed,
    so no hook ever sees it.
    """
    workflow = yaml.safe_load((rendered / ".github" / "workflows" / "wc-quality.yml").read_text())
    steps = workflow["jobs"]["commits"]["steps"]
    tag_step = next(s for s in steps if "tag" in s.get("name", "").lower())
    # Guarded on the release layer having rendered, since a repo without it has no policy.
    assert "release-please-config.json" in tag_step["if"]


def test_the_whole_hook_set_runs_in_ci(rendered: Path) -> None:
    """A local hook is advisory: --no-verify defeats it, and a fresh clone has no shims
    until someone runs `just setup`. `--all-files` rather than a diff range, because a hook
    bypassed when a file was committed would otherwise stay bypassed forever.
    """
    workflow = yaml.safe_load((rendered / ".github" / "workflows" / "wc-quality.yml").read_text())
    script = "\n".join(str(step.get("run", "")) for step in workflow["jobs"]["quality"]["steps"])
    assert "prek run --all-files" in script


# --- governance ------------------------------------------------------------


def test_the_governance_script_ships_with_the_layer(rendered: Path) -> None:
    """Branch protection, required checks, merge types, and repository features are all
    API-only. Verified against a live repository: `gh api repos/<slug>` reports every merge
    and feature setting, a fresh repository returned zero rulesets and `Branch not
    protected`, and GitHub reads no committed file for any of it.

    A layer renders a file, so the API surface is a script this layer ships.
    """
    script = rendered / "scripts" / "repo_govern.py"
    assert script.is_file()
    body = script.read_text()
    # A secret passed to a script is a secret in a shell history.
    assert "secret" in body.lower()
    assert "gh api" in body or '"api"' in body


def test_the_gate_is_the_only_required_check(rendered: Path) -> None:
    """It lists every other job in `needs:` and receives `toJSON(needs)`, so a new job is
    covered without touching branch protection. A path-filtered required check that never
    starts would block every unrelated pull request forever.
    """
    body = (rendered / "scripts" / "repo_govern.py").read_text()
    assert 'REQUIRED_CHECKS = ["gate"]' in body


def test_squash_is_the_only_merge_type(rendered: Path) -> None:
    """A merge commit puts a second author's subject into the history release-please reads,
    and a rebase rewrites the commits CI already checked."""
    body = (rendered / "scripts" / "repo_govern.py").read_text()
    assert '"allow_squash_merge": True' in body
    assert '"allow_merge_commit": False' in body
    assert '"allow_rebase_merge": False' in body


def test_the_governance_recipes_render(rendered: Path) -> None:
    fragment = (rendered / ".just.d" / "github.just").read_text()
    assert "repo-govern" in fragment
    # A check that changes nothing is what CI can run.
    assert "--check" in fragment


def test_the_check_flag_changes_nothing(rendered: Path) -> None:
    """Asserted from the source rather than by calling the API: the check path must not
    reach a PATCH or a PUT."""
    body = (rendered / "scripts" / "repo_govern.py").read_text()
    # apply_settings returns before building the PATCH when checking.
    assert "if check or not differences:" in body
    assert "return differences" in body


def test_every_pinned_action_matches_its_version_comment(rendered: Path) -> None:
    """A comment naming a version the SHA does not point at is worse than no comment.

    zizmor's `ref-version-mismatch` audit is a NETWORK audit, so an `--offline` run reports
    none of these. Three shipped pins had a lying comment when the offline flag was dropped,
    including `dorny/paths-filter` at a v3.0.2 SHA under a `# v4.0.2` comment, and an
    annotated tag's SHA where the commit was needed.

    Checked here by shape rather than by resolving each tag: the network call belongs to
    zizmor, which the linter test above runs without --offline.
    """
    import re

    pattern = re.compile(r"uses:\s+(\S+)@([0-9a-f]{40})(?:\s+#\s*(\S+))?")
    for workflow in sorted((rendered / ".github" / "workflows").glob("*.yml")):
        for action, sha, tag in pattern.findall(workflow.read_text()):
            assert tag, f"{workflow.name}: {action}@{sha[:12]} carries no version comment"
            assert tag.startswith("v"), f"{workflow.name}: {action} comment {tag!r} is not a tag"


def test_opengrep_runs_from_the_fragments_the_layers_declare(rendered: Path) -> None:
    """The CI inversion applied to the ruleset: a language contributes its packs the same way
    it contributes a CodeQL language or a trivy mode."""
    workflow = yaml.safe_load((rendered / ".github" / "workflows" / "wc-security.yml").read_text())
    assert "opengrep" in workflow["jobs"]

    job = workflow["jobs"]["opengrep"]
    # A pack list of zero entries would scan with no rules and report success.
    assert job["if"] == "needs.discover.outputs.any_opengrep == 'true'"
    assert job["permissions"]["security-events"] == "write"

    discover = workflow["jobs"]["discover"]
    assert "opengrep" in discover["outputs"]
    assert "any_opengrep" in discover["outputs"]


def test_the_sarif_is_written_to_stdout_rather_than_the_documented_flag(rendered: Path) -> None:
    """`--sarif-output=FILE` is documented and silently writes nothing.

    Verified against opengrep 1.26.0: the flag produced no file at all, while the same scan
    with `--sarif` on stdout produced valid SARIF 2.1.0 with the finding in it. A workflow
    trusting the documented flag uploads an empty file and reports a clean scan.
    """
    body = (rendered / ".github" / "workflows" / "wc-security.yml").read_text()
    assert "--sarif . > opengrep.sarif" in body

    # The comment above the step names the broken flag to explain why it is avoided, so the
    # check is against the executable lines only.
    code = "\n".join(line for line in body.splitlines() if not line.strip().startswith("#"))
    assert "--sarif-output" not in code


def test_the_scan_does_not_fail_before_the_upload(rendered: Path) -> None:
    """`--error` would end the job on a finding, so the SARIF would never reach the security
    tab. A separate step reads the file back and fails there."""
    workflow = yaml.safe_load((rendered / ".github" / "workflows" / "wc-security.yml").read_text())
    steps = workflow["jobs"]["opengrep"]["steps"]
    names = [step.get("name", "") for step in steps]

    scan = next(s for s in steps if s.get("name") == "Scan")
    assert "--error" not in str(scan.get("run", "")), "a finding would end the job early"
    assert names.index("Upload results") < names.index("Fail on findings")
