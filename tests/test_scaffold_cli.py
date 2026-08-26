"""`scaffold plan`: who owns each path, and when two owners is a refusal.

The conflict rule is the whole reason `plan` exists. Two recipes writing one path used to
mean whichever rendered last won, silently, and the only way to find out was to read the
rendered file. Now it is an exit code before anything touches disk.

The recipes here are throwaway directories under `tmp_path` rather than entries in
`recipes/`: `resolve_source` takes a path as readily as an in-repo id, so a fixture needs no
place in the real catalog, and the matrix stays readable at four files instead of thirty-six.
"""

from __future__ import annotations

import json
from pathlib import Path

from conftest import load_scaffold, render_recipe, scaffold

SHARED = "shared.txt"
FRAGMENT = ".gitignore.d/40-probe.gitignore"


def recipe(root: Path, name: str, files: dict[str, str], extra: str = "") -> str:
    """One throwaway recipe: a copier.yml and a template/ tree. Returns its source path."""
    directory = root / name
    (directory / "template").mkdir(parents=True)
    (directory / "copier.yml").write_text("_subdirectory: template\n" + extra)
    for relative, body in files.items():
        path = directory / "template" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)
    return str(directory)


def skips(*paths: str) -> str:
    return "_skip_if_exists:\n" + "".join(f"  - {path}\n" for path in paths)


def plan(*sources: str, dest: Path) -> tuple[int, dict]:
    """The plan as JSON, with its exit code. 5 means it refused."""
    result = scaffold("plan", *sources, "--dest", str(dest), "--json")
    payload = json.loads(result.stdout) if result.stdout.strip() else {}
    return result.returncode, payload


def classes(payload: dict) -> dict[str, str]:
    return {entry["path"]: entry["class"] for entry in payload["files"]}


# --- two owners of one path ------------------------------------------------


def test_two_owners_of_one_path_refuse(tmp_path: Path) -> None:
    """Exit 5 and both owners named, so the report says which two recipes to reconcile
    rather than that something is wrong."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n"})
    beta = recipe(tmp_path, "beta", {SHARED: "beta\n"})

    code, payload = plan(alpha, beta, dest=tmp_path / "dest")

    assert code == 5
    assert classes(payload)[SHARED] == "conflict"
    assert payload["conflicts"] == [{"path": SHARED, "owners": [alpha, beta]}]


def test_the_conflict_report_names_both_owners_on_stderr(tmp_path: Path) -> None:
    """The human-readable form, which is what a person or an agent actually reads."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n"})
    beta = recipe(tmp_path, "beta", {SHARED: "beta\n"})

    result = scaffold("plan", alpha, beta, "--dest", str(tmp_path / "dest"))

    assert result.returncode == 5
    assert SHARED in result.stderr
    assert alpha in result.stderr and beta in result.stderr
    assert "_skip_if_exists" in result.stderr, "the report must name the way out"


def test_the_later_writer_declaring_skip_if_exists_resolves_it(tmp_path: Path) -> None:
    """Both recipes opted into first-writer-wins, so the outcome is deterministic and the
    plan says `skip` instead of refusing."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n"})
    gamma = recipe(tmp_path, "gamma", {SHARED: "gamma\n"}, extra=skips(SHARED))

    code, payload = plan(alpha, gamma, dest=tmp_path / "dest")

    assert code == 0
    assert classes(payload)[SHARED] == "skip"
    assert payload["conflicts"] == []


def test_the_first_writer_declaring_it_is_not_enough(tmp_path: Path) -> None:
    """`_skip_if_exists` protects a path that is already there, so it resolves nothing on
    the recipe that writes it first. Only the later writers opting out settles the order."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n"}, extra=skips(SHARED))
    beta = recipe(tmp_path, "beta", {SHARED: "beta\n"})

    code, _ = plan(alpha, beta, dest=tmp_path / "dest")

    assert code == 5


# --- fragments -------------------------------------------------------------


def test_differently_named_fragments_never_conflict(tmp_path: Path) -> None:
    """An aggregator folds the whole directory, so two recipes each dropping their own file
    into it is the normal case rather than a collision. Each reads as `fragment` rather than
    `create`: what the generated file ends up saying is the aggregator's call, not the
    plan's."""
    alpha = recipe(tmp_path, "alpha", {".gitignore.d/40-alpha.gitignore": "a\n"})
    beta = recipe(tmp_path, "beta", {".gitignore.d/50-beta.gitignore": "b\n"})

    code, payload = plan(alpha, beta, dest=tmp_path / "dest")

    assert code == 0
    assert classes(payload) == {
        ".gitignore.d/40-alpha.gitignore": "fragment",
        ".gitignore.d/50-beta.gitignore": "fragment",
    }


