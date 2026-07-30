"""The project-scaffold-update skill, and the second package this repository publishes.

`project-scaffold` renders into an empty directory, where nothing can be lost. This one
changes a repository that already exists, so its whole job is what survives a render and what
does not. Each claim below was measured on a real tree rather than read out of a template.

The measurements, all against copier 9.17.0:

  * `copier update` refuses outright: `Cannot update because cannot obtain old template
    references from .copier-answers.gitignore.yml`. A layer renders from a local path, so no
    `_commit` is recorded and there is no upstream ref to diff against.
  * `render` passes `--overwrite`, so an `indent_size = 8` line appended to `.editorconfig`
    was gone after re-rendering `base/repo`, with no prompt. A `_skip_if_exists` path
    survives: an appended paragraph in README.md was kept.
  * `--pretend` listed `create docs/adr/index.md` and left `git status` unchanged.
  * Rendering `lang/rust` into a tree holding `workspace/just` left the import block reading
    `# No fragments rendered yet.`, and `just just-check` reported the drift.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
PACKAGE = REPO_ROOT / "packages" / "project-scaffold-update"
SKILL = PACKAGE / ".apm" / "skills" / "project-scaffold-update" / "SKILL.md"


def skill_body() -> str:
    return SKILL.read_text()


def frontmatter() -> dict:
    return yaml.safe_load(skill_body().split("---")[1])


# --- the skill's own shape -------------------------------------------------


def test_the_skill_exists_where_apm_deploys_from() -> None:
    assert SKILL.is_file()


def test_the_frontmatter_carries_a_matching_trigger() -> None:
    """The description is what an agent matches on, so it states when to use it. The verbs
    are the ones a person types about an existing repo, and they must not collide with
    project-scaffold's: `scaffold` and `bootstrap` belong to that one."""
    meta = frontmatter()
    assert meta["name"] == "project-scaffold-update"
    description = meta["description"].lower()
    assert "use when" in description
    for trigger in ("adopt", "retrofit", "resync", "catch up"):
        assert trigger in description, f"missing trigger: {trigger}"


def test_it_stays_under_the_line_budget() -> None:
    """Same 120-line target as project-scaffold. A skill long enough to skim is unread."""
    assert len(skill_body().splitlines()) <= 120


def test_it_separates_the_three_jobs() -> None:
    """Adopting a layer, re-rendering one, and retrofitting differ in what can be lost, and
    an agent that conflates them retrofits with an adopt-a-layer level of care."""
    body = skill_body()
    for heading in ("## Adopt a layer", "## Apply template changes", "## Retrofit"):
        assert heading in body


def test_it_sends_a_new_repository_to_the_other_skill() -> None:
    """Without this it is the closer match on `add`, and renders layer by layer into an empty
    directory rather than running the interview."""
    assert "project-scaffold" in skill_body()
    assert "does not exist yet" in skill_body()


# --- what was measured ----------------------------------------------------


def test_it_says_copier_update_does_not_work() -> None:
    """The obvious first move, and it fails with a message about template references that
    reads like a missing file rather than a design constraint. An agent that does not know
    this burns a turn on it."""
    body = skill_body()
    assert "copier update" in body
    assert "_commit" in body


def test_it_warns_that_a_hand_edit_to_a_generated_file_is_lost() -> None:
    """`--overwrite` with no prompt. This is the one irreversible thing the skill does, so
    the specific file and the specific loss are named rather than described in general."""
    body = skill_body()
    assert "--overwrite" in body
    assert ".editorconfig" in body
    assert "_skip_if_exists" in body


def test_it_requires_a_preview_before_writing() -> None:
    """`--pretend` was verified to leave the tree untouched, which is what makes it safe to
    run against a repository whose contents nobody has surveyed."""
    body = skill_body()
    assert "just preview" in body
    assert "--pretend" in body


def test_it_names_every_aggregator_and_its_resync() -> None:
    """A layer adopted without resyncing leaves the generated file stale, and the repo has a
    check for each. The gitignore asymmetry is the one worth stating: its folding runs from a
    copier _tasks script in the template, so there is no in-repo recipe to run."""
    body = skill_body()
    for pair in (
        (".just.d/", "just just-sync"),
        (".pre-commit.d/", "just hooks-merge"),
        ("docs/agents/", "just steering"),
        (".gitignore.d/", "base/gitignore"),
    ):
        for token in pair:
            assert token in body, f"missing {token}"
    assert "_tasks" in body


