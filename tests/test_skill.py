"""The project-scaffold skill, and this repository publishing itself.

The repository is now the `agentic-repo` shape it scaffolds: one package under
`packages/`, its own marketplace block, and the catalogs committed. That is the strongest
available check on `agentic/package`, since a layer that cannot publish the repository
that defines it is a layer that does not work.

The skill is prose, so these tests assert the contract rather than the wording: it asks
exactly the six questions `rules/choices.md` marks as asked, names no question that
document marks fixed or derived, and points at every profile that exists.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = (
    REPO_ROOT
    / "packages"
    / "project-scaffold"
    / ".apm"
    / "skills"
    / "project-scaffold"
    / "SKILL.md"
)
PACKAGE = REPO_ROOT / "packages" / "project-scaffold"
PROFILES = REPO_ROOT / "profiles"
CHOICES = REPO_ROOT / "rules" / "choices.md"


def skill_body() -> str:
    return SKILL.read_text()


def frontmatter() -> dict:
    return yaml.safe_load(skill_body().split("---")[1])


# --- the skill's own shape -------------------------------------------------


def test_the_skill_exists_where_apm_deploys_from() -> None:
    """`.apm/skills/<name>/SKILL.md` is the layout apm integrates, verified against
    srobroek/speckit-conductor, whose skills install from exactly this path."""
    assert SKILL.is_file()


def test_the_frontmatter_carries_a_matching_trigger() -> None:
    """The description is what an agent matches on to decide whether to load the skill, so
    it states when to use it rather than what it is."""
    meta = frontmatter()
    assert meta["name"] == "project-scaffold"
    description = meta["description"].lower()
    assert "use when" in description
    # The verbs a person actually types.
    for trigger in ("set up", "scaffold", "initialize", "bootstrap"):
        assert trigger in description, f"{trigger!r} is not a trigger"


def test_it_stays_under_the_line_budget() -> None:
    """Target 120 lines. A skill long enough to skim is a skill nobody reads."""
    assert len(skill_body().splitlines()) <= 120


# --- the interview ---------------------------------------------------------


def test_it_asks_exactly_the_six_questions() -> None:
    """rules/choices.md fixes the count, and a seventh question is one whose answer the
    document already derives."""
    body = skill_body()
    section = body.partition("## The interview")[2].partition("## Pick the profile")[0]
    numbered = [
        line for line in section.splitlines() if line.strip()[:2] in {f"{n}." for n in range(1, 10)}
    ]
    assert len(numbered) == 6, f"expected six questions, found {len(numbered)}"
    assert "six questions" in body


def test_it_asks_nothing_the_choices_table_derives() -> None:
    """A derived question wastes a turn and invites an answer contradicting the tree."""
    body = skill_body()
    section = body.partition("## The interview")[2].partition("## Pick the profile")[0].lower()
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


def test_every_profile_is_reachable_from_the_skill() -> None:
    """A shape the skill cannot name is a shape nobody renders."""
    body = skill_body()
    for path in sorted(PROFILES.glob("*.yml")):
        assert path.stem in body, f"the skill never names {path.stem}"


def test_it_names_the_recipes_that_exist() -> None:
    justfile = (REPO_ROOT / "justfile").read_text()
    body = skill_body()
    for recipe in ("render-profile", "profiles", "render", "preview"):
        assert recipe in body
        assert f"\n{recipe}" in justfile or f"{recipe} " in justfile


def test_it_carries_the_two_ordering_traps() -> None:
    """Both cost real time to find. The generator order silently produces a repository that
    is not a workspace, and a contributor after its aggregator leaves a generated file
    stale, which `just just-check` then fails on."""
    body = skill_body()
    assert "workspace/monorepo" in body
    assert "[workspace]" in body
    assert "aggregator" in body.lower()


def test_it_says_a_repository_takes_one_apm_yml() -> None:
    """agentic/apm and agentic/package own the same path, so naming both is a render that
    overwrites one with the other."""
    body = skill_body()
    assert "agentic/apm" in body
    assert "agentic/package" in body
    assert "never both" in body


# --- this repository publishes itself --------------------------------------


def test_the_repository_is_its_own_agentic_repo() -> None:
    """The shape it scaffolds, applied to itself: a layer that cannot publish the repository
    defining it does not work."""
    manifest = yaml.safe_load((REPO_ROOT / "apm.yml").read_text())
    assert "marketplace" in manifest
    assert manifest["marketplace"]["packages"][0]["source"] == "./packages/project-scaffold"
    # claude and codex only: apm registers no kiro marketplace mapper.
    assert set(manifest["marketplace"]["outputs"]) == {"claude", "codex"}
    # kiro IS a deploy target, which is the distinction the package layer exists to keep.
    assert "kiro" in manifest["targets"]


def test_the_package_carries_its_own_manifest() -> None:
    """`apm pack --check-versions` reports `no_apm_yml` for a package directory without one."""
    assert (PACKAGE / "apm.yml").is_file()
    package = yaml.safe_load((PACKAGE / "apm.yml").read_text())
    assert package["category"], "the codex output requires a category on every package"


def test_the_per_package_plugin_manifests_are_committed() -> None:
    """apm pack writes only the root catalogs. Claude's /plugin install reads the
    per-package manifest at the catalog's source path, so without it the package lists but
    does not install."""
    for directory in (".claude-plugin", ".codex-plugin"):
        manifest = json.loads((PACKAGE / directory / "plugin.json").read_text())
        assert manifest["name"] == "project-scaffold"
        assert manifest["skills"] == "./.apm/skills"


def test_the_catalogs_are_committed_and_current() -> None:
    """agentic-packages and break-stuff both track these, which is what lets a consumer
    resolve the marketplace from a clone with no build step."""
    claude = json.loads((REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text())
    assert claude["plugins"][0]["source"] == "./packages/project-scaffold"

    codex = json.loads((REPO_ROOT / ".agents" / "plugins" / "marketplace.json").read_text())
    # Codex nests the source under a local descriptor rather than a bare string.
    assert codex["plugins"][0]["source"]["path"] == "./packages/project-scaffold"


def test_the_tag_pattern_matches_release_please() -> None:
    """The marketplace resolves a version against whatever release-please tags, and neither
    apm gate detects a mismatch."""
    config = json.loads((REPO_ROOT / "release-please-config.json").read_text())
    assert config["include-component-in-tag"] is True
    assert config["tag-separator"] == "--"

    manifest = yaml.safe_load((REPO_ROOT / "apm.yml").read_text())
    assert manifest["marketplace"]["build"]["tagPattern"] == "{name}--v{version}"


def test_the_versions_agree() -> None:
    root = yaml.safe_load((REPO_ROOT / "apm.yml").read_text())["version"]
    package = yaml.safe_load((PACKAGE / "apm.yml").read_text())["version"]
    tracked = json.loads((REPO_ROOT / ".release-please-manifest.json").read_text())
    assert root == package == tracked["packages/project-scaffold"]


def test_the_skill_points_at_the_documents_rather_than_restating_them() -> None:
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

    # The layer inventory belongs to docs/layers.md and docs/INDEX.md.
    assert "| Layer | Writes |" not in body


def test_the_profile_table_names_shapes_rather_than_layer_sets() -> None:
    """The profile file carries its own layer list, so the skill routes to it instead of
    repeating it. A layer set in two places is a layer set that disagrees with itself."""
    body = skill_body()
    section = body.partition("## Pick the profile")[2].partition("## Render")[0]
    # No layer paths in the routing table.
    assert "base/repo" not in section
    assert "quality/hooks" not in section
    assert "Read the file" in section


def test_the_repository_can_actually_release_itself() -> None:
    """The release-please config and manifest were committed with no workflow to read them.

    Nothing caught it: test_the_repository_is_its_own_agentic_repo checks the apm.yml shape,
    test_release_please_tracks_it checks the manifest entry, and neither asks whether anything
    runs. The repository publishes two APM packages whose versions release-please owns, so with
    no workflow it could never tag, never write a changelog, and never bump either apm.yml --
    while every test about publishing passed.
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

    # The gate deliberately carries neither, which is why this is a separate workflow.
    permissions = workflow["jobs"]["release-please"]["permissions"]
    assert permissions["contents"] == "write"
    assert permissions["pull-requests"] == "write"


