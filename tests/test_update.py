"""`scaffold update`: replay the recorded ref, then 3-way merge the difference over drift.

What makes this possible at all is `_ref`. `copier update` refuses outright here -- `Cannot
update because cannot obtain old template references` -- because a recipe is a subdirectory
of a template repository rather than its root, so copier records no `_commit`. The CLI
records the source's HEAD itself at render time, and `update` renders the recipe twice: once
at that ref, once at HEAD, then merges the difference into the working tree.

The fixture recipe lives in its own git repository under `tmp_path`, because replaying a ref
needs a checkout to replay it from. That is also the shape a recipe outside this repository
arrives in, so the test exercises the general case rather than the in-repo shortcut.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import render_recipe, scaffold

RECIPES = Path(__file__).resolve().parent.parent / "recipes"

ANSWERS_FILE = ".copier-answers.widget.yml"
CONFIG = "one = 1\ntwo = 2\nthree = 3\n"
COPIER_YML = f"""\
_subdirectory: template
_answers_file: {ANSWERS_FILE}
tone:
  type: str
  default: plain
"""


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout


def commit(repo: Path, message: str) -> None:
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", message)


@pytest.fixture
def recipe(tmp_path: Path) -> Path:
    """A small recipe in its own git repository.

    It ships `{{ _copier_conf.answers_file }}.jinja`: copier writes the answers file only
    where the template asks for one, and without it there is nothing for `_ref` to land in.

    `tone` carries a default, so nothing has to answer it, and `tone.txt` renders it. That
    is what makes a refreshed answer visible as file content rather than only as a line in
    the answers file.
    """
    directory = tmp_path / "widget"
    template = directory / "template"
    template.mkdir(parents=True)
    (directory / "copier.yml").write_text(COPIER_YML)
    (template / "{{ _copier_conf.answers_file }}.jinja").write_text(
        "{{ _copier_answers|to_nice_yaml -}}\n"
    )
    (template / "config.toml").write_text(CONFIG)
    (template / "tone.txt.jinja").write_text("tone = {{ tone }}\n")

    git(tmp_path, "init", "-q", str(directory))
    git(directory, "config", "user.email", "t@e.com")
    git(directory, "config", "user.name", "T")
    commit(directory, "the recipe")
    return directory


@pytest.fixture
def rendered(recipe: Path, tmp_path: Path) -> Path:
    """The recipe rendered once, with the destination committed."""
    dest = tmp_path / "dest"
    result = render_recipe(str(recipe), dest)
    assert result.returncode == 0, result.stderr
    assert (dest / ANSWERS_FILE).is_file(), "nothing recorded the ref"
    return dest


def retarget(recipe: Path, body: str, message: str) -> None:
    (recipe / "template" / "config.toml").write_text(body)
    commit(recipe, message)


def drift(dest: Path, body: str) -> None:
    (dest / "config.toml").write_text(body)
    commit(dest, "local drift")


def update(recipe: Path, dest: Path, *data: str) -> subprocess.CompletedProcess[str]:
    """`scaffold update`, each `data` a `KEY=VALUE` answer to refresh on the way through."""
    argv = ["update", str(recipe), "--dest", str(dest)]
    for pair in data:
        argv += ["--data", pair]
    return scaffold(*argv)


# --- what render leaves behind for update ----------------------------------


def test_render_records_the_source_head_and_id(recipe: Path, rendered: Path) -> None:
    """`_ref` is what `update` replays and `_source` is what it replays from. copier's own
    `_commit` is absent for an in-repo recipe, which is why both are recorded here."""
    answers = yaml.safe_load((rendered / ANSWERS_FILE).read_text())
    assert answers["_ref"] == git(recipe, "rev-parse", "HEAD").strip()
    assert answers["_source"] == str(recipe)


# --- the merge -------------------------------------------------------------


def test_a_recipe_change_lands_on_an_untouched_file(recipe: Path, rendered: Path) -> None:
    retarget(recipe, "one = 1\ntwo = 2\nthree = 33\n", "bump three")

    result = update(recipe, rendered)

    assert result.returncode == 0, result.stderr
    assert (rendered / "config.toml").read_text() == "one = 1\ntwo = 2\nthree = 33\n"


def test_drift_survives_a_recipe_change_elsewhere_in_the_file(
    recipe: Path, rendered: Path
) -> None:
    """The whole point. `render` passes `--overwrite`, so re-rendering would have replaced
    the hand-edited line with no prompt; the 3-way merge keeps both changes."""
    drift(rendered, "one = 111\ntwo = 2\nthree = 3\n")
    retarget(recipe, "one = 1\ntwo = 2\nthree = 33\n", "bump three")

    result = update(recipe, rendered)

    assert result.returncode == 0, result.stderr
    assert (rendered / "config.toml").read_text() == "one = 111\ntwo = 2\nthree = 33\n"
    assert "merged" in result.stdout


def test_an_overlapping_change_conflicts(recipe: Path, rendered: Path) -> None:
    """Both sides edited the same line, so there is no answer to pick. Standard markers and
    exit 5, which is a human's decision rather than a silent one."""
    drift(rendered, "one = 1\ntwo = 222\nthree = 3\n")
    retarget(recipe, "one = 1\ntwo = 22\nthree = 3\n", "bump two")

    result = update(recipe, rendered)

    assert result.returncode == 5
    body = (rendered / "config.toml").read_text()
    assert "<<<<<<< local" in body
    assert ">>>>>>> updated" in body
    assert "222" in body and "22" in body
    assert "conflict markers" in result.stderr


