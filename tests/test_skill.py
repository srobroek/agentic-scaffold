"""The two skills, and how a harness reaches them.

A skill is prose, so these tests assert the contract rather than the wording: the interview
asks exactly the six questions `rules/choices.md` marks as asked, names no question that
document marks fixed or derived, and names only CLI subcommands that exist.

Kept deliberately shallow. Skill prose is rewritten often, and a test pinning a sentence
fails on an improvement rather than on a defect.

`.agents/skills/<name>` is generated wiring: read here, never edited here.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import scaffold

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILLS = REPO_ROOT / "skills"
SCAFFOLD_SKILL = SKILLS / "project-scaffold" / "SKILL.md"
UPDATE_SKILL = SKILLS / "project-scaffold-update" / "SKILL.md"
PROFILES = REPO_ROOT / "profiles"

NAMES = ("project-scaffold", "project-scaffold-update")


def skill_body() -> str:
    return SCAFFOLD_SKILL.read_text()


def frontmatter(path: Path) -> dict:
    return yaml.safe_load(path.read_text().split("---")[1])


# --- how a harness finds the skills ----------------------------------------


def test_the_plugin_manifest_points_at_the_one_skill_directory() -> None:
    """`skills/` is the single source. A second copy under a package directory is what the
    old layout had, and the two drifted."""
    manifest = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    assert manifest["skills"] == "./skills"
    for name in NAMES:
        assert (SKILLS / name / "SKILL.md").is_file()


def test_each_codex_entry_point_is_a_committed_relative_symlink() -> None:
    """Codex reads `.agents/skills/<name>/SKILL.md`, and Claude reads `skills/`. One of the
    two has to be a link, or the bodies drift.

    Git mode 120000 is the load-bearing part: committed as a regular file, a clone gets a
    one-line text file holding the target path, and the harness reads that as the skill.
    """
    listing = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-s", "--", ".agents/skills"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    modes = {line.split()[3]: line.split()[0] for line in listing.splitlines() if line}

    for name in NAMES:
        entry = f".agents/skills/{name}"
        assert modes.get(entry) == "120000", f"{entry} is not committed as a symlink"
        link = REPO_ROOT / entry
        assert link.resolve() == (SKILLS / name).resolve()


# --- the skills' own shape -------------------------------------------------


@pytest.mark.parametrize("path", [SCAFFOLD_SKILL, UPDATE_SKILL], ids=NAMES)
def test_the_frontmatter_carries_a_matching_trigger(path: Path) -> None:
    """The description is what an agent matches on to decide whether to load the skill, so
    it states when to use it rather than what it is."""
    meta = frontmatter(path)
    assert meta["name"] == path.parent.name
    assert "use when" in meta["description"].lower()


@pytest.mark.parametrize("path", [SCAFFOLD_SKILL, UPDATE_SKILL], ids=NAMES)
def test_it_stays_under_the_line_budget(path: Path) -> None:
    """A skill long enough to skim is a skill nobody reads. The ceiling rose from 120 when
    both absorbed the retired runner's semantics, and to 160 when the interview grew the
    grill-the-shape rounds."""
    assert len(path.read_text().splitlines()) <= 160


def test_the_scaffold_skill_names_the_verbs_a_person_types() -> None:
    description = frontmatter(SCAFFOLD_SKILL)["description"].lower()
    for trigger in ("set up", "scaffold", "initialize", "bootstrap"):
        assert trigger in description, f"{trigger!r} is not a trigger"


def test_the_update_skill_names_the_verbs_a_person_types() -> None:
    description = frontmatter(UPDATE_SKILL)["description"].lower()
    for trigger in ("adopt", "retrofit", "resync"):
        assert trigger in description, f"{trigger!r} is not a trigger"


# --- the interview ---------------------------------------------------------


def interview() -> str:
    return skill_body().partition("## Interview")[2].partition("## Propose the recipe set")[0]


def test_the_opening_round_stays_six_questions_and_the_shape_gets_grilled() -> None:
    """rules/choices.md fixes the opening count -- a seventh up-front question is one whose
    answer the document already derives. What nothing derives is grilled in rounds instead,
    and that section has to exist or the non-derivable decisions default silently."""
    numbered = [
        line
        for line in interview().splitlines()
        if line.strip()[:2] in {f"{n}." for n in range(1, 10)}
    ]
    assert len(numbered) == 6, f"expected six opening questions, found {len(numbered)}"
    assert "## grill the shape" in skill_body().lower()
    assert "generator_answers" in skill_body()


def test_it_asks_nothing_the_choices_table_derives() -> None:
    """A derived question wastes a turn and invites an answer contradicting the tree."""
    section = interview().lower()
    # Rows in the Derive table of rules/choices.md, which the agent settles itself.
    for derived in ("task runner", "coverage floor", "default branch", "version matrix"):
        assert derived not in section, f"the interview asks about {derived!r}, which is derived"


def test_it_reads_a_public_repository_back_before_creating_it() -> None:
    """`gh repo create --public` publishes immediately and is indexed, so the name, owner,
    and visibility are confirmed first."""
    body = skill_body()
    assert "--public" in body
    assert "read" in body.lower() and "back" in body.lower()


# --- what it points at -----------------------------------------------------


@pytest.mark.parametrize("path", [SCAFFOLD_SKILL, UPDATE_SKILL], ids=NAMES)
def test_it_names_only_subcommands_the_cli_has(path: Path) -> None:
    """A skill naming a subcommand the CLI dropped is an instruction that exits 2.

    Asked of the CLI rather than of a list here, because a list here is the copy that drifts.
    """
    named = {
        part
        for group in re.findall(r"scaffold\.py <?([a-z][a-z|-]*)>?", path.read_text())
        for part in group.split("|")
    }
    assert named, "the skill names no subcommand at all"
    for subcommand in sorted(named):
        result = scaffold(subcommand, "--help")
        assert result.returncode == 0, f"`scaffold {subcommand}` is not a subcommand"


def test_it_routes_to_the_recipe_list_rather_than_naming_every_profile() -> None:
    """Thirteen profiles named in prose is thirteen strings that go stale. `scaffold list`
    prints the set with its summaries, so the skill names only the two mappings a summary
    does not give away."""
    body = skill_body()
    assert "scaffold list" in body
    unnamed = sorted(path.stem for path in PROFILES.glob("*.yml") if path.stem not in body)
    assert unnamed, "the skill lists every profile again, which is the copy that drifts"


def test_it_carries_the_two_ordering_traps() -> None:
    """Both cost real time to find. The generator order silently produces a repository that
    is not a workspace, and a contributor after its aggregator leaves a generated file
    stale, which `just just-check` then fails on."""
    body = skill_body()
    assert "workspace/monorepo" in body
    assert "[workspace]" in body
    assert "aggregator" in body.lower()


def test_it_makes_the_marketplaces_the_users_to_name() -> None:
    """Registering a source reaches every project on the machine, so a suggested default is
    a supply-chain decision taken for the user. The native commands are named because the
    scaffold registers nothing itself."""
    body = skill_body()
    assert "Marketplaces are the user's to name" in body
    assert "machine-global" in body
    assert "omp plugin marketplace add" in body
    assert "/plugin marketplace add" in body
    assert ".agents/plugins/marketplace.json" in body


def test_the_skill_suggests_no_marketplace_of_its_own() -> None:
    """The rule is worth nothing if the prose next to it names a source: a reader copies the
    example. Every `<owner/repo>` here stays a placeholder."""
    body = skill_body()
    named = re.findall(r"marketplace add ([^\s`]+)", body)
    assert named, "the skill names no registration command at all"
    assert set(named) == {"<owner/repo>"}, f"the skill suggests a marketplace: {named}"


def test_it_points_at_the_documents_rather_than_restating_them() -> None:
    """A rule stated twice drifts, so the skill cites and the document holds the content.

    Checked by looking for the tables those documents own. A size ratio would prove
    nothing: rules/choices.md is shorter than the skill.
    """
    body = skill_body()
    assert "rules/choices.md" in body, "the skill must cite the choices table"

    # The Derive and Fixed tables belong to rules/choices.md. Copying a row here is the
    # duplication that drifts.
    for row in ("| Task runner |", "| Sub-runner |", "| Coverage floor |", "| Docs engine |"):
        assert row not in body, f"the skill copies {row!r} from rules/choices.md"

    # The recipe inventory belongs to docs/recipes.md and docs/INDEX.md.
    assert "| Layer | Writes |" not in body
    assert "| Recipe | Writes |" not in body


def test_the_recipe_set_section_names_shapes_rather_than_recipe_sets() -> None:
    """The profile file carries its own recipe list, so the skill routes to it instead of
    repeating it. A recipe set in two places is a recipe set that disagrees with itself."""
    section = skill_body().partition("## Propose the recipe set")[2].partition("## Answers")[0]
    assert "base/repo" not in section
    assert "quality/hooks" not in section
    assert "Read the profile" in section


# --- the update skill ------------------------------------------------------
#
# It changes a repository that already exists, so its whole job is what survives a render
# and what does not. Each claim below was measured on a real tree: rendering `lang/rust`
# into a tree holding `workspace/just` left the import block reading `# No fragments
# rendered yet.`, and an appended `.editorconfig` line was gone after re-rendering
# `base/repo`, while an appended README.md paragraph survived under `_skip_if_exists`.


def test_the_update_skill_separates_the_three_jobs() -> None:
    """Which job it is decides everything after, so the routing table is the first thing in
    the file. Retrofit is the one that has no `_ref` to replay."""
    body = UPDATE_SKILL.read_text()
    for job in ("**Adopt**", "**Apply changes**", "**Retrofit**"):
        assert job in body, f"the routing table has no {job} row"
    assert "predates this tool, no `.copier-answers.*.yml`" in body


def test_the_update_skill_names_the_ref_it_replays() -> None:
    """`update` renders at the recorded `_ref` and again at HEAD. A skill that does not say
    where the ref comes from cannot explain why a repository with no answers file is a
    retrofit rather than an update."""
    body = UPDATE_SKILL.read_text()
    assert "_ref" in body
    assert ".copier-answers." in body
    assert "git merge-file" in body


def test_the_update_skill_refuses_to_re_run_over_a_conflict() -> None:
    """A conflicted update is not applied: the recipe keeps its recorded `_ref`, so a re-run
    replays the same base and conflicts again rather than reporting success over markers
    nobody resolved. Resolving them and re-running is what advances the ref.
    """
    body = UPDATE_SKILL.read_text()
    assert "exit 5" in body
    assert "conflict markers" in body


def test_the_update_skill_pairs_every_fold_with_its_command() -> None:
    """A recipe adopted without re-folding leaves the generated file stale, and the
    destination has a check for each. The gitignore asymmetry is the one worth stating: its
    fold runs from a copier `_tasks` script inside the recipe, so no in-repo command runs it.
    """
    body = UPDATE_SKILL.read_text()
    for directory, command in (
        (".just.d/", "just just-sync"),
        (".pre-commit.d/", "just hooks-merge"),
        ("docs/agents/", "just steering"),
        (".gitignore.d/", "base/gitignore"),
    ):
        assert directory in body, f"no fold named for {directory}"
        assert command in body, f"{directory} is named without {command}"
    assert "copier task" in body or "_tasks" in body


def test_the_update_skill_sends_a_new_repository_to_the_other_skill() -> None:
    """Without this it is the closer match on `add`, and renders recipe by recipe into an
    empty directory rather than running the interview."""
    body = UPDATE_SKILL.read_text()
    assert "project-scaffold" in body
    assert "does not exist yet" in body


def test_the_update_skill_requires_a_commit_before_rendering() -> None:
    """The git diff is the whole review for an adopt or a retrofit, neither of which merges.
    Rendering onto a dirty tree destroys it."""
    body = UPDATE_SKILL.read_text().lower()
    assert "commit the destination" in body


def test_the_update_skill_requires_a_preview_before_writing() -> None:
    """`--pretend` was verified to leave the tree untouched, which is what makes it safe
    against a repository whose contents nobody has surveyed. `just preview` is the recipe
    that wraps it, and it is a recipe of this checkout rather than of the destination."""
    body = UPDATE_SKILL.read_text()
    assert "just preview" in body
    assert "--pretend" in body
    justfile = (REPO_ROOT / "justfile").read_text()
    assert "\npreview" in justfile, "the skill names `just preview`, which the justfile lacks"


def test_the_update_skill_warns_that_a_hand_edit_to_a_generated_file_is_lost() -> None:
    """`render` passes `--overwrite` with no prompt. This is the one irreversible thing, so
    the escape hatch is named with the path that has it."""
    body = UPDATE_SKILL.read_text()
    assert "_skip_if_exists" in body
    assert "README.md" in body
    assert "lost on re-render" in body


def test_the_update_skill_points_at_the_requires_map_rather_than_listing_it() -> None:
    """scripts/scaffold.py holds it and validates profiles against it. A copy here drifts."""
    body = UPDATE_SKILL.read_text()
    assert "REQUIRES" in body
    assert "scripts/scaffold.py" in body


# --- the repository releases itself ----------------------------------------


def test_the_repository_can_actually_release_itself() -> None:
    """The release-please config and manifest were once committed with no workflow to read
    them, and nothing noticed: the tests about publishing all checked shape, and none asked
    whether anything ran.
    """
    workflow_path = REPO_ROOT / ".github" / "workflows" / "release-please.yml"
    assert workflow_path.is_file(), (
        "release-please-config.json exists but no workflow reads it, so no release can happen"
    )
    workflow = yaml.safe_load(workflow_path.read_text())

    # The config filenames are inputs, so a rename here silently stops the release.
    # Found by index once, which broke when the App-token mint step moved ahead of it.
    step = next(
        s
        for s in workflow["jobs"]["release-please"]["steps"]
        if "release-please-action" in str(s.get("uses", ""))
    )
    assert step["with"]["config-file"] == "release-please-config.json"
    assert step["with"]["manifest-file"] == ".release-please-manifest.json"
    assert (REPO_ROOT / step["with"]["config-file"]).is_file()
    assert (REPO_ROOT / step["with"]["manifest-file"]).is_file()

    # Triggers on the default branch, not per pull request: the release PR is built from the
    # commits already merged.
    assert workflow[True]["push"]["branches"] == ["main"]

    permissions = workflow["jobs"]["release-please"]["permissions"]
    assert permissions["contents"] == "write"
    assert permissions["pull-requests"] == "write"


def test_the_release_train_is_one_root_component() -> None:
    """One component, so the tag is a plain `v{version}`. The old layout tagged
    `{name}--v{version}` because a marketplace resolved a version out of the tag, and that
    marketplace is gone: a component tag now names a component nothing publishes.
    """
    config = json.loads((REPO_ROOT / "release-please-config.json").read_text())
    assert list(config["packages"]) == ["."]
    assert "include-component-in-tag" not in config
    assert "tag-separator" not in config

    tracked = json.loads((REPO_ROOT / ".release-please-manifest.json").read_text())
    assert list(tracked) == ["."]

    # The version a harness reads has to be bumped with the tag, or an installed plugin
    # reports a version the repository left behind.
    extra = config["packages"]["."]["extra-files"]
    assert any(entry["path"] == ".claude-plugin/plugin.json" for entry in extra)


def test_the_three_catalogs_are_identical_and_track_the_release() -> None:
    """One catalog serves OMP, Claude Code, and Codex; three copies exist only
    because each runtime reads its own path. Divergence would install different
    things per harness, and a version that trails plugin.json makes the upgrade
    check lie -- release-please bumps all of them through extra-files."""
    import json

    catalogs = [
        REPO_ROOT / ".omp-plugin" / "marketplace.json",
        REPO_ROOT / ".claude-plugin" / "marketplace.json",
        REPO_ROOT / ".agents" / "plugins" / "marketplace.json",
    ]
    first, *rest = catalogs
    for other in rest:
        assert first.read_bytes() == other.read_bytes(), other

    plugin = json.loads((REPO_ROOT / ".claude-plugin" / "plugin.json").read_text())
    catalog = json.loads(first.read_text())
    assert catalog["plugins"][0]["version"] == plugin["version"]
    assert catalog["plugins"][0]["source"] == "."