def test_it_requires_the_answers_file_when_re_rendering() -> None:
    """Without it copier re-derives defaults, so a re-render silently changes answers nobody
    revisited."""
    assert ".copier-answers." in skill_body()


def test_it_points_at_the_requires_map_rather_than_listing_it() -> None:
    """scripts/profiles.py holds it and validates against it. A copy here drifts."""
    body = skill_body()
    assert "REQUIRES" in body
    assert "scripts/profiles.py" in body


def test_it_requires_a_commit_before_rendering() -> None:
    """The git diff is the entire review mechanism here, since there is no three-way merge.
    Rendering onto a dirty tree destroys it."""
    body = skill_body().lower()
    assert "commit before rendering" in body


def test_the_recipes_it_names_exist() -> None:
    """A skill naming a recipe that was renamed sends an agent to a command that fails."""
    # A recipe name is the first word before the colon: `render layer dest *answers:` takes
    # parameters, so splitting on the colon alone yields the whole signature.
    recipes = {
        line.split(":")[0].split()[0]
        for line in (REPO_ROOT / "justfile").read_text().splitlines()
        if line and not line[0].isspace() and ":" in line and not line.startswith("#")
    }
    for named in ("render", "preview", "check"):
        assert named in recipes, f"the skill names `just {named}`, which the justfile lacks"


# --- the package -----------------------------------------------------------


def test_the_package_carries_its_own_manifest() -> None:
    """`apm pack --check-versions` reports `no_apm_yml` for a package directory without one."""
    spec = yaml.safe_load((PACKAGE / "apm.yml").read_text())
    assert spec["name"] == "project-scaffold-update"
    # Mandatory whenever the codex output is built.
    assert spec["category"] == "workflow"


def test_the_per_package_plugin_manifests_are_committed() -> None:
    """apm pack writes only the root catalogs. Claude reads the per-package manifest at the
    catalog's source path, so without it the package lists and does not install."""
    for directory in (".claude-plugin", ".codex-plugin"):
        manifest = json.loads((PACKAGE / directory / "plugin.json").read_text())
        assert manifest["name"] == "project-scaffold-update"
        assert manifest["skills"] == "./.apm/skills"


def test_the_root_manifest_publishes_it() -> None:
    manifest = yaml.safe_load((REPO_ROOT / "apm.yml").read_text())
    sources = {entry["source"] for entry in manifest["marketplace"]["packages"]}
    assert "./packages/project-scaffold-update" in sources


def test_both_catalogs_carry_both_packages() -> None:
    """`apm pack` rebuilds these and they are committed, so a package added to apm.yml
    without a pack leaves the catalogs behind and a consumer resolving from a clone never
    sees it."""
    claude = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    codex = json.loads((REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text())

    assert {plugin["name"] for plugin in claude["plugins"]} == {
        "project-scaffold",
        "project-scaffold-update",
    }
    # Codex nests the source under a local descriptor rather than a bare string.
    assert {plugin["source"]["path"] for plugin in codex["plugins"]} == {
        "./packages/project-scaffold",
        "./packages/project-scaffold-update",
    }


def test_release_please_tracks_it() -> None:
    """Untracked, it never gets a tag, and the marketplace resolves a version against
    whatever release-please tagged."""
    config = json.loads((REPO_ROOT / "release-please-config.json").read_text())
    entry = config["packages"]["packages/project-scaffold-update"]
    assert entry["component"] == "project-scaffold-update"
    # The version in apm.yml is what the catalog carries, so release-please has to bump it.
    assert entry["extra-files"] == [
        {"type": "yaml", "path": "apm.yml", "jsonpath": "$.version"}
    ]

    tracked = json.loads((REPO_ROOT / ".release-please-manifest.json").read_text())
    version = yaml.safe_load((PACKAGE / "apm.yml").read_text())["version"]
    assert tracked["packages/project-scaffold-update"] == version
