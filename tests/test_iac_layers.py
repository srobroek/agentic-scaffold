"""iac/terraform: the OpenTofu root module, the per-environment files, and the fragments.

Where a test needs OpenTofu or tflint it runs the real binary against rendered output.
Reading a template proves nothing: `terraform_tflint` was named `tflint` in the package
this layer was ported from, `--severity=HIGH,CRITICAL` split into two arguments as an
unquoted flow sequence, and tflint applied none of `.tflint.hcl` when run without an
explicit `--config`. Every one of those rendered and read correctly.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import render_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent
LAYER = REPO_ROOT / "recipes" / "iac" / "terraform"

ANSWERS = """\
project_name: demo
environments: [dev, prod]
aws_region: eu-west-1
state_bucket: demo-tofu-state
default_branch: main
"""

HOOKS_ANSWERS = """\
hook_exclude_patterns: []
max_file_kb: 500
commit_scopes: []
"""

needs_tofu = pytest.mark.skipif(shutil.which("tofu") is None, reason="tofu absent from PATH")
needs_tflint = pytest.mark.skipif(shutil.which("tflint") is None, reason="tflint absent from PATH")
needs_just = pytest.mark.skipif(shutil.which("just") is None, reason="just absent from PATH")


def render(layer: str, dest: Path, answers: str = ANSWERS) -> subprocess.CompletedProcess[str]:
    return render_recipe(layer, dest, answers)


def tofu(dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["tofu", *args], cwd=dest, capture_output=True, text=True, check=False)


@pytest.fixture
def terraform(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render("iac/terraform", dest)
    assert result.returncode == 0, result.stderr
    return dest


# --- layout ----------------------------------------------------------------


def test_one_root_module_with_per_environment_files(terraform: Path) -> None:
    """The layout is a single root module, not a root module per environment.

    Both of the fixed decisions depend on it: `-backend-config=envs/<env>.tfbackend`
    is partial configuration OF one backend block, and `tofu test` reads `tests/`
    under the root module. A root module per environment would need the tests
    directory passed explicitly and would duplicate the provider block per
    environment, which is the duplication partial configuration exists to remove.
    """
    infra = terraform / "infra"
    for name in ("main.tf", "variables.tf", "outputs.tf", "versions.tf"):
        assert (infra / name).is_file(), f"{name} belongs to the single root module"

    # An environment is a pair of files, never a directory.
    for env in ("dev", "prod"):
        assert (infra / "envs" / f"{env}.tfbackend").is_file()
        assert (infra / "envs" / f"{env}.tfvars").is_file()
        assert not (infra / "envs" / env).is_dir(), (
            f"envs/{env}/ is a directory, so the layout reverted to a root module per "
            "environment and the -backend-config path no longer applies"
        )


def test_the_backend_block_is_empty_for_partial_configuration(terraform: Path) -> None:
    """An `s3` backend with no arguments, so every value comes from -backend-config.

    A populated block would bind the root module to one environment, and a value
    present in both places is an error rather than an override.
    """
    versions = (terraform / "infra" / "versions.tf").read_text()
    assert 'backend "s3" {}' in versions


def settings(path: Path) -> dict[str, str]:
    """The key = value pairs of an HCL-ish file, with comments and blanks dropped.

    Asserting against raw text matches the explanatory comments as readily as the
    configuration, which is how three earlier versions of these tests passed or failed
    on prose rather than on what tofu reads.
    """
    found = {}
    for line in path.read_text().splitlines():
        line = line.split("#", 1)[0].strip()
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        found[key.strip()] = value.strip().strip('"')
    return found


def test_the_backend_files_carry_use_lockfile_and_no_lock_table(terraform: Path) -> None:
    """S3 native locking, which is the reason the version floor is 1.10."""
    backend = settings(terraform / "infra" / "envs" / "dev.tfbackend")
    assert backend["use_lockfile"] == "true"
    assert not any("dynamodb" in key.lower() for key in backend), (
        "the decision excludes a DynamoDB lock table"
    )

    # Each environment writes to its own key, or two environments share one state file.
    assert backend["key"] == "dev/tofu.tfstate"
    assert settings(terraform / "infra" / "envs" / "prod.tfbackend")["key"] == "prod/tofu.tfstate"


def test_environments_drive_the_rendered_files(tmp_path: Path) -> None:
    """`environments` is what decides which files exist, not a fixed dev/prod pair."""
    dest = tmp_path / "three"
    dest.mkdir()
    answers = ANSWERS.replace("[dev, prod]", "[sandbox, staging, live]")
    assert render("iac/terraform", dest, answers).returncode == 0

    envs = dest / "infra" / "envs"
    assert sorted(p.name for p in envs.glob("*.tfbackend")) == [
        "live.tfbackend",
        "sandbox.tfbackend",
        "staging.tfbackend",
    ]
    # The first entry is the default for every recipe taking an env argument.
    assert 'tofu_default_env := "sandbox"' in (dest / ".just.d" / "terraform.just").read_text()


def test_bootstrap_keeps_local_state(terraform: Path) -> None:
    """bootstrap creates the state bucket, so it cannot store its state in it."""
    versions = (terraform / "infra" / "bootstrap" / "versions.tf").read_text()
    # Comments stripped: the file explains at length why there is no backend, and
    # matching raw text finds that prose rather than a block.
    code = "\n".join(line.split("#", 1)[0] for line in versions.splitlines())
    assert "backend" not in code, (
        "bootstrap must not declare a backend: it creates the bucket the other root "
        "module stores state in"
    )
    main = (terraform / "infra" / "bootstrap" / "main.tf").read_text()
    assert "prevent_destroy = true" in main, "a lost state bucket is unrecoverable"


def test_the_child_module_source_resolves_from_the_root_module(terraform: Path) -> None:
    """`./modules/<name>`, not `../modules/<name>`.

    `tofu test` resolves a module source relative to the root module rather than to
    the test file, so the `../` form fails under both plan and test. Verified against
    OpenTofu 1.12.5, where it reported "Module not installed".
    """
    main = (terraform / "infra" / "main.tf").read_text()
    assert 'source = "./modules/naming"' in main


# --- the real tools --------------------------------------------------------


@needs_tofu
def test_every_root_module_initialises_and_validates(terraform: Path) -> None:
    """-backend=false, so this needs no credentials and no -backend-config."""
    for root in (terraform / "infra", terraform / "infra" / "bootstrap"):
        init = tofu(root, "init", "-backend=false", "-input=false")
        assert init.returncode == 0, f"{root.name}: {init.stderr}"
        validate = tofu(root, "validate")
        assert validate.returncode == 0, f"{root.name}: {validate.stdout}{validate.stderr}"


@needs_tofu
def test_the_rendered_configuration_is_already_formatted(terraform: Path) -> None:
    """`tofu fmt -check` passes on rendered output, so the first commit is not a reformat."""
    result = tofu(terraform / "infra", "fmt", "-recursive", "-check", "-diff")
    assert result.returncode == 0, result.stdout


@needs_tofu
def test_the_test_suite_passes_without_credentials(terraform: Path) -> None:
    """`tofu test` from infra/ with no -test-directory flag.

    It reads tests/ under the root module by default, and `mock_provider` keeps every
    run off the provider API. Without the mock the aws provider resolves a region and
    credentials during plan, so the suite fails wherever no AWS profile exists.
    """
    assert tofu(terraform / "infra", "init", "-backend=false", "-input=false").returncode == 0
    result = tofu(terraform / "infra", "test")
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout


@needs_tofu
def test_the_environment_validation_rejects_an_unknown_environment(terraform: Path) -> None:
    """The variable validation is what catches a wrong or missing -var-file.

    Asserted through the suite's own `expect_failures` run, so this fails if the
    validation block is dropped from variables.tf.
    """
    variables = (terraform / "infra" / "variables.tf").read_text()
    assert "validation {" in variables
    assert 'contains(["dev", "prod"], var.environment)' in variables


@needs_tflint
def test_tflint_reports_nothing_on_rendered_output(terraform: Path) -> None:
    """The layer passes its own lint gate at the warning threshold.

    `--config` with an absolute path is mandatory: tflint reads only its working
    directory's config and never a parent's, and `--recursive` visits infra/,
    infra/modules/*, and infra/bootstrap each as its own working directory. Verified
    against tflint 0.64.0, where the flag's absence applied the default rules instead
    and reported findings `.tflint.hcl` had disabled.

    The aws ruleset is skipped when it cannot be downloaded, which is what an
    unauthenticated GitHub API rate limit looks like.
    """
    config = terraform / ".tflint.hcl"
    init = subprocess.run(
        ["tflint", "--init", f"--config={config}"],
        cwd=terraform,
        capture_output=True,
        text=True,
        check=False,
    )
    if init.returncode != 0:
        pytest.skip(f"tflint --init could not fetch the ruleset: {init.stderr.strip()[:120]}")

    result = subprocess.run(
        [
            "tflint",
            "--recursive",
            f"--config={config}",
            "--minimum-failure-severity=warning",
        ],
        cwd=terraform,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@needs_tflint
def test_the_child_module_declares_a_required_version(terraform: Path) -> None:
    """`terraform_required_version` applies to a child module, not only a root one.

    Verified against tflint 0.64.0: omitting it from modules/naming failed the lint
    gate with one warning. The comment in that module previously claimed the opposite.
    """
    module = (terraform / "infra" / "modules" / "naming" / "main.tf").read_text()
    assert "required_version" in module


# --- fragments -------------------------------------------------------------


def test_the_hook_fragment_names_the_real_hook_ids(terraform: Path) -> None:
    """The ids are `terraform_*`, and the tflint one is `terraform_tflint`.

    pre-commit-terraform ships no `tofu_*` set and no bare `tflint` id. The package
    this layer was ported from used `tflint`, which prek rejects as unknown.
    """
    fragment = yaml.safe_load((terraform / ".pre-commit.d" / "terraform.yaml").read_text())
    ids = {hook["id"] for repo in fragment["repos"] for hook in repo["hooks"]}
    assert {"terraform_fmt", "terraform_validate", "terraform_tflint", "terraform_trivy"} <= ids


def test_the_trivy_severity_survives_as_one_argument(terraform: Path) -> None:
    """`--severity=HIGH,CRITICAL` must be quoted or YAML splits it on the comma.

    Unquoted inside `[...]` it is a flow sequence of two entries, and trivy then
    receives a bare `CRITICAL` as a positional argument. This is why the value is
    quoted in the fragment.
    """
    fragment = yaml.safe_load((terraform / ".pre-commit.d" / "terraform.yaml").read_text())
    for repo in fragment["repos"]:
        for hook in repo["hooks"]:
            if hook["id"] == "terraform_trivy":
                assert hook["args"] == ["--args=--severity=HIGH,CRITICAL"]
                return
    pytest.fail("terraform_trivy is absent from the fragment")


def test_the_hooks_that_invoke_a_binary_pin_it_to_tofu(terraform: Path) -> None:
    """PCT_TFPATH, because the hook scripts prefer `terraform` over `tofu`.

    Their search order is --tf-path, PCT_TFPATH, TERRAGRUNT_TFPATH, `terraform`, then
    `tofu`. On a machine carrying both, the unset case runs terraform against a
    repository this layer pins to OpenTofu.

    `terraform_trivy` is excluded deliberately: it calls `trivy conf` and never the
    IaC binary, so pinning it there would assert something the hook cannot honour.
    """
    fragment = yaml.safe_load((terraform / ".pre-commit.d" / "terraform.yaml").read_text())
    needs_binary = {"terraform_fmt", "terraform_validate", "terraform_tflint"}
    seen = set()
    for repo in fragment["repos"]:
        if "pre-commit-terraform" not in repo.get("repo", ""):
            continue
        for hook in repo["hooks"]:
            if hook["id"] not in needs_binary:
                continue
            seen.add(hook["id"])
            assert hook.get("env", {}).get("PCT_TFPATH") == "tofu", (
                f"{hook['id']} does not pin the binary, so it may run terraform"
            )
    assert seen == needs_binary, f"a hook went missing from the fragment: {needs_binary - seen}"


def test_the_tflint_hook_passes_an_absolute_config_path(terraform: Path) -> None:
    """`__GIT_WORKING_DIR__` is substituted by the hook script with the repo root.

    The script chdirs into each directory it lints, and tflint reads no parent's
    config, so a relative path would silently lint with the default rules.
    """
    fragment = yaml.safe_load((terraform / ".pre-commit.d" / "terraform.yaml").read_text())
    for repo in fragment["repos"]:
        for hook in repo["hooks"]:
            if hook["id"] == "terraform_tflint":
                joined = " ".join(hook["args"])
                assert "__GIT_WORKING_DIR__/.tflint.hcl" in joined
                assert "--minimum-failure-severity=warning" in joined
                return
    pytest.fail("terraform_tflint is absent from the fragment")


def test_the_tflint_config_sits_at_the_repository_root(terraform: Path) -> None:
    """Not under infra/. tflint never searches a parent directory for its config."""
    assert (terraform / ".tflint.hcl").is_file()
    assert not (terraform / "infra" / ".tflint.hcl").exists()


def test_the_lock_file_is_committed_and_state_is_not(terraform: Path) -> None:
    """The gitignore fragment's two load-bearing decisions."""
    fragment = (terraform / ".gitignore.d" / "terraform").read_text()
    assert "*.tfstate" in fragment
    assert "*.tfplan" in fragment, "a plan holds every variable value in cleartext"
    assert ".terraform.lock.hcl" not in [
        line.strip() for line in fragment.splitlines() if not line.startswith("#")
    ], "the lock file is committed: it is what pins provider versions across the team"
    # envs/*.tfvars is committed, so the broad tfvars rule must not swallow it.
    assert "!infra/envs/*.tfvars" in fragment


def test_the_security_fragment_asks_for_the_misconfig_scanner(terraform: Path) -> None:
    """CodeQL has no HCL extractor, so trivy's `misconfig` is what reads this layer."""
    fragment = yaml.safe_load((terraform / ".github" / "security.d" / "terraform.yml").read_text())
    assert fragment["codeql"]["supported"] is False
    assert "misconfig" in fragment["trivy"]["scanners"]


# --- integration with the aggregating layers -------------------------------


def test_the_fragment_reaches_the_root_config_when_hooks_render_after(tmp_path: Path) -> None:
    """The render-order case this layer exists to exercise.

    quality/hooks folds `.pre-commit.d/*` into the root config, so rendering it before
    this layer leaves the terraform fragment out with nothing to report the omission:
    prek reads the merged file and never sees the fragment directory.
    """
    dest = tmp_path / "both"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("iac/terraform", dest).returncode == 0
    assert render("quality/hooks", dest, HOOKS_ANSWERS).returncode == 0

    merged = yaml.safe_load((dest / ".pre-commit-config.yaml").read_text())
    ids = {hook["id"] for repo in merged["repos"] for hook in repo["hooks"]}
    assert "terraform_fmt" in ids, "the terraform fragment did not reach the root config"
    assert "trailing-whitespace" in ids, "the hygiene fragment was lost"


@needs_just
def test_every_recipe_carries_its_own_description(tmp_path: Path) -> None:
    """`just` takes the comment on the line above a recipe as its `--list` description.

    Rationale therefore goes above a blank line, or a sentence fragment becomes the
    description. Three shipped fragments had this defect before it was caught.
    """
    dest = tmp_path / "justrepo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("iac/terraform", dest).returncode == 0
    assert render("workspace/just", dest, "").returncode == 0

    listing = subprocess.run(
        ["just", "--list"], cwd=dest, capture_output=True, text=True, check=False
    )
    assert listing.returncode == 0, listing.stderr

    described = {}
    for line in listing.stdout.splitlines():
        if "#" not in line or not line.startswith("    "):
            continue
        name, _, description = line.strip().partition("#")
        described[name.split()[0]] = description.strip()

    for recipe in ("tf", "tf-plan", "tf-apply", "tf-lint", "tf-test", "tf-bootstrap"):
        assert recipe in described, f"{recipe} has no description"
        text = described[recipe]
        # A fragment of rationale reads as a lowercase clause or a trailing comma.
        assert text[0].isupper(), f"{recipe}'s description looks like prose: {text!r}"
        assert not text.endswith(","), f"{recipe}'s description is a sentence fragment: {text!r}"


@needs_just
def test_the_recipes_keep_their_parameters_through_rendering(tmp_path: Path) -> None:
    """just shares jinja's `{{ }}`, so the fragment body is wrapped in `{% raw %}`.

    Without it every `{{ env }}` is substituted at render time with an undefined
    variable and each recipe silently loses its argument.
    """
    dest = tmp_path / "params"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    assert render("iac/terraform", dest).returncode == 0

    fragment = (dest / ".just.d" / "terraform.just").read_text()
    assert "tf-plan env=tofu_default_env:" in fragment
    assert "envs/{{ env }}.tfbackend" in fragment, "the parameter was substituted away"
    # The one line that IS interpolated.
    assert 'tofu_default_env := "dev"' in fragment


# --- CI --------------------------------------------------------------------


def test_the_workflows_contribute_the_documented_jobs(terraform: Path) -> None:
    """`lint-tofu` and `plan-tofu` are reusable; apply is triggered, not called."""
    workflows = terraform / ".github" / "workflows"
    assert (workflows / "wc-lint-tofu.yml").is_file()
    assert (workflows / "wc-plan-tofu.yml").is_file()

    plan = yaml.safe_load((workflows / "wc-plan-tofu.yml").read_text())
    assert "workflow_call" in plan[True]
    # One plan job per environment, which is what the CI rules specify.
    assert plan["jobs"]["plan"]["strategy"]["matrix"]["environment"] == ["dev", "prod"]

    apply = yaml.safe_load((workflows / "tofu-apply.yml").read_text())
    assert "workflow_dispatch" in apply[True]
    assert "workflow_call" not in apply[True], (
        "apply must not be callable from the gate: it is a manual action"
    )
    assert "push" not in apply[True], "an apply on merge applies what nobody reviewed"


def test_apply_is_manual_serialised_and_default_branch_only(terraform: Path) -> None:
    """The three properties that stop two people applying at once."""
    apply = yaml.safe_load((terraform / ".github" / "workflows" / "tofu-apply.yml").read_text())
    job = apply["jobs"]["apply"]

    assert "refs/heads/main" in job["if"]
    # Never cancelled: a cancelled apply leaves state describing half-created resources.
    assert apply["concurrency"]["cancel-in-progress"] is False
    # The GitHub environment is where a required reviewer is configured.
    assert job["environment"]


def test_the_plan_job_carries_the_permissions_it_needs(terraform: Path) -> None:
    """id-token for OIDC, pull-requests for the comment.

    A called workflow cannot hold more than its caller granted, so these have to be
    declared here as well as in the caller.
    """
    plan = yaml.safe_load((terraform / ".github" / "workflows" / "wc-plan-tofu.yml").read_text())
    permissions = plan["jobs"]["plan"]["permissions"]
    assert permissions["id-token"] == "write"
    assert permissions["pull-requests"] == "write"


def test_the_lint_job_passes_a_token_to_tflint(terraform: Path) -> None:
    """`tflint --init` fetches the aws ruleset from the GitHub API.

    Unauthenticated it returns 403 for rate limiting, after which every directory
    reports "Plugin not found" -- observed on a real run of this layer.
    """
    workflow = (terraform / ".github" / "workflows" / "wc-lint-tofu.yml").read_text()
    assert "GITHUB_TOKEN" in workflow


def test_no_action_is_pinned_to_a_tag(terraform: Path) -> None:
    """Every `uses:` is a 40-character SHA with the tag in a trailing comment."""
    for workflow in (terraform / ".github" / "workflows").glob("*.yml"):
        for number, line in enumerate(workflow.read_text().splitlines(), start=1):
            stripped = line.strip()
            if not stripped.startswith("- uses:") and "uses:" not in stripped:
                continue
            if "uses:" not in stripped:
                continue
            reference = stripped.split("uses:", 1)[1].strip().split()[0]
            if reference.startswith("./"):
                continue
            _, _, version = reference.partition("@")
            assert len(version) == 40 and all(c in "0123456789abcdef" for c in version), (
                f"{workflow.name}:{number} pins {reference!r} rather than a SHA"
            )


def test_the_gitlab_fragment_declares_known_stages(terraform: Path) -> None:
    """A job naming a stage absent from `stages:` fails the whole pipeline.

    `gen_gitlab_stages.py` rebuilds that list from the fragments, and it refuses a
    stage outside its own STAGE_ORDER, so the two have to agree.
    """
    fragment = yaml.safe_load((terraform / ".gitlab" / "ci" / "terraform.yml").read_text())
    known = {"quality", "lint", "test", "security", "build", "deploy"}
    for name, job in fragment.items():
        if name.startswith("."):
            continue
        assert job["stage"] in known, f"{name} names the unknown stage {job['stage']!r}"

    # Apply is manual and serialised on GitLab too.
    assert fragment["tofu-apply"]["when"] == "manual"
    assert "resource_group" in fragment["tofu-apply"]


def test_every_gitlab_job_is_namespaced(terraform: Path) -> None:
    """Merge order across the include glob is not deterministic.

    No two fragments may set the same key, so every job and anchor here is prefixed.
    """
    fragment = yaml.safe_load((terraform / ".gitlab" / "ci" / "terraform.yml").read_text())
    for name in fragment:
        assert name.lstrip(".").startswith("tofu"), f"{name} is not namespaced to this layer"


# --- the lock script -------------------------------------------------------


def test_the_lock_script_names_both_operating_systems(terraform: Path) -> None:
    """A lock generated on a Mac carries darwin only, and CI then fails on init.

    The failure lands in CI rather than at the commit that caused it, which is the
    reason this script exists rather than pre-commit-terraform's own lock hook: that
    one triggers on an existing lock file, so it skips the commit that first adds a
    provider.
    """
    script = (terraform / "scripts" / "tofu_lock.sh").read_text()
    for platform in ("linux_amd64", "linux_arm64", "darwin_arm64", "darwin_amd64"):
        assert platform in script


def test_the_lock_script_avoids_bash_4_builtins(terraform: Path) -> None:
    """macOS ships bash 3.2, where `mapfile` and `readarray` do not exist.

    A recipe using either reports success while doing nothing.
    """
    # Comments stripped: the script names both builtins in the comment explaining why
    # it uses neither.
    script = (terraform / "scripts" / "tofu_lock.sh").read_text()
    code = "\n".join(line.split("#", 1)[0] for line in script.splitlines())
    assert "mapfile" not in code
    assert "readarray" not in code


@needs_tofu
def test_the_lock_script_writes_a_lock_for_every_root(terraform: Path) -> None:
    """Runs the real script, since a lock file it fails to write looks like a pass."""
    script = terraform / "scripts" / "tofu_lock.sh"
    script.chmod(0o755)
    result = subprocess.run(
        [str(script)], cwd=terraform, capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stdout + result.stderr

    for root in ("infra", "infra/bootstrap"):
        lock = terraform / root / ".terraform.lock.hcl"
        assert lock.is_file(), f"{root} has no lock file"
        text = lock.read_text()
        assert 'provider "registry.opentofu.org/hashicorp/aws"' in text
        # One h1 hash per platform per provider, so a single-platform lock is short.
        assert text.count("h1:") >= 4, f"{root}'s lock covers too few platforms"


def test_empty_versions_resolve_and_never_render_blank(tmp_path: Path) -> None:
    """Empty answers ask mise for the newest release, with the recipe's floor as
    the offline fallback; either way no rendered pin may be blank."""
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("iac/terraform", dest, ANSWERS)  # ANSWERS pins no versions
    assert result.returncode == 0, result.stderr

    mise = (dest / ".mise" / "conf.d" / "terraform.toml").read_text()
    for tool in ("opentofu", "tflint"):
        pin = [line for line in mise.splitlines() if line.startswith(f"{tool} = ")][0]
        assert pin.split('"')[1], f"{tool} pin rendered blank"
    versions_tf = (dest / "infra" / "versions.tf").read_text()
    assert 'required_version = ">= "' not in versions_tf