def test_a_file_the_recipe_gained_is_created(recipe: Path, rendered: Path) -> None:
    """A recipe that grew a file has nothing to merge against, so the file is written."""
    (recipe / "template" / "extra.txt").write_text("new\n")
    commit(recipe, "add a file")

    result = update(recipe, rendered)

    assert result.returncode == 0, result.stderr
    assert (rendered / "extra.txt").read_text() == "new\n"


# --- a refreshed answer ----------------------------------------------------


def test_a_refreshed_answer_lands_in_the_content_it_renders(
    recipe: Path, rendered: Path
) -> None:
    """`--data` is how a recorded answer changes, and the answer is only worth anything if
    it reaches the files. The base render replays the RECORDED answers and only the new
    render sees `--data`, so the refresh arrives as a template-side diff and merges like any
    recipe change. Feeding both renders would make the base agree with the destination,
    which reads as `unchanged` and silently drops the new answer.
    """
    assert (rendered / "tone.txt").read_text() == "tone = plain\n", "the default did not render"

    result = update(recipe, rendered, "tone=loud")

    assert result.returncode == 0, result.stderr
    assert (rendered / "tone.txt").read_text() == "tone = loud\n"


def test_a_refreshed_answer_is_recorded_for_the_next_update(
    recipe: Path, rendered: Path
) -> None:
    """The answers file is the only memory of it. Were the old answer left recorded, the
    next update would replay `plain` as its base and revert the refresh."""
    assert update(recipe, rendered, "tone=loud").returncode == 0

    assert yaml.safe_load((rendered / ANSWERS_FILE).read_text())["tone"] == "loud"
    commit(rendered, "take the refreshed answer")

    result = update(recipe, rendered)

    assert result.returncode == 0, result.stderr
    assert (rendered / "tone.txt").read_text() == "tone = loud\n"


def test_a_local_edit_on_the_refreshed_line_conflicts(recipe: Path, rendered: Path) -> None:
    """A refreshed answer is not privileged over a hand edit: same line, both sides, so the
    same markers and the same exit 5 a recipe change gets."""
    (rendered / "tone.txt").write_text("tone = hand\n")
    commit(rendered, "local drift")

    result = update(recipe, rendered, "tone=loud")

    assert result.returncode == 5
    body = (rendered / "tone.txt").read_text()
    assert "<<<<<<< local" in body
    assert "hand" in body and "loud" in body


def test_an_answer_nobody_refreshed_survives_an_update(recipe: Path, rendered: Path) -> None:
    """Without this, every update would reset the tree to the recipe's defaults."""
    render = render_recipe(str(recipe), rendered.parent / "answered", "tone: quiet\n")
    assert render.returncode == 0, render.stderr
    answered = rendered.parent / "answered"
    retarget(recipe, "one = 1\ntwo = 2\nthree = 33\n", "bump three")

    result = update(recipe, answered)

    assert result.returncode == 0, result.stderr
    assert (answered / "tone.txt").read_text() == "tone = quiet\n"
    assert (answered / "config.toml").read_text() == "one = 1\ntwo = 2\nthree = 33\n"


# --- the answers file ------------------------------------------------------


def test_the_answers_file_is_taken_from_head_and_carries_the_new_ref(
    recipe: Path, rendered: Path
) -> None:
    """A 3-way merge of YAML mangles it, so the CLI owns this file: HEAD's copy verbatim,
    then the ref rewritten. Without the rewrite a second update replays the first ref."""
    before = yaml.safe_load((rendered / ANSWERS_FILE).read_text())["_ref"]
    retarget(recipe, "one = 1\ntwo = 2\nthree = 33\n", "bump three")

    result = update(recipe, rendered)

    assert result.returncode == 0, result.stderr
    body = (rendered / ANSWERS_FILE).read_text()
    assert "<<<<<<<" not in body, "the answers file went through a merge"
    answers = yaml.safe_load(body)
    assert answers["_ref"] == git(recipe, "rev-parse", "HEAD").strip()
    assert answers["_ref"] != before
    assert "answers" in result.stdout


def test_a_conflicted_update_is_not_applied(recipe: Path, rendered: Path) -> None:
    """Nothing about a conflicting run half-lands. The answers file keeps its recorded `_ref`,
    so a re-run replays the same base and conflicts the same way instead of replaying HEAD
    against HEAD and reporting success over markers nobody resolved.
    """
    before = yaml.safe_load((rendered / ANSWERS_FILE).read_text())["_ref"]
    drift(rendered, "one = 1\ntwo = 222\nthree = 3\n")
    retarget(recipe, "one = 1\ntwo = 22\nthree = 3\n", "bump two")

    first = update(recipe, rendered)

    assert first.returncode == 5
    assert "keeps its recorded _ref until the conflicts resolve" in first.stdout
    assert yaml.safe_load((rendered / ANSWERS_FILE).read_text())["_ref"] == before

    assert update(recipe, rendered).returncode == 5
    assert yaml.safe_load((rendered / ANSWERS_FILE).read_text())["_ref"] == before


