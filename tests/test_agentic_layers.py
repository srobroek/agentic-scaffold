"""agentic/*: apm.yml, beads bootstrap, and what they contribute to the aggregators."""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml
from conftest import render_recipe as render

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPES = REPO_ROOT / "recipes"

APM_ANSWERS = """\
project_name: demo
description: A demo project
apm_packages: []
apm_target: "claude,codex"
apm_cli_version: "0.25.0"
"""

BEADS_ANSWERS = """\
bd_prefix: demo
# embedded, so a test render leaves no dolt server process behind.
bd_storage_mode: embedded
bd_dolt_sync: local-only
bd_sync_remote: ""
bd_auto_export: false
bd_dolt_auto_commit: "on"
bd_push_command: ""
bd_sync_hook: pre-push
"""


def git_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    for key, value in (("user.email", "t@e.com"), ("user.name", "T")):
        subprocess.run(["git", "-C", str(path), "config", key, value], check=True)
    return path


needs_bd = pytest.mark.skipif(shutil.which("bd") is None, reason="bd absent from PATH")


# --- agentic/apm -----------------------------------------------------------


@pytest.fixture
def apm(tmp_path: Path) -> Path:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("agentic/apm", dest, APM_ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def test_apm_yml_parses_and_carries_the_threaded_values(apm: Path) -> None:
    spec = yaml.safe_load((apm / "apm.yml").read_text())
    assert spec["name"] == "demo"
    assert spec["target"] == "claude,codex"
    # `includes: auto` is what makes `apm compile` weave package context into
    # AGENTS.md, which is why docs/agents carries pointers rather than prose.
    assert spec["includes"] == "auto"


def test_an_empty_package_list_is_valid(apm: Path) -> None:
    """A repository can seed the layer and choose packages later.

    bailiff's version carried a validator refusing the empty list, which made the
    layer unusable until someone had picked packages. `agentic/marketplace`
    recommends against the rendered layer set afterwards.
    """
    spec = yaml.safe_load((apm / "apm.yml").read_text())
    assert spec["dependencies"]["apm"] == []


def test_the_packages_are_written_when_supplied(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    locators = [
        "srobroek/agentic-packages/packages/speckit#>=5.0.0 <6.0.0",
        "srobroek/slopvac/packages/write-docs#>=1.0.0 <2.0.0",
    ]
    render(
        "agentic/apm",
        dest,
        APM_ANSWERS.replace(
            "apm_packages: []", "apm_packages:\n" + "".join(f'  - "{p}"\n' for p in locators)
        ),
    )
    assert yaml.safe_load((dest / "apm.yml").read_text())["dependencies"]["apm"] == locators


def test_the_cli_version_is_pinned_in_the_recipes(apm: Path) -> None:
    """An unpinned CLI would change what a re-render installs."""
    body = (apm / ".just.d" / "apm.just").read_text()
    assert "apm-cli==0.25.0" in body
    # just's own interpolation has to survive jinja rendering.
    assert "{{ apm }}" in body


def test_apm_ignores_its_install_tree(apm: Path) -> None:
    assert "apm_modules/" in (apm / ".gitignore.d" / "apm").read_text()


def test_an_existing_apm_yml_is_not_overwritten(apm: Path) -> None:
    """A package list is hand-edited after rendering."""
    manifest = apm / "apm.yml"
    manifest.write_text("name: mine\nversion: 9.9.9\n")

    render("agentic/apm", apm, APM_ANSWERS)

    assert "mine" in manifest.read_text()


# --- agentic/beads ---------------------------------------------------------


@pytest.fixture
def beads(tmp_path: Path) -> Path:
    dest = git_repo(tmp_path / "d")
    result = render("agentic/beads", dest, BEADS_ANSWERS)
    assert result.returncode == 0, result.stdout + result.stderr
    return dest


@needs_bd
def test_beads_initialises_without_touching_the_hooks_path(beads: Path) -> None:
    """`bd init` without --skip-hooks repoints core.hooksPath at .beads/hooks.

    That copy also picks up whatever hook binaries are ambient, which is how a 347MB
    git-defender copy with an unusable arm64 slice ended up blocking every commit.
    quality/hooks reproduces bd's five hooks as prek entries instead.
    """
    assert (beads / ".beads").is_dir()

    result = subprocess.run(
        ["git", "-C", str(beads), "config", "--local", "--get", "core.hooksPath"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0, f"core.hooksPath was set to {result.stdout.strip()!r}"
    assert not (beads / ".beads" / "hooks").exists()


@needs_bd
def test_the_agent_lifecycle_hooks_are_kept(beads: Path) -> None:
    """These reload beads context after compaction.

    `--skip-agents` would remove them, which is what makes an AGENTS.md carrying no
    beads prose safe. bailiff's version passed that flag unconditionally.
    """
    codex = yaml.safe_load((beads / ".codex" / "hooks.json").read_text())["hooks"]
    for event in ("SessionStart", "UserPromptSubmit", "PreCompact", "PostCompact"):
        assert event in codex, f"codex {event} hook is missing"

    claude = yaml.safe_load((beads / ".claude" / "settings.json").read_text())["hooks"]
    assert "SessionStart" in claude


@needs_bd
def test_bds_ignore_lines_move_into_a_fragment(beads: Path) -> None:
    """base/gitignore rebuilds the root file, so lines left there would be dropped.

    bd appends its block with a header and no end marker, so nothing else could tell
    which lines were its.
    """
    fragment = (beads / ".gitignore.d" / "beads").read_text()
    for pattern in (".dolt/", ".beads-credential-key", ".beads/proxieddb/"):
        assert pattern in fragment

    # And the root file no longer carries bd's block, which would double them up.
    root = beads / ".gitignore"
    if root.is_file():
        assert "added by bd init" not in root.read_text()


@needs_bd
def test_the_ignore_lines_survive_a_gitignore_rebuild(beads: Path) -> None:
    """The end-to-end case the render order exists for."""
    result = render("base/gitignore", beads, 'gitignore_templates: ""\n')
    assert result.returncode == 0, result.stderr

    body = (beads / ".gitignore").read_text()
    for pattern in (".dolt/", ".beads-credential-key"):
        assert pattern in body, f"{pattern} was lost when .gitignore was rebuilt"


@needs_bd
def test_beads_is_idempotent(beads: Path) -> None:
    """`--init-if-missing` exits 0 on a second run rather than aborting."""
    result = render("agentic/beads", beads, BEADS_ANSWERS)
    assert result.returncode == 0, result.stdout + result.stderr


def bd_command() -> list[str]:
    """The exact argv bd_init.py builds, read from the module rather than guessed."""
    import importlib.util

    path = RECIPES / "agentic" / "beads" / "tasks" / "bd_init.py"
    spec = importlib.util.spec_from_file_location("bd_init_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    captured: list[list[str]] = []
    module.run = lambda command, dest, required=True: captured.append(command) or 0
    module.move_gitignore_lines = lambda dest: None
    module.main(["/nonexistent", "--prefix", "x"])
    return captured[0]


def test_the_layer_never_skips_the_agent_hooks() -> None:
    """`--skip-agents` would remove the hooks that reload beads context.

    Checked against the argv the task actually builds: a comment naming the flag as
    rejected must not make this test pass or fail.
    """
    assert "--skip-agents" not in bd_command()

    # And no answer can introduce it, since the flag is not a variable.
    body = yaml.safe_load((RECIPES / "agentic" / "beads" / "copier.yml").read_text())
    assert "--skip-agents" not in " ".join(body["_tasks"])


def test_server_mode_is_the_default_and_reaches_bd() -> None:
    """rule://beads-setup makes server mode the init default: an embedded database
    resolves by walking up from the working directory, so a copied checkout gets a
    second writable database whose claims never reach the run."""
    assert "--server" in bd_command()

    config = yaml.safe_load((RECIPES / "agentic" / "beads" / "copier.yml").read_text())
    assert config["bd_storage_mode"]["default"] == "server"
    assert "--storage-mode" in " ".join(config["_tasks"])


@needs_bd
def test_beads_is_tracked_rather_than_stealthed(beads: Path) -> None:
    """`--stealth` writes `.beads/` into `.git/info/exclude`, so the database is local.

    A scaffolded repository shares its issues, and `bd init` auto-detects a fork and
    offers exclusion on its own, so this asserts the end state rather than the flag.
    agentic-packages is stealthed that way: its `.beads/` is excluded and untracked.
    """
    exclude = beads / ".git" / "info" / "exclude"
    if exclude.is_file():
        assert "beads" not in exclude.read_text(), ".beads was excluded from git"

    tracked = subprocess.run(
        ["git", "-C", str(beads), "ls-files", ".beads/"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert ".beads/config.yaml" in tracked, "the beads config is untracked"


def test_the_layer_never_passes_stealth() -> None:
    """Checked against the argv the task builds, not a comment naming the flag."""
    assert "--stealth" not in bd_command()

    body = yaml.safe_load((RECIPES / "agentic" / "beads" / "copier.yml").read_text())
    assert "--stealth" not in " ".join(body["_tasks"])


def test_the_layer_always_skips_the_git_hooks() -> None:
    """quality/hooks owns those five events as prek entries."""
    assert "--skip-hooks" in bd_command()


def test_a_non_git_destination_is_initialised(tmp_path: Path) -> None:
    """`scaffold render` git-inits a bare destination before the recipe runs.

    `bd init` reads the repo's git config and aborts outside a work tree, which
    is why the old wrapper refused a non-git destination. The CLI owns the
    destination now, so the render succeeds and the tree is a repository.
    """
    dest = tmp_path / "notgit"
    dest.mkdir()

    result = render("agentic/beads", dest, BEADS_ANSWERS)

    assert result.returncode == 0, result.stderr
    assert (dest / ".git").is_dir()


# --- beads configuration ---------------------------------------------------


@needs_bd
def test_the_sync_remote_is_derived_from_the_git_origin(tmp_path: Path) -> None:
    """`sync.remote` is the one property every repository with beads sets.

    Surveyed across agentic-packages, claudebroker, platevault, skymath, and slopvac.
    The `git+` prefix is what marks it a Dolt remote over the git transport; without it
    bd reads the URL as a plain remote.
    """
    dest = git_repo(tmp_path / "d")
    subprocess.run(
        ["git", "-C", str(dest), "remote", "add", "origin", "git@github.com:srobroek/demo.git"],
        check=True,
    )

    # git-origin is the answer that derives it; local-only deliberately does not.
    answers = BEADS_ANSWERS.replace("bd_dolt_sync: local-only", "bd_dolt_sync: git-origin")
    assert render("agentic/beads", dest, answers).returncode == 0

    result = subprocess.run(
        ["bd", "config", "get", "sync.remote"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True,
    )
    # The scp-style address is normalised to a URL before the prefix is added.
    assert result.stdout.strip() == "git+ssh://git@github.com/srobroek/demo.git"


@needs_bd
def test_an_explicit_sync_remote_wins(tmp_path: Path) -> None:
    dest = git_repo(tmp_path / "d")
    explicit = "git+https://gitlab.com/group/thing.git"

    render(
        "agentic/beads",
        dest,
        BEADS_ANSWERS.replace('bd_sync_remote: ""', f'bd_sync_remote: "{explicit}"'),
    )

    result = subprocess.run(
        ["bd", "config", "get", "sync.remote"],
        cwd=dest,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == explicit


@needs_bd
@pytest.mark.parametrize(
    ("answer", "key", "expected"),
    [
        ("bd_auto_export: true", "export.auto", "true"),
        ("bd_dolt_auto_commit: batch", "dolt.auto-commit", "batch"),
        ("bd_push_command: dbd", "custom.bd-push-command", "dbd"),
    ],
)
def test_each_surveyed_property_reaches_bd(
    answer: str, key: str, expected: str, tmp_path: Path
) -> None:
    """Each of these is set in a real repository, so each is an answer here.

    export.auto in slopvac, dolt.auto-commit in platevault, and the push command where
    the database runs in a container.
    """
    dest = git_repo(tmp_path / "d")
    field = answer.split(":")[0]
    answers = "\n".join(
        answer if line.startswith(field) else line for line in BEADS_ANSWERS.splitlines()
    )

    assert render("agentic/beads", dest, answers + "\n").returncode == 0

    result = subprocess.run(
        ["bd", "config", "get", key], cwd=dest, capture_output=True, text=True, check=True
    )
    assert result.stdout.strip() == expected


def test_the_database_push_hook_never_blocks_a_git_push() -> None:
    """A push failing on an unreachable remote must not stop the git push.

    `bd dolt push` is recoverable by running it again, and blocking would make an
    offline commit-and-push impossible.
    """
    script = (
        RECIPES / "agentic" / "beads" / "template" / "scripts" / "bd-dolt-push.sh"
    ).read_text()

    # Every exit is 0, and the failure branch reports rather than propagating.
    assert "exit 0" in script
    assert "exit 1" not in script
    assert script.rstrip().endswith("exit 0")


def test_the_database_push_reads_the_configured_push_command() -> None:
    """A direct `bd dolt push` hangs where the database runs in a container.

    The wrapper is named by `custom.bd-push-command`, so the hook reads it rather than
    assuming `bd`.
    """
    script = (
        RECIPES / "agentic" / "beads" / "template" / "scripts" / "bd-dolt-push.sh"
    ).read_text()

    assert "custom.bd-push-command" in script
    # `bd config get` prints "<key> (not set)" rather than failing, so both are handled.
    assert "not set" in script
    # And a configured wrapper that is absent is skipped rather than run.
    assert "command -v" in script


def test_the_database_push_runs_at_pre_push(tmp_path: Path) -> None:
    """A commit is local, so pushing per commit is work nobody waits on.

    A git push is the moment the database has to follow.
    """
    dest = git_repo(tmp_path / "d")
    render(
        "quality/hooks", dest, "hook_exclude_patterns: []\nmax_file_kb: 500\ncommit_scopes: []\n"
    )

    config = yaml.safe_load((dest / ".pre-commit-config.yaml").read_text())
    hook = next(h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "bd-dolt-push")
    assert hook["stages"] == ["pre-push"]
    assert "pre-push" in config["default_install_hook_types"]


# --- ADR rendering ---------------------------------------------------------


def test_the_adr_fragment_renders_and_writes(tmp_path: Path) -> None:
    """The only writing hook in the merged config, so it must stage what it writes.

    prek fails a commit when a hook modifies a tracked file and leaves it unstaged,
    and silently omits a newly written untracked one, so a renderer that does not
    stage produces either a failed commit or a missing file.
    """
    dest = git_repo(tmp_path / "d")
    render(
        "quality/hooks", dest, "hook_exclude_patterns: []\nmax_file_kb: 500\ncommit_scopes: []\n"
    )

    config = yaml.safe_load((dest / ".pre-commit-config.yaml").read_text())
    hook = next(h for repo in config["repos"] for h in repo["hooks"] if h["id"] == "render-adrs")
    assert hook["stages"] == ["pre-commit"]
    # A database is not a path: no staged file set reveals that a bead changed.
    assert hook["always_run"] is True
    assert "files" not in hook


def test_the_adr_hooks_no_op_without_their_tooling(tmp_path: Path) -> None:
    """Beads is optional tooling, so a clone without bd must still commit.

    The renderer is guarded on its own presence because quality/hooks renders
    whether or not agentic/beads did, and the linter on `bd` being installed.
    """
    dest = git_repo(tmp_path / "d")
    render(
        "quality/hooks", dest, "hook_exclude_patterns: []\nmax_file_kb: 500\ncommit_scopes: []\n"
    )

    config = yaml.safe_load((dest / ".pre-commit-config.yaml").read_text())
    hooks = {h["id"]: h for repo in config["repos"] for h in repo["hooks"]}
    assert "test -x scripts/render_adrs.py" in hooks["render-adrs"]["entry"]
    assert "command -v bd" in hooks["adr-lint-decisions"]["entry"]


def test_beads_ships_the_adr_renderer(tmp_path: Path) -> None:
    """agentic/beads owns beads-adjacent scripts, the split bd-dolt-push.sh uses.

    A prek `entry:` cannot point into apm_modules/, so the script is vendored into
    the rendered project rather than referenced from an installed package.
    """
    dest = git_repo(tmp_path / "d")
    render("agentic/beads", dest, "bd_prefix: xy\nbd_storage_mode: embedded\n")

    script = dest / "scripts" / "render_adrs.py"
    assert script.is_file()
    assert script.stat().st_mode & 0o111, "a bare-path entry needs the execute bit"
    body = script.read_text()
    assert "VENDORED from srobroek/agentic-packages" in body, "provenance must survive"
    assert "bd export" in body


DECISION = """\
## Decision

Use OpenTofu.

## Rationale

The licence change makes the alternative unusable here.

## Alternatives Considered

Terraform: rejected, BUSL.
"""


def decisions_rendered(tmp_path: Path) -> Path:
    """A repo with agentic/beads and docs/adr, one closed decision, and ADRs rendered."""
    dest = git_repo(tmp_path / "adr")
    render(
        "agentic/beads",
        dest,
        "bd_prefix: adrt\nbd_storage_mode: embedded\nbd_dolt_sync: local-only\n",
    )
    render("docs/adr", dest, "project_name: demo\n")

    subprocess.run(
        ["bd", "create", "Use OpenTofu", "--type", "decision", "-d", DECISION],
        cwd=dest,
        check=True,
        capture_output=True,
    )
    listed = subprocess.run(
        ["bd", "list", "--type", "decision", "--json"],
        cwd=dest,
        check=True,
        capture_output=True,
        text=True,
    )
    bead = json.loads(listed.stdout)[0]["id"]
    subprocess.run(
        ["bd", "close", bead, "--reason", "settled"], cwd=dest, check=True, capture_output=True
    )
    subprocess.run(
        [sys.executable, "scripts/render_adrs.py"], cwd=dest, check=True, capture_output=True
    )
    return dest


@needs_bd
def test_a_rendered_record_opens_with_its_frontmatter(tmp_path: Path) -> None:
    """`---` on line 1, or a frontmatter parser reads the block as body text.

    An earlier version put the provenance comment above it, which left `status`, `date`,
    and `bead` invisible to anything indexing these records.
    """
    dest = decisions_rendered(tmp_path)
    record = next((dest / "docs" / "adr").glob("0001-*.md"))
    body = record.read_text()

    assert body.startswith("---"), "frontmatter must be the first thing in the file"
    parsed = yaml.safe_load(body.split("---")[1])
    assert parsed["status"] == "accepted"
    assert parsed["bead"]
    # The provenance note still ships, below the block.
    assert "Edit the bead, not this file" in body


@needs_bd
def test_the_index_lists_every_rendered_record(tmp_path: Path) -> None:
    """docs/adr ships an index, and a table left at its placeholder row reports that a
    project has no decisions while numbered files accumulate beside it."""
    dest = decisions_rendered(tmp_path)
    index = (dest / "docs" / "adr" / "index.md").read_text()
    rows = index.partition("<!-- BEGIN GENERATED: decisions -->")[2].partition(
        "<!-- END GENERATED: decisions -->"
    )[0]

    assert "0001-use-opentofu.md" in rows, "the row links the record it describes"
    assert "| accepted |" in rows
    assert "| | |" not in rows, "the placeholder row must be gone"


@needs_bd
def test_the_index_keeps_what_is_outside_the_markers(tmp_path: Path) -> None:
    """The prose above the table explains the convention and is the project's to edit."""
    dest = decisions_rendered(tmp_path)
    index_path = dest / "docs" / "adr" / "index.md"
    index_path.write_text(index_path.read_text() + "\n## Local note\n\nSurvives.\n")

    subprocess.run(
        [sys.executable, "scripts/render_adrs.py"], cwd=dest, check=True, capture_output=True
    )
    body = index_path.read_text()
    assert "Survives." in body
    assert "# Decision records" in body


@needs_bd
def test_an_index_without_markers_is_left_alone(tmp_path: Path) -> None:
    """docs/adr may not have rendered, or a project may have replaced the index.

    Injecting a table into a file that never asked for one is worse than leaving it
    alone, so the renderer reports nothing rather than editing it.
    """
    dest = decisions_rendered(tmp_path)
    index_path = dest / "docs" / "adr" / "index.md"
    index_path.write_text("# My own index\n\nNo markers here.\n")

    result = subprocess.run(
        [sys.executable, "scripts/render_adrs.py"], cwd=dest, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    assert index_path.read_text() == "# My own index\n\nNo markers here.\n"


@needs_bd
def test_check_reports_a_stale_index_without_repairing_it(tmp_path: Path) -> None:
    """A gate that fixes what it checks destroys a hand edit and passes on the rerun."""
    dest = decisions_rendered(tmp_path)
    index_path = dest / "docs" / "adr" / "index.md"
    index_path.write_text(index_path.read_text().replace("Use OpenTofu", "TAMPERED"))

    result = subprocess.run(
        [sys.executable, "scripts/render_adrs.py", "--check"],
        cwd=dest,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, "a stale index must fail the check"
    assert "TAMPERED" in index_path.read_text(), "--check must not rewrite the tree"


@needs_bd
def test_rendering_is_idempotent(tmp_path: Path) -> None:
    """A second run must restage nothing, or every unrelated commit carries every ADR."""
    dest = decisions_rendered(tmp_path)
    before = {path.name: path.read_text() for path in (dest / "docs" / "adr").glob("*.md")}

    result = subprocess.run(
        [sys.executable, "scripts/render_adrs.py"], cwd=dest, capture_output=True, text=True
    )
    assert result.returncode == 0
    assert "wrote" not in result.stdout, "nothing changed, so nothing should be written"
    after = {path.name: path.read_text() for path in (dest / "docs" / "adr").glob("*.md")}
    assert after == before


# --- AGENTS.md ownership ---------------------------------------------------


@needs_bd
def test_docs_agents_owns_the_index_and_beads_appends_below(tmp_path: Path) -> None:
    """bd's own AGENTS.md is 127 lines of three overlapping beads blocks.

    Left to itself that file becomes what a repository's agents read first, so the
    task passes `--agents-template` pointing at the body docs/agents rendered.
    Verified against bd 1.1.2.
    """
    dest = git_repo(tmp_path / "d")
    assert render("docs/agents", dest, "project_name: demo\n").returncode == 0
    assert render("agentic/beads", dest, BEADS_ANSWERS).returncode == 0

    index = (dest / "AGENTS.md").read_text()
    assert index.startswith("# demo"), "bd's body won"
    assert "## Read for" in index
    # bd still gets its block, appended below the body it was given.
    assert "BEADS" in index


@needs_bd
def test_the_index_recovers_when_beads_rendered_first(tmp_path: Path) -> None:
    """Render order should not be the only thing keeping the body in place."""
    dest = git_repo(tmp_path / "d")
    assert render("agentic/beads", dest, BEADS_ANSWERS).returncode == 0
    assert render("docs/agents", dest, "project_name: demo\n").returncode == 0

    index = (dest / "AGENTS.md").read_text()
    assert index.startswith("# demo")
    # And bd's block is not lost in the recovery.
    assert "BEADS" in index


def test_claude_md_is_a_relative_symlink(tmp_path: Path) -> None:
    """One file serves both harnesses, and a relative target survives a clone."""
    dest = git_repo(tmp_path / "d")
    render("docs/agents", dest, "project_name: demo\n")

    link = dest / "CLAUDE.md"
    assert link.is_symlink(), "CLAUDE.md is not a symlink"
    assert link.readlink() == Path("AGENTS.md")


def test_the_index_is_a_copy_not_a_symlink(tmp_path: Path) -> None:
    """agentic/beads appends to AGENTS.md, and a symlink would write into the body."""
    dest = git_repo(tmp_path / "d")
    render("docs/agents", dest, "project_name: demo\n")

    assert not (dest / "AGENTS.md").is_symlink()
    assert (dest / "docs" / "agents" / "AGENTS.body.md").is_file()


def test_a_hand_edited_index_survives_a_second_render(tmp_path: Path) -> None:
    dest = git_repo(tmp_path / "d")
    render("docs/agents", dest, "project_name: demo\n")

    index = dest / "AGENTS.md"
    index.write_text(index.read_text() + "\n## Mine\n\nDo not lose this.\n")

    render("docs/agents", dest, "project_name: demo\n")

    assert "Do not lose this." in index.read_text()


# --- what both contribute to the aggregators -------------------------------


@pytest.mark.parametrize("layer", ["agentic/apm", "agentic/beads"])
def test_each_layer_ships_a_just_fragment(layer: str) -> None:
    name = layer.split("/")[1]
    matches = list((RECIPES / layer).glob(f"template/.just.d/{name}*.just*"))
    assert matches, f"{layer} ships no .just.d fragment"


def test_a_recipe_description_is_not_a_stray_rationale_line() -> None:
    """just takes the comment directly above a recipe as its `--list` description.

    A rationale block ending just above the recipe silently becomes the description,
    which then reads as a sentence fragment in `just --list`.
    """
    offenders = []
    for fragment in sorted(RECIPES.glob("*/*/template/.just.d/*.just*")):
        lines = fragment.read_text().splitlines()
        for index, line in enumerate(lines):
            if not re.match(r"^\[group\(", line):
                continue
            # Walk back over the attribute to the comment that documents the recipe.
            comment = lines[index - 1] if index else ""
            if not comment.lstrip().startswith("#"):
                continue
            text = comment.lstrip("# ").strip()
            # A description is a phrase, not the tail of a sentence.
            if text.endswith(".") or (text and text[0].islower()):
                offenders.append(f"{fragment.name}: {text!r}")
    assert not offenders, "rationale leaked into a recipe description: " + "; ".join(offenders)
