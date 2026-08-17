"""workspace/moon: the project graph over an existing workspace.

Every assertion about a moon key was learned by running moon 2.4.6 against rendered
output, because the published schema and the shipped CLI disagree. `runner:` does not
exist (it is `pipeline:`), `vcs.manager` is rejected in favour of `vcs.client` even
though workspace.json still documents `manager`, and a project's kind is `layer:` where
1.x used `type:`. Each of those rendered happily and failed only when moon read it.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from conftest import mise_bin
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

RUST = 'layout: rust\nproject_name: demo\nmembers: "crates/*"\nrust_edition: "2024"\n'
TS = 'layout: ts\nproject_name: demo\nmembers: "packages/*"\n'
PY = 'layout: python\nproject_name: demo\nmembers: "packages/*"\npython_version: "3.13"\n'
GO = (
    'layout: go\nproject_name: demo\nmembers: ""\n'
    'go_module_path: github.com/srobroek/demo\ngo_version: "1.26"\n'
)

# The CLI mise installs, which is not on PATH by default.
# Resolved through mise. See conftest.mise_bin for why not an installs/<tool>/latest path.
_MOON_BIN = mise_bin("moon")
MOON_BIN = (_MOON_BIN / "moon") if _MOON_BIN else Path("moon")
MOON = str(MOON_BIN) if MOON_BIN.is_file() else shutil.which("moon")
needs_moon = pytest.mark.skipif(MOON is None, reason="moon absent")


def render(layer: str, dest: Path, answers: str) -> subprocess.CompletedProcess[str]:
    answers_file = dest.parent / f"{dest.name}-{layer.replace('/', '-')}.yml"
    answers_file.write_text(answers)
    return subprocess.run(
        [sys.executable, str(RENDER), layer, str(dest), "--answers", str(answers_file)],
        capture_output=True,
        text=True,
        check=False,
    )


def git_repo(path: Path) -> None:
    """A repo with a commit on the branch moon's `vcs.defaultBranch` names.

    `-b main` and the empty base commit both matter. moon resolves a merge base against that
    branch to decide what changed, and a fresh repo with no commit has none: it warns `Unable to
    resolve a merge base between the base and head revisions` and the run fails. Locally the
    warning never appeared because `init.defaultBranch` is already `main` here, so three tests
    passed on this machine and failed in CI.
    """
    subprocess.run(["git", "init", "-q", "-b", "main", str(path)], check=True)
    for key, value in (("user.email", "t@e.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(path), "config", key, value], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "--allow-empty", "-m", "base"],
        check=True,
        capture_output=True,
    )


def commit(path: Path) -> None:
    subprocess.run(["git", "-C", str(path), "add", "-A"], check=True)
    subprocess.run(
        ["git", "-C", str(path), "commit", "-q", "-m", "wip"],
        check=False,
        capture_output=True,
    )


def moon(dest: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([MOON, *args], cwd=dest, capture_output=True, text=True, check=False)


def workspace(tmp_path: Path, name: str, answers: str) -> Path:
    """A rendered monorepo with moon over it, and two members in a dependency chain."""
    dest = tmp_path / name
    dest.mkdir(parents=True)
    git_repo(dest)
    assert render("workspace/monorepo", dest, answers).returncode == 0

    if "rust" in answers:
        for member, extra in (
            ("core", ""),
            ("api", '\n[dependencies]\ncore = { path = "../core" }\n'),
        ):
            src = dest / "crates" / member / "src"
            src.mkdir(parents=True)
            (src / "lib.rs").write_text("pub fn f() -> u8 { 1 }\n")
            (dest / "crates" / member / "Cargo.toml").write_text(
                f'[package]\nname = "{member}"\nversion = "0.1.0"\n'
                f"edition.workspace = true\n{extra}"
            )
    elif "ts" in answers:
        for member, deps in (("ui", ""), ("app", ',"dependencies":{"ui":"workspace:*"}')):
            src = dest / "packages" / member / "src"
            src.mkdir(parents=True)
            (src / "index.ts").write_text("export const x = 1;\n")
            (dest / "packages" / member / "package.json").write_text(
                f'{{"name":"{member}","version":"0.1.0"{deps}}}'
            )
    elif "python" in answers:
        for member, deps in (("lib", ""), ("svc", '\ndependencies = ["lib>=0.1.0"]')):
            pkg = dest / "packages" / member / "src" / member
            pkg.mkdir(parents=True)
            (pkg / "__init__.py").touch()
            (dest / "packages" / member / "pyproject.toml").write_text(
                f'[project]\nname = "{member}"\nversion = "0.1.0"\n'
                f'requires-python = ">=3.13"{deps}\n'
            )
    else:
        for member in ("serve", "tool"):
            path = dest / "cmd" / member
            path.mkdir(parents=True)
            (path / "main.go").write_text("package main\n\nfunc main() {}\n")

    assert render("workspace/moon", dest, answers).returncode == 0
    commit(dest)
    return dest


@pytest.fixture
def rust_workspace(tmp_path: Path) -> Path:
    return workspace(tmp_path, "rust", RUST)


# --- the graph is derived, not asked ---------------------------------------


def test_a_moon_yml_is_generated_per_member(rust_workspace: Path) -> None:
    """Members come from the manifest's own glob, so the layer asks for no member list."""
    assert (rust_workspace / "crates" / "core" / "moon.yml").is_file()
    assert (rust_workspace / "crates" / "api" / "moon.yml").is_file()