def test_the_same_fragment_path_from_two_recipes_is_a_conflict(tmp_path: Path) -> None:
    """The aggregator merges the directory, not the file. Two recipes writing one fragment
    path means one of them is discarded, which is the thing the fold hides."""
    alpha = recipe(tmp_path, "alpha", {FRAGMENT: "a\n"})
    delta = recipe(tmp_path, "delta", {FRAGMENT: "d\n"})

    code, payload = plan(alpha, delta, dest=tmp_path / "dest")

    assert code == 5
    assert classes(payload)[FRAGMENT] == "conflict"


def test_skip_if_exists_does_not_rescue_a_shared_fragment(tmp_path: Path) -> None:
    """Sharper than the case above, and the reason `is_fragment` is consulted first: a
    fragment silently folded into a generated file gives first-writer-wins nothing to mean.
    """
    alpha = recipe(tmp_path, "alpha", {FRAGMENT: "a\n"})
    delta = recipe(tmp_path, "delta", {FRAGMENT: "d\n"}, extra=skips(FRAGMENT))

    code, payload = plan(alpha, delta, dest=tmp_path / "dest")

    assert code == 5
    assert classes(payload)[FRAGMENT] == "conflict"


def test_a_merge_glob_extends_the_fold_directories(tmp_path: Path) -> None:
    """`_scaffold.merge` is how a recipe declares a directory the built-in list does not
    carry. Without it the shared path would resolve to `skip`; with it, the same pair
    refuses, which is what makes the glob observable at all.
    """
    shared = "conf.d/probe.conf"
    merge = '_scaffold:\n  merge: ["conf.d/*"]\n'

    without = plan(
        recipe(tmp_path / "plain", "alpha", {shared: "a\n"}),
        recipe(tmp_path / "plain", "beta", {shared: "b\n"}, extra=skips(shared)),
        dest=tmp_path / "dest",
    )
    assert without[0] == 0
    assert classes(without[1])[shared] == "skip"

    declared = plan(
        recipe(tmp_path / "merged", "alpha", {shared: "a\n"}, extra=merge),
        recipe(tmp_path / "merged", "beta", {shared: "b\n"}, extra=skips(shared)),
        dest=tmp_path / "dest",
    )
    assert declared[0] == 5
    assert classes(declared[1])[shared] == "conflict"


# --- the plan's shape and its promise --------------------------------------


def test_the_json_plan_carries_a_path_owners_and_a_class_per_file(tmp_path: Path) -> None:
    """The machine-readable form the skill reads back to the user before rendering, and the
    whole class vocabulary a single-owner recipe can produce."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n", ".gitignore.d/40-a.gitignore": "a\n"})

    code, payload = plan(alpha, dest=tmp_path / "dest")

    assert code == 0
    assert set(payload) == {"files", "conflicts"}
    for entry in payload["files"]:
        assert set(entry) == {"path", "owners", "class"}
        assert entry["owners"] == [alpha]
    assert classes(payload) == {SHARED: "create", ".gitignore.d/40-a.gitignore": "fragment"}


def test_a_path_already_in_the_destination_is_an_overwrite(tmp_path: Path) -> None:
    """`create` and `overwrite` is the split that decides whether a retrofit needs review."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n"})
    dest = tmp_path / "dest"
    dest.mkdir()
    (dest / SHARED).write_text("mine\n")

    code, payload = plan(alpha, dest=dest)

    assert code == 0
    assert classes(payload)[SHARED] == "overwrite"


def test_plan_writes_nothing(tmp_path: Path) -> None:
    """It renders into a scratch tree to learn the paths, which is what makes a jinja-named
    or conditional file exact. None of that may reach the destination."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n"})
    dest = tmp_path / "dest"
    dest.mkdir()

    code, _ = plan(alpha, dest=dest)

    assert code == 0
    assert list(dest.rglob("*")) == []


# --- the gate render sits behind -------------------------------------------


def test_render_refuses_a_conflicting_set(tmp_path: Path) -> None:
    """The plan is not advisory. A render naming both recipes stops before writing."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n"})
    beta = recipe(tmp_path, "beta", {SHARED: "beta\n"})
    dest = tmp_path / "dest"

    result = scaffold("render", alpha, beta, "--dest", str(dest))

    assert result.returncode == 5
    assert not (dest / SHARED).exists()


def test_force_renders_past_a_conflict(tmp_path: Path) -> None:
    """The user's call to make, and the last writer wins: the flag exists so the refusal is
    not a dead end when the overlap is understood."""
    alpha = recipe(tmp_path, "alpha", {SHARED: "alpha\n"})
    beta = recipe(tmp_path, "beta", {SHARED: "beta\n"})
    dest = tmp_path / "dest"

    result = scaffold("render", alpha, beta, "--dest", str(dest), "--force")

    assert result.returncode == 0, result.stderr
    assert (dest / SHARED).read_text() == "beta\n"


# --- check-answers ---------------------------------------------------------


def asks(question: str) -> str:
    return f"\n{question}:\n  type: str\n"