def test_every_package_release_please_tracks_is_published() -> None:
    """The two manifests have to agree, or release-please bumps a package the marketplace never
    ships, or the marketplace ships one whose version nothing maintains."""
    config = json.loads((REPO_ROOT / "release-please-config.json").read_text())
    tracked = {path for path in config["packages"] if path != "."}

    manifest = yaml.safe_load((REPO_ROOT / "apm.yml").read_text())
    published = {
        entry["source"].removeprefix("./") for entry in manifest["marketplace"]["packages"]
    }
    assert tracked == published, f"release-please tracks {tracked}, marketplace ships {published}"


def test_the_catalogs_are_gated_against_drift() -> None:
    """`just check` has to fail when a package reaches apm.yml and the catalogs stay behind.

    Verified against apm rather than assumed: dropping one plugin from
    `.claude-plugin/marketplace.json` made `just packages` exit 4, and restoring it exit 0.
    `--dry-run` is load-bearing on `--check-clean`, because without it the run regenerates the
    catalogs first and then passes against what it just wrote.
    """
    justfile = (REPO_ROOT / "justfile").read_text()
    assert "\npackages:" in justfile, "no recipe checks the committed catalogs"
    # The release workflow's sync step calls `package-build` by that name, matching what the
    # agentic/package layer ships. Without it the sync fails with `justfile does not contain
    # recipe`, which is how this repository broke its own release run.
    assert "\npackage-build:" in justfile
    assert "--check-clean --dry-run" in justfile
    assert "--check-versions --dry-run" in justfile

    # In `check`, so a contributor and CI run it without asking.
    check = next(
        line for line in justfile.splitlines() if line.startswith("check:")
    )
    assert "packages" in check.split(), f"`packages` is not in the gate: {check}"


def test_the_kiro_rationale_survives_a_release() -> None:
    """release-please rewrites apm.yml to bump `version`, and its YAML writer drops comments.

    The 0.2.0 release silently removed the note explaining why kiro is a deploy target but not a
    marketplace output -- a distinction the agentic/package layer exists to keep, and the one
    thing about this manifest a reader cannot infer from the keys. Restoring it by hand after
    every release only works if something notices, so this is what notices.
    """
    body = (REPO_ROOT / "apm.yml").read_text()
    assert "kiro is a target rather than a marketplace" in body, (
        "the kiro rationale is gone from apm.yml; release-please's YAML writer strips comments, "
        "so restore it after the release"
    )