@pytest.mark.parametrize(
    ("answers", "member", "dependency"),
    [
        (RUST, "crates/api", "core"),
        (TS, "packages/app", "ui"),
        (PY, "packages/svc", "lib"),
    ],
    ids=["rust-path-dependency", "ts-workspace-protocol", "python-requirement-string"],
)
def test_the_dependency_edge_is_derived_from_the_member_manifest(
    tmp_path: Path, answers: str, member: str, dependency: str
) -> None:
    """Each toolchain declares a sibling differently, and all three are read.

    rust uses `{ path = "../core" }`, ts `"ui": "workspace:*"`, python the requirement
    string `lib>=0.1.0`. The edge is what makes moon invalidate a dependent when its
    dependency changes, so a missed one silently serves a stale build.
    """
    dest = workspace(tmp_path, "w", answers)
    config = yaml.safe_load((dest / member / "moon.yml").read_text())
    assert config["dependsOn"] == [dependency]
    assert f"{dependency}:build" in config["tasks"]["build"]["deps"]


def test_go_derives_no_edges(tmp_path: Path) -> None:
    """A go member is a package in one module, so there is no manifest to read."""
    dest = workspace(tmp_path, "go", GO)
    config = yaml.safe_load((dest / "cmd" / "serve" / "moon.yml").read_text())
    assert "dependsOn" not in config


def test_a_depended_on_member_is_a_library(rust_workspace: Path) -> None:
    """`layer:`, not `type:`. moon 2.x renamed the key and rejects the old spelling.

    An application is what nothing else depends on, which is how moon decides what may
    be a root of the graph.
    """
    core = yaml.safe_load((rust_workspace / "crates" / "core" / "moon.yml").read_text())
    api = yaml.safe_load((rust_workspace / "crates" / "api" / "moon.yml").read_text())
    assert core["layer"] == "library"
    assert api["layer"] == "application"
    assert "type" not in core


# --- the keys moon actually accepts ---------------------------------------


def test_the_workspace_config_uses_the_keys_the_cli_accepts(rust_workspace: Path) -> None:
    """Three renamed keys, each of which rendered fine and failed only when moon read it.

    `pipeline` was `runner`, and `vcs.client` was `vcs.manager` -- the published
    workspace.json still documents `manager`, so the CLI is what this follows.
    """
    config = yaml.safe_load((rust_workspace / ".moon" / "workspace.yml").read_text())
    assert "runner" not in config, "moon 2.x calls this section `pipeline`"
    assert "cacheLifetime" in config["pipeline"]
    assert config["vcs"]["client"] == "git", "moon 2.4.6 rejects vcs.manager"
    assert "manager" not in config["vcs"]


def test_moon_does_not_sync_dependencies_back_into_manifests(rust_workspace: Path) -> None:
    """cargo, uv, and bun already resolve members through the root glob, so letting moon
    write edges back would give two tools one job."""
    config = yaml.safe_load((rust_workspace / ".moon" / "workspace.yml").read_text())
    assert config["pipeline"]["syncProjectDependencies"] is False


def test_the_toolchain_declares_no_versions(rust_workspace: Path) -> None:
    """mise owns every toolchain through .mise/conf.d/. Declaring a version here too
    would have moon download a second copy of the compiler."""
    config = yaml.safe_load((rust_workspace / ".moon" / "toolchain.yml").read_text())
    assert "version" not in (config.get("rust") or {})


# --- inputs and outputs, the two that decide whether caching works ---------


def test_rust_outputs_are_workspace_relative(rust_workspace: Path) -> None:
    """cargo writes to the WORKSPACE root target/, never crates/<name>/target/.

    A bare `target` is member-relative, so moon found nothing to cache and reported
    "defines outputs but after being ran, either none or not". The `/` prefix is moon's
    workspace-relative token.
    """
    config = yaml.safe_load((rust_workspace / "crates" / "core" / "moon.yml").read_text())
    outputs = config["tasks"]["build"]["outputs"]
    assert outputs == ["/target/debug"]