def test_a_question_with_no_default_is_reported_with_its_recipe(tmp_path: Path) -> None:
    """`--defaults` cannot fill it, and the CLI never prompts, so a gap has to surface as a
    finding before the render rather than as a copier prompt during one."""
    needy = recipe(
        tmp_path, "needy", {"name.txt.jinja": "{{ service_name }}\n"}, extra=asks("service_name")
    )

    result = scaffold("check-answers", needy)

    assert result.returncode == 1
    assert f"Provide a value for 'service_name' in recipe '{needy}'" in result.stderr


def test_every_gap_is_reported_at_once(tmp_path: Path) -> None:
    """One key per run would be one interview turn per run. The agent re-asks the whole set,
    so the whole set has to arrive together."""
    first = recipe(tmp_path, "first", {"a.txt.jinja": "{{ alpha }}\n"}, extra=asks("alpha"))
    second = recipe(tmp_path, "second", {"b.txt.jinja": "{{ beta }}\n"}, extra=asks("beta"))

    result = scaffold("check-answers", first, second)

    assert result.returncode == 1
    assert "'alpha'" in result.stderr
    assert "'beta'" in result.stderr


def test_a_provided_answer_closes_the_gap(tmp_path: Path) -> None:
    needy = recipe(
        tmp_path, "needy", {"name.txt.jinja": "{{ service_name }}\n"}, extra=asks("service_name")
    )

    result = scaffold("check-answers", needy, "--data", "service_name=widget")

    assert result.returncode == 0
    assert "answers complete" in result.stdout


def test_a_question_carrying_a_default_is_not_a_gap(tmp_path: Path) -> None:
    """`--defaults` fills it, so asking would spend a turn on an answer already decided."""
    source = recipe(
        tmp_path,
        "defaulted",
        {"r.txt.jinja": "{{ region }}\n"},
        extra="\nregion:\n  type: str\n  default: eu-west-1\n",
    )

    result = scaffold("check-answers", source)

    assert result.returncode == 0
    assert "answers complete" in result.stdout


def test_an_answered_recipe_renders_what_the_answer_says(tmp_path: Path) -> None:
    """The end of the loop: a gap closed by `--data-file` is a render that succeeds."""
    needy = recipe(
        tmp_path, "needy", {"name.txt.jinja": "{{ service_name }}\n"}, extra=asks("service_name")
    )
    dest = tmp_path / "dest"

    result = render_recipe(needy, dest, "service_name: widget\n")

    assert result.returncode == 0, result.stderr
    assert (dest / "name.txt").read_text() == "widget\n"


# --- a profile plus positional extras ---------------------------------------


def test_profile_plus_extras_union(tmp_path: Path) -> None:
    """`--profile` used to ignore positional recipes with exit 0 -- a plan for the
    wrong set. Now they union in and the extra's files appear in the map."""
    result = scaffold(
        "plan",
        "--profile",
        "go-app",
        "release/dep-updates",
        "--dest",
        str(tmp_path / "dest"),
        "--demo",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    owners = {entry["path"]: entry["owners"] for entry in json.loads(result.stdout)["files"]}
    assert owners.get("renovate.json") == ["release/dep-updates"]


def test_profile_plus_extras_orders_fragments_before_aggregators(tmp_path: Path) -> None:
    """lang/api appended naively lands after workspace/just and quality/hooks and
    would refuse; the union is toposorted by `after` and fragment edges instead."""
    result = scaffold(
        "plan",
        "--profile",
        "go-app",
        "lang/api",
        "--dest",
        str(tmp_path / "dest"),
        "--demo",
        "--json",
    )

    assert result.returncode == 0, result.stderr
    assert "warning:" not in result.stderr


def test_profile_plus_impossible_extra_refuses(tmp_path: Path) -> None:
    """Reordering fixes position, not absence: docs/api-refs without docs/site is a
    REQUIRES problem and exits 2 naming what is missing."""
    result = scaffold(
        "plan",
        "--profile",
        "go-app",
        "docs/api-refs",
        "--dest",
        str(tmp_path / "dest"),
        "--demo",
    )

    assert result.returncode == 2
    assert "docs/site" in result.stderr


def test_positional_set_warns_but_runs() -> None:
    """A hand-named order is the user's own; a violated `after` prints a warning
    rather than refusing."""
    result = scaffold("check-answers", "host/github", "lang/go")

    assert "warning: puts host/github before lang/go" in result.stderr


def test_order_set_places_an_extra_by_its_declared_edges() -> None:
    """The unit under the union: lang/api sorts before the aggregators it feeds
    (.just.d, .pre-commit.d) and before host/github, which declares `after: lang/*`."""
    ordered = load_scaffold().order_set(
        [
            "base/license",
            "base/repo",
            "lang/go",
            "host/github",
            "workspace/just",
            "quality/hooks",
            "base/gitignore",
            "lang/api",
        ]
    )

    position = {recipe: index for index, recipe in enumerate(ordered)}
    for later in ("workspace/just", "quality/hooks", "host/github"):
        assert position["lang/api"] < position[later], ordered
