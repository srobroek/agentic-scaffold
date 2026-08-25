"""iac/cdk: the AWS CDK app projen owns.

The ts-node trap is the whole reason this layer is shaped the way it is, and it was
reproduced rather than trusted: with projen's defaults, `npx projen` throws inside
ts-node's findAndReadConfig under TypeScript 7.0.2. Setting `projenrcTsOptions.runner`
fixes that, and is still not enough -- projen writes cdk.json's `app` as a separate
ts-node command, so `cdk synth` kept failing until `app` was overridden too. That second
override is absent from the architecture note and was found by running the tool.

The synth tests install real npm packages, so they are marked slow.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest
from conftest import mise_bin, render_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent

ANSWERS = "project_name: demo-cdk\ndefault_branch: main\n"

PROJEN = "projen@0.101.22"
TSX = "tsx@4.23.1"

# mise installs node outside the PATH a bare subprocess inherits. See conftest.mise_bin for
# why this is resolved through `mise which` rather than an installs/<tool>/latest path.
NODE_BIN = mise_bin("npm")
needs_node = pytest.mark.skipif(
    shutil.which("npm") is None and (NODE_BIN is None or not (NODE_BIN / "npm").is_file()),
    reason="npm absent",
)
slow = pytest.mark.skipif(
    os.environ.get("SCAFFOLD_SKIP_SLOW") == "1",
    reason="SCAFFOLD_SKIP_SLOW=1",
)


def node_env() -> dict[str, str]:
    env = dict(os.environ)
    if NODE_BIN is not None and NODE_BIN.is_dir():
        env["PATH"] = f"{NODE_BIN}:{env['PATH']}"
    return env


def render(dest: Path) -> subprocess.CompletedProcess[str]:
    return render_recipe("iac/cdk", dest, ANSWERS)


def run(dest: Path, *args: str, timeout: int = 900) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=dest,
        capture_output=True,
        text=True,
        check=False,
        env=node_env(),
        timeout=timeout,
    )


@pytest.fixture
def cdk(tmp_path: Path) -> Path:
    dest = tmp_path / "repo"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render(dest)
    assert result.returncode == 0, result.stderr
    return dest


@pytest.fixture(scope="session")
def _synth_root(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """A rendered app taken through the documented bootstrap.

    `projen new` writes a ts-node task and the synth that would replace it is the thing
    that fails, so tsx is installed first and the projenrc is run directly through it.

    Session-scoped, because the npm install and the synth cost about 40 seconds. Handed to a
    test through `synthesised`, which copies it: two tests mutate the tree, and a shared
    mutable directory raced under `-n auto`. One worker installed typescript@7 and re-synthed
    while another read, and projen's `install:ci` task then ran `npm ci` against a lockfile
    mid-write.
    """
    cdk = tmp_path_factory.mktemp("cdk-synth")
    subprocess.run(["git", "init", "-q", str(cdk)], check=True)
    result = render(cdk)
    assert result.returncode == 0, result.stderr

    assert run(cdk, "npm", "init", "-y").returncode == 0
    install = run(cdk, "npm", "install", "--no-audit", "--no-fund", PROJEN, TSX)
    assert install.returncode == 0, install.stderr[-2000:]
    # CI unset for the synth, deliberately. projen branches on `process.env.CI`
    # (node-package.js:588): truthy picks its `install:ci` task, which runs `npm ci`. The synth
    # is the step that ADDS the CDK dependencies to package.json, so at that moment the lockfile
    # predates them and `npm ci` refuses with EUSAGE `Missing: aws-cdk@... from lock file`. An
    # `npm install` is the correct command for a tree whose manifest just changed.
    #
    # This is why five CDK tests errored only in CI. Reproduced locally with `CI=true pytest`.
    env = node_env()
    env.pop("CI", None)
    synth = subprocess.run(
        ("npx", "tsx", ".projenrc.ts"),
        cwd=cdk,
        capture_output=True,
        text=True,
        check=False,
        env=env,
        timeout=900,
    )
    # The HEAD of each stream, not the tail. npm prints its own usage when it rejects an
    # argument, and that usage is long enough that a tail-truncated message shows only the
    # flag list and hides the one line naming the cause. Two CI cycles were spent guessing
    # at `npm ci` failures whose reason had been scrolled off.
    assert synth.returncode == 0, (
        "stdout:\n" + synth.stdout[:4000] + "\n\nstderr:\n" + synth.stderr[:4000]
    )
    return cdk


@pytest.fixture
def synthesised(_synth_root: Path, tmp_path: Path) -> Path:
    """A private copy of the synthesised tree.

    The expensive part happens once per session; the copy is cheap against it and is what
    makes a mutating test safe in parallel.
    """
    target = tmp_path / "synth"
    shutil.copytree(_synth_root, target, symlinks=True)
    return target


# --- what the projenrc must say --------------------------------------------


def test_the_projenrc_renders(cdk: Path) -> None:
    assert (cdk / ".projenrc.ts").is_file()


def test_both_ts_node_call_sites_are_overridden(cdk: Path) -> None:
    """Two separate overrides, because one was not enough.

    `projenrcTsOptions.runner` governs how the projenrc executes. cdk.json's `app` is
    written independently, so `cdk synth` still ran ts-node until `app` was set as well.
    """
    body = (cdk / ".projenrc.ts").read_text()
    assert "TypeScriptRunner.tsx()" in body
    assert "app: 'npx tsx src/main.ts'" in body

    # ts-node is named at length in the comments explaining why it is avoided, so the
    # check is against code with every comment removed.
    code = "\n".join(
        line for line in body.splitlines() if not line.strip().startswith(("//", "*", "/*"))
    )
    assert "ts-node" not in code, "no executable line may invoke ts-node"


def test_the_package_manager_is_explicit(cdk: Path) -> None:
    """projen otherwise defaults to yarn_classic and warns the option will become
    required. Nothing else in the scaffold uses yarn."""
    assert "NodePackageManager.NPM" in (cdk / ".projenrc.ts").read_text()


def test_projen_owns_no_ci_and_no_linter(cdk: Path) -> None:
    """host/* owns CI and lang/ts owns linting, so projen's copies of both are off."""
    body = (cdk / ".projenrc.ts").read_text()
    assert "github: false" in body
    assert "eslint: false" in body


def test_gitignore_patterns_go_through_the_api(cdk: Path) -> None:
    """projen marks .gitignore read-only, so a pattern added by hand is lost at the next
    synth. addPatterns is the only way to reach projen's copy."""
    assert "project.gitignore.addPatterns(" in (cdk / ".projenrc.ts").read_text()


# --- fragments -------------------------------------------------------------


def test_the_security_fragment_supports_codeql(cdk: Path) -> None:
    """Constructs are TypeScript, so CodeQL reads them. iac/terraform reports false for
    the same key because CodeQL has no HCL extractor."""
    import yaml

    fragment = yaml.safe_load((cdk / ".github" / "security.d" / "cdk.yml").read_text())
    assert fragment["codeql"]["supported"] is True
    assert fragment["codeql"]["language"] == "javascript-typescript"
    assert "misconfig" in fragment["trivy"]["scanners"]


def test_the_synthesised_output_is_ignored_but_projen_state_is_not(cdk: Path) -> None:
    """cdk.out is regenerated and cdk.context.json pins a lookup to one account, so both
    are ignored. .projen/ is committed, so a fresh clone can run tasks before a synth."""
    fragment = (cdk / ".gitignore.d" / "cdk").read_text()
    patterns = [
        line.strip() for line in fragment.splitlines() if line.strip() and not line.startswith("#")
    ]
    assert "cdk.out/" in patterns
    assert "cdk.context.json" in patterns
    assert not any(p.startswith(".projen") for p in patterns)


def test_the_recipes_keep_bootstrap_separate_from_synth(cdk: Path) -> None:
    """The order is load-bearing: the first synth must run through tsx directly, because
    the default task still points at ts-node until that synth rewrites it."""
    fragment = (cdk / ".just.d" / "cdk.just").read_text()
    assert "cdk-bootstrap-projen" in fragment
    assert "npx tsx .projenrc.ts" in fragment
    # A deploy stays manual; nothing wires it into CI.
    assert "--require-approval any-change" in fragment
    # just's own parameters survived rendering.
    assert "npx cdk diff {{ env }}" in fragment


# --- the real tool ---------------------------------------------------------


@needs_node
@slow
def test_the_bootstrap_synthesises(synthesised: Path) -> None:
    """The fixture itself is the assertion: it fails if the documented order does not
    produce a working app."""
    assert (synthesised / "cdk.json").is_file()
    assert (synthesised / "src" / "main.ts").is_file()


@needs_node
@slow
def test_the_synth_rewrites_both_commands_to_tsx(synthesised: Path) -> None:
    """After the first synth neither call site runs ts-node."""
    tasks = json.loads((synthesised / ".projen" / "tasks.json").read_text())
    assert tasks["tasks"]["default"]["steps"] == [{"execArgs": ["tsx", ".projenrc.ts"]}]

    app = json.loads((synthesised / "cdk.json").read_text())["app"]
    assert app == "npx tsx src/main.ts"
    assert "ts-node" not in app


@needs_node
@slow
def test_projen_writes_no_workflows(synthesised: Path) -> None:
    """`github: false` honoured, so the host layer's reusable workflows are the only CI."""
    assert not (synthesised / ".github" / "workflows").exists()


@needs_node
@slow
def test_everything_works_under_typescript_7(synthesised: Path) -> None:
    """The regression this layer exists to prevent.

    With projen's defaults, `npx projen` throws in ts-node's findAndReadConfig at
    TypeScript 7.0.2 and `cdk synth` fails with it. Both must pass here.
    """
    assert (
        run(synthesised, "npm", "install", "--no-audit", "--no-fund", "typescript@7").returncode
        == 0
    )

    installed = json.loads(
        (synthesised / "node_modules" / "typescript" / "package.json").read_text()
    )["version"]
    assert installed.startswith("7."), f"expected TypeScript 7, got {installed}"

    projen = run(synthesised, "npx", "projen")
    assert projen.returncode == 0, projen.stdout[-1500:] + projen.stderr[-1500:]

    synth = run(synthesised, "npx", "cdk", "synth", "--quiet")
    assert synth.returncode == 0, synth.stdout[-1500:] + synth.stderr[-1500:]


@needs_node
@slow
def test_a_resynth_leaves_the_layered_files_intact(synthesised: Path) -> None:
    """The bead's acceptance criterion. projen regenerates its own files and must not
    touch what another layer contributed."""
    (synthesised / ".just.d").mkdir(exist_ok=True)
    (synthesised / ".mise" / "conf.d").mkdir(parents=True, exist_ok=True)
    probes = {
        synthesised / ".just.d" / "probe.just": "# layered\n",
        synthesised / ".mise" / "conf.d" / "probe.toml": "[tools]\n",
        synthesised / ".gitignore.d" / "probe": "layered\n",
    }
    for path, body in probes.items():
        path.write_text(body)

    assert run(synthesised, "npx", "projen").returncode == 0

    for path, body in probes.items():
        assert path.read_text() == body, f"{path.name} was overwritten by the synth"
    assert (synthesised / ".github" / "security.d" / "cdk.yml").is_file()