def test_go_inputs_match_go_sources(tmp_path: Path) -> None:
    """Go keeps sources beside the package rather than under src/.

    A `src/**/*` pattern matches nothing in a go member, so no edit would ever
    invalidate the build and moon would serve a stale cache entry forever.
    """
    dest = workspace(tmp_path, "go", GO)
    config = yaml.safe_load((dest / "cmd" / "serve" / "moon.yml").read_text())
    inputs = config["tasks"]["build"]["inputs"]
    assert "**/*.go" in inputs
    assert "src/**/*" not in inputs


def test_no_task_declares_an_output_nothing_creates(tmp_path: Path) -> None:
    """An outputs entry naming a path the command never writes makes moon warn and cache
    nothing, which is worse than declaring none. python syncs into a shared .venv and go
    discards its binary, so both declare no outputs."""
    for answers, member in ((PY, "packages/lib"), (GO, "cmd/serve")):
        dest = workspace(tmp_path, f"out-{member.replace('/', '-')}", answers)
        config = yaml.safe_load((dest / member / "moon.yml").read_text())
        assert "outputs" not in config["tasks"]["build"]


def test_every_generated_config_is_valid_yaml(tmp_path: Path) -> None:
    """A nested single quote inside a single-quoted scalar broke the python command
    before it was caught: `python -c 'pass'` ended the YAML string early."""
    for answers, members in (
        (RUST, ["crates/core", "crates/api"]),
        (TS, ["packages/ui", "packages/app"]),
        (PY, ["packages/lib", "packages/svc"]),
        (GO, ["cmd/serve", "cmd/tool"]),
    ):
        dest = workspace(tmp_path, f"yaml-{members[0].replace('/', '-')}", answers)
        for name in [".moon/workspace.yml", ".moon/toolchain.yml"] + [
            f"{m}/moon.yml" for m in members
        ]:
            yaml.safe_load((dest / name).read_text())


def test_the_package_name_comes_from_the_manifest(rust_workspace: Path) -> None:
    """cargo's -p takes the crate name, while moon's project id is the directory. The
    two differ whenever a crate is named differently from its folder, so the name is
    written in literally rather than through $MOON_PROJECT_ID."""
    config = yaml.safe_load((rust_workspace / "crates" / "core" / "moon.yml").read_text())
    assert config["tasks"]["build"]["command"] == "cargo build -p core"
    assert "MOON_PROJECT_NAME" not in (rust_workspace / "crates" / "core" / "moon.yml").read_text()


# --- regeneration ----------------------------------------------------------


def test_text_outside_the_markers_survives_regeneration(rust_workspace: Path) -> None:
    target = rust_workspace / "crates" / "core" / "moon.yml"
    target.write_text(target.read_text() + "\ntags:\n  - hand-added\n")
    subprocess.run(
        [sys.executable, "scripts/gen_moon.py", "."],
        cwd=rust_workspace,
        check=True,
        capture_output=True,
    )
    assert "hand-added" in target.read_text()


def test_the_check_flag_reports_a_stale_file(rust_workspace: Path) -> None:
    current = subprocess.run(
        [sys.executable, "scripts/gen_moon.py", ".", "--check"],
        cwd=rust_workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    assert current.returncode == 0, current.stderr

    # A member added without regenerating is the case this catches.
    new = rust_workspace / "crates" / "extra"
    (new / "src").mkdir(parents=True)
    (new / "src" / "lib.rs").write_text("pub fn g() {}\n")
    (new / "Cargo.toml").write_text(
        '[package]\nname = "extra"\nversion = "0.1.0"\nedition.workspace = true\n'
    )
    stale = subprocess.run(
        [sys.executable, "scripts/gen_moon.py", ".", "--check"],
        cwd=rust_workspace,
        capture_output=True,
        text=True,
        check=False,
    )
    assert stale.returncode == 1
    assert "just moon-sync" in stale.stderr


def test_generation_is_idempotent(rust_workspace: Path) -> None:
    before = (rust_workspace / "crates" / "api" / "moon.yml").read_text()
    for _ in range(2):
        subprocess.run(
            [sys.executable, "scripts/gen_moon.py", "."],
            cwd=rust_workspace,
            check=True,
            capture_output=True,
        )
    assert (rust_workspace / "crates" / "api" / "moon.yml").read_text() == before


# --- the real CLI ----------------------------------------------------------


@needs_moon
@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        (RUST, {"core": "library", "api": "application"}),
        (TS, {"ui": "library", "app": "application"}),
        (PY, {"lib": "library", "svc": "application"}),
    ],
    ids=["rust", "ts", "python"],
)
def test_moon_resolves_the_generated_graph(
    tmp_path: Path, answers: str, expected: dict[str, str]
) -> None:
    """Runs the real CLI. This is the test that caught every renamed key."""
    dest = workspace(tmp_path, "w", answers)
    result = moon(dest, "query", "projects")
    assert result.returncode == 0, result.stdout + result.stderr

    projects = json.loads(result.stdout)["projects"]
    layers = {p["id"]: p["layer"] for p in projects}
    assert layers == expected

    edges = {p["id"]: [d["id"] for d in p.get("dependencies", [])] for p in projects}
    dependent = next(name for name, layer in expected.items() if layer == "application")
    dependency = next(name for name, layer in expected.items() if layer == "library")
    assert edges[dependent] == [dependency]