def test_resolving_the_conflict_lets_the_next_update_land(recipe: Path, rendered: Path) -> None:
    """The other end of that loop, and what makes a conflict a pause rather than a dead end:
    a resolution matching the new render leaves the replay nothing to merge, so it comes out
    clean and the ref finally advances.
    """
    drift(rendered, "one = 1\ntwo = 222\nthree = 3\n")
    retarget(recipe, "one = 1\ntwo = 22\nthree = 3\n", "bump two")
    assert update(recipe, rendered).returncode == 5

    (rendered / "config.toml").write_text("one = 1\ntwo = 22\nthree = 3\n")
    commit(rendered, "resolve the conflict")

    result = update(recipe, rendered)

    assert result.returncode == 0, result.stderr
    assert "<<<<<<<" not in (rendered / "config.toml").read_text()
    answers = yaml.safe_load((rendered / ANSWERS_FILE).read_text())
    assert answers["_ref"] == git(recipe, "rev-parse", "HEAD").strip()


# --- the refusals ----------------------------------------------------------


def test_a_destination_that_was_never_rendered_is_refused(recipe: Path, tmp_path: Path) -> None:
    """No answers file means no ref, and guessing one would replay an arbitrary commit."""
    bare = tmp_path / "bare"
    bare.mkdir()

    result = update(recipe, bare)

    assert result.returncode == 2
    assert ANSWERS_FILE in result.stderr


def test_an_answers_file_with_no_ref_is_refused(recipe: Path, rendered: Path) -> None:
    """A tree scaffolded before ref recording. The skill's answer is to render instead,
    passing that file as `--data-file`, and read the diff."""
    answers = yaml.safe_load((rendered / ANSWERS_FILE).read_text())
    del answers["_ref"]
    del answers["_commit"]
    (rendered / ANSWERS_FILE).write_text(yaml.safe_dump(answers))

    result = update(recipe, rendered)

    assert result.returncode == 2
    assert "_ref" in result.stderr


def test_a_recipe_with_no_checkout_is_refused(recipe: Path, rendered: Path) -> None:
    """A recipe fetched as a plain directory has no history to replay, so `update` says so
    rather than rendering HEAD over the tree and calling it a merge."""
    copy = recipe.parent / "copy"
    copy.mkdir()
    for path in ("copier.yml",):
        (copy / path).write_text((recipe / path).read_text())
    (copy / "template").mkdir()
    for path in (recipe / "template").iterdir():
        (copy / "template" / path.name).write_text(path.read_text())

    result = scaffold("update", str(copy), "--dest", str(rendered))

    assert result.returncode == 2
    assert "no git checkout" in result.stderr


# --- the aggregators it cannot re-fold -------------------------------------


def test_it_names_the_fold_to_re_run_when_a_fragment_changed(
    recipe: Path, rendered: Path
) -> None:
    """`update` merges the fragment and stops. The generated file the aggregator writes is
    stale from that moment, and nothing in the destination re-folds `.gitignore.d` -- its
    fold runs from a copier task inside base/gitignore. So the note is the whole handover.
    """
    fragment = recipe / "template" / ".gitignore.d" / "40-widget.gitignore"
    fragment.parent.mkdir(parents=True)
    fragment.write_text("build/\n")
    commit(recipe, "contribute a gitignore fragment")

    result = update(recipe, rendered)

    assert result.returncode == 0, result.stderr
    assert (rendered / ".gitignore.d" / "40-widget.gitignore").is_file()
    assert "note: .gitignore.d changed; re-run the base/gitignore fold" in result.stdout


# --- the recipes in this repository ----------------------------------------


def test_every_recipe_ships_the_answers_file_update_replays_from() -> None:
    """copier writes an answers file only where the template asks for one, so a recipe
    without `{{ _copier_conf.answers_file }}.jinja` renders perfectly and can never be
    updated: `update` finds no `_ref` and refuses. Nothing else here would notice, because
    every other test renders and reads the tree rather than re-rendering it later.
    """
    missing = []
    for config in sorted(RECIPES.glob("*/*/copier.yml")):
        body = yaml.safe_load(config.read_text()) or {}
        recipe_id = str(config.parent.relative_to(RECIPES))
        if not body.get("_answers_file"):
            missing.append(f"{recipe_id}: declares no _answers_file")
        elif not (
            config.parent / body.get("_subdirectory", ".") / "{{ _copier_conf.answers_file }}.jinja"
        ).is_file():
            missing.append(f"{recipe_id}: ships no answers-file template")

    assert not missing, f"recipes `update` could never replay: {missing}"