@needs_moon
@pytest.mark.slow
def test_moon_orders_the_chain_and_caches_the_second_run(tmp_path: Path) -> None:
    """The capability the layer exists for, against a real cargo build.

    Asking for the dependent's task builds its dependency first, in order, from one
    command. The second run restores both from cache. Measured on this fixture: 2.5s
    cold against 0.75s warm with both cached.
    """
    if shutil.which("cargo") is None:
        pytest.skip("cargo absent")
    dest = workspace(tmp_path, "rust", RUST)

    cold = moon(dest, "run", "api:build")
    assert cold.returncode == 0, cold.stdout + cold.stderr
    # core precedes api in the output, because api's task declares the dependency.
    assert cold.stdout.index("core:build") < cold.stdout.index("api:build")
    # The rust output path was wrong once; this is the message it produced.
    assert "defines outputs but after being ran" not in cold.stdout + cold.stderr

    warm = moon(dest, "run", "api:build")
    assert warm.returncode == 0, warm.stdout + warm.stderr
    assert "cached" in warm.stdout


@needs_moon
@pytest.mark.slow
def test_changing_a_dependency_invalidates_its_dependents(tmp_path: Path) -> None:
    """Transitive invalidation is what `just` structurally cannot express: a hand-written
    loop reruns everything or nothing, with no graph to consult."""
    if shutil.which("cargo") is None:
        pytest.skip("cargo absent")
    dest = workspace(tmp_path, "rust", RUST)
    assert moon(dest, "run", "api:build").returncode == 0
    assert "cached" in moon(dest, "run", "api:build").stdout

    (dest / "crates" / "core" / "src" / "lib.rs").write_text("pub fn f() -> u8 { 99 }\n")
    after = moon(dest, "run", "api:build")
    assert after.returncode == 0, after.stdout + after.stderr
    assert "2 cached" not in after.stdout, "api must rebuild when core changes"


@needs_moon
@pytest.mark.slow
def test_changing_only_the_dependent_reuses_the_dependency_cache(tmp_path: Path) -> None:
    if shutil.which("cargo") is None:
        pytest.skip("cargo absent")
    dest = workspace(tmp_path, "rust", RUST)
    assert moon(dest, "run", "api:build").returncode == 0

    (dest / "crates" / "api" / "src" / "lib.rs").write_text("pub fn f() -> u8 { 2 }\n")
    after = moon(dest, "run", "api:build")
    assert after.returncode == 0, after.stdout + after.stderr
    assert "1 cached" in after.stdout, "core should still be cached"


# --- fragments -------------------------------------------------------------


def test_the_cache_directory_is_ignored(rust_workspace: Path) -> None:
    fragment = (rust_workspace / ".gitignore.d" / "moon").read_text()
    patterns = [
        line.strip() for line in fragment.splitlines() if line.strip() and not line.startswith("#")
    ]
    assert ".moon/cache/" in patterns
    # The graph itself is committed; only the cache is not.
    assert not any("workspace.yml" in p for p in patterns)


def test_the_recipes_render_and_pin_the_cli(rust_workspace: Path) -> None:
    fragment = (rust_workspace / ".just.d" / "moon.just").read_text()
    assert "moon-sync" in fragment
    assert "--affected --upstream" in fragment, "affected-only is the CI entry point"
    # just shares jinja's {{ }}, so an unwrapped body would lose these parameters.
    assert "moon run {{ member }}:{{ task }}" in fragment

    pin = (rust_workspace / ".mise" / "conf.d" / "moon.toml").read_text()
    assert '"npm:@moonrepo/cli"' in pin
