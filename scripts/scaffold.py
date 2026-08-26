#!/usr/bin/env python3
"""The scaffold CLI: plan, render, update, and inspect recipe sets.

One entry point replacing render.py, render_profile.py, and profiles.py.
A recipe is one directory holding a copier.yml and, usually, a template/.
Recipes come from four places through one flag surface:

  lang/rust                    a recipe in this repository's recipes/
  ./path/to/recipe             a local directory
  https://host/user/repo.git   a git repository (copier clones it)
  gh:user/template             any remote copier template

Subcommands:

  list           recipes and profiles
  check          validate profiles against recipes/
  plan           the full file map -- owners, merges, conflicts -- writing nothing
  render         render recipes or a profile into a destination
  check-answers  every missing required answer, reported at once
  update         re-render against the recorded ref and 3-way merge drift

The skill asks questions; this tool renders. It never prompts: answers come
from --data and --data-file, and a missing required answer is a check-answers
finding rather than an interactive session.
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import NoReturn

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
# Both overridable so a test can validate a copied directory. Writing a fixture into the
# real profiles/ made the suite fail under `-n auto`: one worker saw another worker's
# file, and the test reading every profile counted it as real. A fixture recipe has the
# same problem, plus `docs/INDEX.md` and the render-every-profile check read recipes/.
RECIPES = Path(os.environ.get("SCAFFOLD_RECIPES") or REPO_ROOT / "recipes")
PROFILES = Path(os.environ.get("SCAFFOLD_PROFILES") or REPO_ROOT / "profiles")

# copier 9.17.0 stops applying its own DEFAULT_EXCLUDE once `_subdirectory` is
# set, and every recipe here sets it. A `.DS_Store` Finder wrote into a template
# directory then renders into the generated project. Because `.DS_Store` is
# gitignored, such a file never shows up in `git status`, so nothing else here
# would report it.
#
# `--exclude` REPLACES the default set rather than adding to it, so the whole
# default is repeated, plus the two macOS artifacts.
EXCLUDE = (
    "copier.yaml",
    "copier.yml",
    "~*",
    "*.py[co]",
    "__pycache__",
    ".git",
    ".DS_Store",
    ".svn",
    "._*",
)

# Directories whose files are fragments: an aggregator folds them into one
# generated file, so two recipes contributing differently-named fragments under
# one of these never conflict. Two recipes writing the SAME fragment path still do.
FRAGMENT_DIRS = (
    ".gitignore.d/",
    ".just.d/",
    ".mise/conf.d/",
    ".pre-commit.d/",
    ".github/quality.d/",
    ".github/security.d/",
    ".gitlab/ci/",
)

# Recipes that cannot function without another. Distinct from `after`, which
# orders two recipes a profile already named and says nothing about absence.
REQUIRES = {
    # The reference pages are generated in the code repo from its own source, so
    # the code repo is what has to build and push them. deploy-sibling builds
    # where the site lives, which is the one place the extractors cannot run.
    "docs/api-refs": ("docs/site", "docs/deploy-split"),
}

# Each aggregator and the directory it folds. A recipe shipping that directory
# in its template contributes to it and must render before the aggregator.
AGGREGATORS = (
    ("workspace/just", ".just.d"),
    ("base/gitignore", ".gitignore.d"),
    ("quality/hooks", ".pre-commit.d"),
)

REQUIRED_PROFILE_KEYS = ("name", "summary", "generator", "layers", "build")


def die(code: int, message: str) -> NoReturn:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


# --- sources -------------------------------------------------------------


class Source:
    """One recipe, wherever it lives.

    `id` is what the user said. `template` is what copier receives: a local
    directory for in-repo and path sources, the URL itself for git and copier
    templates. `repo` is the git checkout that can answer `rev-parse HEAD`
    for ref recording, when there is one.
    """

    def __init__(self, id: str, template: str, repo: Path | None, in_repo: bool):
        self.id = id
        self.template = template
        self.repo = repo
        self.in_repo = in_repo

    @property
    def name(self) -> str:
        """The short name answer files and plans use: `lang/rust` -> `rust`."""
        return self.id.rstrip("/").rsplit("/", 1)[-1]

    def head(self) -> str | None:
        if self.repo is None:
            return None
        result = subprocess.run(
            ["git", "-C", str(self.repo), "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout.strip() or None


def resolve_source(ref: str) -> Source:
    """In-repo id, local path, git URL, or remote copier template."""
    # An id, never a filesystem path: `RECIPES / <absolute path>` IS that path
    # under pathlib, so an absolute local template would masquerade as in-repo.
    if not Path(ref).is_absolute() and not ref.startswith("."):
        in_repo = RECIPES / ref
        if (in_repo / "copier.yml").is_file():
            return Source(ref, str(in_repo), REPO_ROOT, in_repo=True)
    if "://" in ref or ref.startswith(("gh:", "gl:", "git@")):
        return Source(ref, ref, None, in_repo=False)
    local = Path(ref).expanduser()
    if (local / "copier.yml").is_file() or (local / "copier.yaml").is_file():
        repo = local if (local / ".git").exists() else None
        return Source(ref, str(local), repo, in_repo=False)
    die(2, f"no such recipe: {ref} (not under recipes/, not a local template, not a URL)")


def recipe_config(source: Source) -> dict:
    path = Path(source.template)
    if not path.is_dir():
        return {}
    for name in ("copier.yml", "copier.yaml"):
        manifest = path / name
        if manifest.is_file():
            return yaml.safe_load(manifest.read_text()) or {}
    return {}


def scaffold_meta(config: dict) -> dict:
    meta = config.get("_scaffold") or {}
    return meta if isinstance(meta, dict) else {}


def answers_file_name(source: Source, config: dict) -> str:
    declared = config.get("_answers_file")
    if isinstance(declared, str) and "{{" not in declared:
        return declared
    return f".copier-answers.{source.name}.yml"


# --- copier --------------------------------------------------------------


def copier_copy(
    source: Source,
    dest: Path,
    data: dict,
    data_file: Path | None,
    pretend: bool = False,
    skip_tasks: bool = False,
    quiet: bool = False,
) -> subprocess.CompletedProcess:
    command = [
        sys.executable,
        "-m",
        "copier",
        "copy",
        "--trust",
        "--defaults",
        "--overwrite",
    ]
    for pattern in EXCLUDE:
        command += ["--exclude", pattern]
    if pretend:
        command.append("--pretend")
    if skip_tasks:
        command.append("--skip-tasks")
    if data_file is not None:
        command += ["--data-file", str(data_file)]
    for key, value in data.items():
        command += ["--data", f"{key}={value}"]
    command += [source.template, str(dest)]
    return subprocess.run(command, check=False, capture_output=quiet)


def check_binaries(source: Source, meta: dict) -> None:
    missing = [b for b in meta.get("requires_bin", []) if shutil.which(b) is None]
    if missing:
        die(3, f"{source.id} needs {', '.join(missing)} on PATH")


def run_precheck(source: Source, meta: dict, dest: Path) -> None:
    name = meta.get("precheck")
    if not name:
        return
    script = Path(source.template) / name
    if not script.is_file():
        die(3, f"{source.id} declares precheck {name!r}, which is absent")
    result = subprocess.run(
        [sys.executable, str(script), str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        die(3, f"{source.id} precheck refused: {detail}")


# --- profiles ------------------------------------------------------------


def load_profile(name: str) -> dict:
    path = PROFILES / f"{name}.yml"
    if not path.is_file():
        die(2, f"no such profile: {name}")
    return yaml.safe_load(path.read_text()) or {}


def recipe_exists(recipe: str) -> bool:
    return (RECIPES / recipe / "copier.yml").is_file()


def declared_after(recipe: str) -> list[str]:
    config = yaml.safe_load((RECIPES / recipe / "copier.yml").read_text()) or {}
    after = scaffold_meta(config).get("after") or []
    return [entry for entry in after if isinstance(entry, str)]


def matches(pattern: str, recipes: list[str]) -> list[str]:
    return [recipe for recipe in recipes if fnmatch.fnmatch(recipe, pattern)]


def contributes(recipe: str, directory: str) -> bool:
    return (RECIPES / recipe / "template" / directory).is_dir()


def exclusive_groups(recipes: list[str]) -> list[str]:
    """Two present recipes naming the same `_scaffold.exclusive_group`."""
    problems = []
    groups: dict[str, str] = {}
    for recipe in recipes:
        config = yaml.safe_load((RECIPES / recipe / "copier.yml").read_text()) or {}
        group = scaffold_meta(config).get("exclusive_group")
        if not group:
            continue
        if group in groups:
            problems.append(
                f"names both {groups[group]} and {recipe}, which declare exclusive_group {group!r}"
            )
        groups[group] = recipe
    return problems


def check_set(recipes: list[str]) -> list[str]:
    """Problems with a recipe list independent of any profile file."""
    problems: list[str] = []

    # Ordering. A recipe's own `after` is the authority, and a glob there
    # matches whatever the run selected: `lang/*` in host/github's list
    # means every language recipe the set names, not every one that exists.
    present = [recipe for recipe in recipes if recipe_exists(recipe)]
    position = {recipe: index for index, recipe in enumerate(present)}
    for recipe in present:
        for pattern in declared_after(recipe):
            for earlier in matches(pattern, present):
                if earlier == recipe:
                    continue
                if position[earlier] > position[recipe]:
                    problems.append(
                        f"puts {recipe} before {earlier}, but {recipe} declares `after: {pattern}`"
                    )

    problems += exclusive_groups(present)

    for recipe, needed in REQUIRES.items():
        if recipe not in present:
            continue
        for requirement in needed:
            if requirement not in present:
                problems.append(f"names {recipe}, which cannot work without {requirement}")

    # A recipe that contributes to an aggregated directory has to precede the
    # recipe that aggregates it, or the generated file is stale the moment the
    # render finishes. `after` cannot express this alone: workspace/just would
    # have to name every present and future contributor, and workspace/moon was
    # missed exactly that way -- rust-gui rendered clean and then failed
    # `just just-check`.
    for aggregator, directory in AGGREGATORS:
        if aggregator not in position:
            continue
        for recipe in present:
            if recipe == aggregator or not contributes(recipe, directory):
                continue
            if position[recipe] > position[aggregator]:
                problems.append(
                    f"renders {recipe} after {aggregator}, but it contributes a "
                    f"{directory} fragment that {aggregator} folds in"
                )

    # The monorepo axis. `workspace/monorepo` writes the root manifest that
    # every member resolves through, so a language recipe rendering first would
    # write into a repository that is not yet a workspace.
    if "workspace/monorepo" in present:
        root = position["workspace/monorepo"]
        for language in matches("lang/*", present):
            if position[language] < root:
                problems.append(
                    f"renders {language} before workspace/monorepo, so the member "
                    "glob does not exist yet"
                )

    return problems


def order_set(recipes: list[str]) -> list[str]:
    """A stable topological order for a recipe set nobody hand-ordered.

    Input order breaks ties, so a valid list passes through unchanged. Edges are
    the three ordering authorities `check_set` enforces: a recipe's `after`
    globs, fragment contributors before their aggregator, and workspace/monorepo
    before every language recipe.
    """
    present = [recipe for recipe in recipes if recipe_exists(recipe)]
    edges: dict[str, set[str]] = {recipe: set() for recipe in present}
    for recipe in present:
        for pattern in declared_after(recipe):
            for earlier in matches(pattern, present):
                if earlier != recipe:
                    edges[recipe].add(earlier)
    for aggregator, directory in AGGREGATORS:
        if aggregator not in edges:
            continue
        for recipe in present:
            if recipe != aggregator and contributes(recipe, directory):
                edges[aggregator].add(recipe)
    if "workspace/monorepo" in edges:
        for language in matches("lang/*", present):
            edges[language].add("workspace/monorepo")

    ordered = []
    remaining = list(present)
    while remaining:
        ready = next(
            (r for r in remaining if not (edges[r] & set(remaining))),
            None,
        )
        if ready is None:
            die(2, f"recipe ordering is cyclic: {', '.join(remaining)}")
        remaining.remove(ready)
        ordered.append(ready)
    return ordered + [recipe for recipe in recipes if not recipe_exists(recipe)]


def check_profile(path: Path) -> list[str]:
    """Every problem with one profile, so a run reports them together."""
    problems: list[str] = []
    try:
        profile = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        return [f"is not valid YAML: {exc}"]

    for key in REQUIRED_PROFILE_KEYS:
        if key not in profile:
            problems.append(f"has no `{key}`")
    if problems:
        return problems

    if profile["name"] != path.stem:
        problems.append(f"names itself {profile['name']!r} but the file is {path.stem!r}")

    recipes = profile["layers"]
    if not isinstance(recipes, list) or not recipes:
        return [*problems, "`layers` is empty"]

    for recipe in recipes:
        if not recipe_exists(recipe):
            problems.append(f"names {recipe}, which has no recipes/{recipe}/copier.yml")

    if not profile["build"]:
        problems.append("`build` is empty, so rendering it would prove nothing")

    problems += check_set(recipes)

    return problems


def dead_answers(path: Path) -> list[str]:
    """Profile answer keys no selected recipe declares as a question.

    A warning rather than a refusal: shared keys flow to many recipes
    legitimately, so the comparison is against the union of the selected
    recipes' questions -- anything outside that union is answered into the
    void. python_framework was exactly this: asked, recorded, read by nothing.
    """
    profile = yaml.safe_load(path.read_text()) or {}
    answers = profile.get("answers") or {}
    recipes = [r for r in profile.get("layers") or [] if recipe_exists(r)]
    declared: set[str] = set()
    for recipe in recipes:
        config = yaml.safe_load((RECIPES / recipe / "copier.yml").read_text()) or {}
        declared |= {k for k, v in config.items() if not k.startswith("_") and isinstance(v, dict)}
    return [
        f"answers `{key}`, which no selected recipe asks" for key in answers if key not in declared
    ]


# --- planning ------------------------------------------------------------


def is_fragment(path: str, merge_globs: list[str]) -> bool:
    if any(path.startswith(prefix) for prefix in FRAGMENT_DIRS):
        return True
    return any(fnmatch.fnmatch(path, pattern) for pattern in merge_globs)


def rendered_paths(source: Source, data: dict, data_file: Path | None) -> list[str]:
    """What one recipe writes, learned by rendering it into a scratch git repo.

    Rendering rather than parsing template filenames is what makes conditional
    and jinja-templated names exact.
    """
    with tempfile.TemporaryDirectory(prefix="scaffold-plan-") as scratch:
        scratch_path = Path(scratch)
        subprocess.run(["git", "init", "-q", str(scratch_path)], check=True)
        env_answers = scratch_path / ".plan-answers.yml"
        if data_file is not None:
            env_answers.write_text(data_file.read_text())
            merged = yaml.safe_load(env_answers.read_text()) or {}
        else:
            merged = {}
        merged.update(data)
        env_answers.write_text(yaml.safe_dump(merged))
        result = copier_copy(source, scratch_path, {}, env_answers, skip_tasks=True, quiet=True)
        if result.returncode != 0:
            die(4, f"copier failed rendering {source.id} for the plan")
        return sorted(
            str(p.relative_to(scratch_path))
            for p in scratch_path.rglob("*")
            if p.is_file()
            and ".git" not in p.relative_to(scratch_path).parts
            and p.name != ".plan-answers.yml"
        )


def build_plan(
    sources: list[Source],
    dest: Path,
    data: dict,
    data_file: Path | None,
) -> dict:
    """The full file map: every path, its writers, and its class.

    Classes:
      create     one owner, path absent from the destination
      overwrite  one owner, path present and different
      unchanged  one owner, path present, not compared (copier decides)
      skip       a later writer declares `_skip_if_exists`; the first owner wins
      fragment   under a fold directory; the aggregator merges it
      conflict   two owners and no declared resolution -- the plan refuses

    The map covers what the TEMPLATES write. A file the generator creates first
    (a `uv init` README) shifts create to skip at render time, and a file a task
    writes (LICENSE, the folded .gitignore) appears in no row at all -- tasks
    stay off in the plan's scratch renders because they reach the network.
    """
    writers: dict[str, list[str]] = {}
    skip_declared: dict[str, set[str]] = {}
    answer_files: set[str] = set()

    for source in sources:
        config = recipe_config(source)
        skips = {s for s in config.get("_skip_if_exists", []) if isinstance(s, str)}
        answer_files.add(answers_file_name(source, config))
        for path in rendered_paths(source, data, data_file):
            writers.setdefault(path, []).append(source.id)
            if any(fnmatch.fnmatch(path, pattern) for pattern in skips):
                skip_declared.setdefault(path, set()).add(source.id)

    entries = []
    conflicts = []
    for path, owners in sorted(writers.items()):
        merge_globs_any = []
        for source in sources:
            if source.id in owners:
                merge_globs_any += scaffold_meta(recipe_config(source)).get("merge", [])
        fragment = is_fragment(path, [g for g in merge_globs_any if isinstance(g, str)])
        if path in answer_files or path.startswith(".copier-answers."):
            klass = "answers"
        elif len(owners) == 1:
            if fragment:
                # One recipe's fold contribution; an aggregator merges the directory.
                klass = "fragment"
            elif (dest / path).exists():
                klass = "skip" if skip_declared.get(path) else "overwrite"
            else:
                klass = "create"
        elif fragment:
            # Two recipes writing the SAME fragment path is still a conflict.
            klass = "conflict"
        elif all(owner in skip_declared.get(path, set()) for owner in owners[1:]):
            # Everyone after the first declared _skip_if_exists: deterministic
            # first-writer-wins that both recipes opted into.
            klass = "skip"
        else:
            klass = "conflict"
        if klass == "conflict":
            conflicts.append({"path": path, "owners": owners})
        entries.append({"path": path, "owners": owners, "class": klass})

    return {"files": entries, "conflicts": conflicts}


def print_plan(plan: dict) -> None:
    width = max((len(e["path"]) for e in plan["files"]), default=4)
    for entry in plan["files"]:
        owners = ", ".join(entry["owners"])
        print(f"  {entry['class']:<9} {entry['path']:<{width}}  {owners}")
    if plan["conflicts"]:
        print("\nconflicts:", file=sys.stderr)
        for conflict in plan["conflicts"]:
            print(
                f"  {conflict['path']}: owned by {' and '.join(conflict['owners'])}",
                file=sys.stderr,
            )
        print(
            "\nrefusing: two recipes own the same file. Drop one, or declare\n"
            "`_skip_if_exists` in the later recipe so the first owner wins.",
            file=sys.stderr,
        )


# --- answers -------------------------------------------------------------


def required_questions(config: dict) -> list[str]:
    """Question keys with no default: the ones --defaults cannot fill."""
    gaps = []
    for key, spec in config.items():
        if key.startswith("_") or not isinstance(spec, dict):
            continue
        if "default" not in spec and spec.get("when") is not False:
            gaps.append(key)
    return gaps


def merge_provided(data: dict, data_file: Path | None) -> dict:
    provided = dict(data)
    if data_file is not None:
        provided.update(yaml.safe_load(data_file.read_text()) or {})
    return provided


def collect_gaps(
    sources: list[Source], data: dict, data_file: Path | None
) -> list[tuple[str, str]]:
    provided = merge_provided(data, data_file)
    gaps = []
    for source in sources:
        config = recipe_config(source)
        for key in required_questions(config):
            if key not in provided:
                gaps.append((source.id, key))
    return gaps


def invalid_answers(
    sources: list[Source], data: dict, data_file: Path | None
) -> list[tuple[str, str, str]]:
    """Provided answers a question's own `validator` refuses.

    Rendered the way copier renders them, so the refusal lands in the round
    that asked the question instead of surfacing later as a failed render.
    """
    import jinja2

    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, keep_trailing_newline=True)
    provided = merge_provided(data, data_file)
    problems = []
    for source in sources:
        for key, spec in recipe_config(source).items():
            if key.startswith("_") or not isinstance(spec, dict):
                continue
            if key not in provided or "validator" not in spec or spec.get("when") is False:
                continue
            # `--data key=[go]` arrives as a string; copier parses a yaml-typed
            # answer before validating, so the preflight parses it the same way.
            value = provided[key]
            if spec.get("type") == "yaml" and isinstance(value, str):
                try:
                    value = yaml.safe_load(value)
                except yaml.YAMLError:
                    problems.append((source.id, key, "not valid YAML"))
                    continue
            context = {**provided, key: value}
            message = env.from_string(spec["validator"]).render(context).strip()
            if message:
                problems.append((source.id, key, " ".join(message.split())))
    return problems


# --- rendering -----------------------------------------------------------


def git_commit(dest: Path, message: str) -> None:
    subprocess.run(["git", "-C", str(dest), "add", "-A"], check=False, capture_output=True)
    subprocess.run(
        ["git", "-C", str(dest), "commit", "-q", "-m", message],
        check=False,
        capture_output=True,
    )


def record_ref(source: Source, dest: Path, config: dict) -> None:
    """Write the rendered ref into the recipe's answers file.

    copier records `_commit` only when the template is a git repository root.
    An in-repo recipe is a subdirectory, so the CLI records the scaffold
    repository's HEAD under `_ref` instead; `update` reads it back.
    """
    head = source.head()
    if head is None:
        return
    answers_path = dest / answers_file_name(source, config)
    if not answers_path.is_file():
        return
    answers = yaml.safe_load(answers_path.read_text()) or {}
    answers["_ref"] = head
    answers["_source"] = source.id
    answers_path.write_text(yaml.safe_dump(answers, sort_keys=True))


def run_recipe_tasks(source: Source, dest: Path, answers: dict) -> None:
    """Run a recipe's own `_tasks` against the destination.

    `update` merges template output only, so files a task writes -- LICENSE, the
    folded .gitignore, a settled pin -- would otherwise sit still while _ref
    advances. Each command template renders the same way copier renders it, with
    the answers plus a `_copier_conf` carrying the source and destination paths.
    """
    config = recipe_config(source)
    tasks = [t for t in config.get("_tasks") or [] if isinstance(t, str)]
    if not tasks:
        return
    import jinja2

    env = jinja2.Environment(undefined=jinja2.ChainableUndefined, keep_trailing_newline=True)
    context = {
        **answers,
        "_copier_conf": {"src_path": source.template, "dst_path": str(dest)},
    }
    for template in tasks:
        command = " ".join(env.from_string(template).render(context).split())
        print(f"  task      {command}")
        result = subprocess.run(command, shell=True, cwd=dest, check=False)
        if result.returncode != 0:
            die(4, f"{source.id} task failed (exit {result.returncode}): {command}")


def render_one(
    source: Source,
    dest: Path,
    data: dict,
    data_file: Path | None,
    pretend: bool,
) -> None:
    config = recipe_config(source)
    meta = scaffold_meta(config)
    check_binaries(source, meta)
    run_precheck(source, meta, dest)
    result = copier_copy(source, dest, data, data_file, pretend=pretend)
    if result.returncode != 0:
        die(4, f"copier failed rendering {source.id} (exit {result.returncode})")
    if not pretend:
        record_ref(source, dest, config)


def demo_answers(profile: dict) -> dict:
    """Answers a profile build can use without an interview.

    A real render takes these from the agent; `check` and profile builds use
    these stand-ins.
    """
    name = profile["name"]
    return {
        "project_name": name.replace("-", "_"),
        "description": profile.get("summary", "A scaffolded project."),
        "org": "scaffold",
        "author": "Scaffold",
        "owner": "scaffold",
        "repo_url": "https://github.com/scaffold/demo",
        "default_branch": "main",
        "site_url": "https://scaffold.github.io/demo",
        "pages_repo": "scaffold/scaffold.github.io",
        "go_module_path": f"github.com/scaffold/{name}",
        "bd_prefix": "".join(c for c in name if c not in "aeiou-")[:3] or "prj",
        # local-only, because a render must not reach a remote.
        "bd_dolt_sync": "local-only",
        # embedded, so a throwaway render leaves no dolt server process behind.
        "bd_storage_mode": "embedded",
    }


def run_build(profile: dict, dest: Path) -> int:
    """Each command in the profile's own build, in the destination.

    Where the profile needs no generator, `just setup` runs first: the build
    commands assume the toolchain the fragments pin, and three real defects (a
    missing lockfile, a yaml-less python, a mise pin that cannot resolve)
    shipped because nothing exercised the fresh-clone handoff. A generator
    profile cannot run setup here -- its installs read manifests only the
    generator writes, and generators reach the network, which is why the
    render deliberately skips them; the skill flow and the end-to-end
    validation exercise that handoff instead. A setup failure counts as a
    build failure.
    """
    failures = 0
    commands = list(profile.get("build") or [])
    generatorless = (profile.get("generator") or "none") == "none"
    if generatorless and (dest / "justfile").is_file() and shutil.which("just") and commands:
        commands.insert(0, "just setup")
    for command in commands:
        binary = command.split()[0]
        if shutil.which(binary) is None:
            print(f"  skip  {command}  ({binary} absent)")
            continue
        result = subprocess.run(
            command, shell=True, cwd=dest, capture_output=True, text=True, check=False
        )
        if result.returncode == 0:
            print(f"  ok    {command}")
            continue
        failures += 1
        print(f"  FAIL  {command}  (exit {result.returncode})", file=sys.stderr)
        for line in (result.stdout + result.stderr).splitlines()[-25:]:
            print(f"        {line}", file=sys.stderr)
    return failures


# --- update --------------------------------------------------------------


def render_at_ref(source: Source, ref: str, data_file: Path, out: Path) -> None:
    """Render an in-repo or local-git recipe as it was at `ref`."""
    assert source.repo is not None
    with tempfile.TemporaryDirectory(prefix="scaffold-old-") as worktree:
        old = Path(worktree) / "src"
        subprocess.run(
            ["git", "-C", str(source.repo), "worktree", "add", "--detach", str(old), ref],
            check=True,
            capture_output=True,
        )
        try:
            rel = Path(source.template).resolve().relative_to(source.repo.resolve())
            old_source = Source(source.id, str(old / rel), None, in_repo=False)
            subprocess.run(["git", "init", "-q", str(out)], check=True)
            # Tasks stay off in a scratch render: they reach the network and
            # mutate state (bd init, gh fetches, bun installs), and the 3-way
            # merge compares template output only -- task-written files are the
            # destination's own and are refolded there after the update.
            result = copier_copy(old_source, out, {}, data_file, skip_tasks=True)
            if result.returncode != 0:
                die(4, f"copier failed rendering {source.id} at {ref[:12]}")
        finally:
            subprocess.run(
                ["git", "-C", str(source.repo), "worktree", "remove", "--force", str(old)],
                check=False,
                capture_output=True,
            )


def merge_file(dest_file: Path, old_file: Path, new_file: Path) -> str:
    """3-way merge new template output over local drift. Returns the outcome."""
    for path in (old_file, new_file):
        if not path.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.touch()
    if not dest_file.exists():
        dest_file.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(new_file, dest_file)
        return "created"
    result = subprocess.run(
        [
            "git",
            "merge-file",
            "-L",
            "local",
            "-L",
            "base",
            "-L",
            "updated",
            str(dest_file),
            str(old_file),
            str(new_file),
        ],
        capture_output=True,
        check=False,
    )
    return "conflict" if result.returncode != 0 else "merged"


def update_recipe(source: Source, dest: Path, data: dict) -> int:
    """Re-render at HEAD and 3-way merge against what the recorded ref produced.

    Local hand edits survive where they do not overlap a template change;
    a true overlap gets standard conflict markers and a nonzero exit.
    """
    config = recipe_config(source)
    answers_path = dest / answers_file_name(source, config)
    if not answers_path.is_file():
        die(2, f"{dest} has no {answers_path.name}; render {source.id} first")
    answers = yaml.safe_load(answers_path.read_text()) or {}
    ref = answers.get("_ref") or answers.get("_commit")
    if not ref:
        die(2, f"{answers_path.name} records no _ref; re-render instead")
    if source.repo is None:
        die(2, f"{source.id} has no git checkout to replay {ref[:12]} from")

    recorded = {k: v for k, v in answers.items() if not k.startswith("_")}
    merged = {**recorded, **data}

    conflicts = 0
    touched_fragments: set[str] = set()
    with tempfile.TemporaryDirectory(prefix="scaffold-update-") as scratch:
        base = Path(scratch) / "base"
        new = Path(scratch) / "new"
        # The base replays the RECORDED answers; only the new render sees --data.
        # An answer change then surfaces as a template-side diff and 3-way merges
        # like any other, instead of matching the base and losing to the dest.
        base_answers = Path(scratch) / "answers-base.yml"
        base_answers.write_text(yaml.safe_dump(recorded))
        new_answers = Path(scratch) / "answers-new.yml"
        new_answers.write_text(yaml.safe_dump(merged))
        base.mkdir()
        new.mkdir()
        render_at_ref(source, ref, base_answers, base)
        subprocess.run(["git", "init", "-q", str(new)], check=True)
        result = copier_copy(source, new, {}, new_answers, skip_tasks=True)
        if result.returncode != 0:
            die(4, f"copier failed rendering {source.id} at HEAD")

        paths = {
            str(p.relative_to(root))
            for root in (base, new)
            for p in root.rglob("*")
            if p.is_file() and ".git" not in p.relative_to(root).parts
        }
        answer_rels: list[str] = []
        for rel in sorted(paths):
            if Path(rel).name.startswith(".copier-answers."):
                # The CLI owns the answers file; a 3-way merge of YAML mangles
                # it. Applied after the loop, and only when the update landed.
                answer_rels.append(rel)
                continue
            outcome = merge_file(dest / rel, base / rel, new / rel)
            if outcome == "conflict":
                conflicts += 1
                print(f"  CONFLICT  {rel}", file=sys.stderr)
            else:
                print(f"  {outcome:<9} {rel}")
            if any(rel.startswith(prefix) for prefix in FRAGMENT_DIRS):
                touched_fragments.add(rel.split("/", 1)[0])

        if conflicts == 0:
            # Task-written files -- LICENSE, the folded .gitignore -- exist in
            # no scratch render (tasks stay off there), so the merge above never
            # moves them. Every recipe's tasks are idempotent, so the dest runs
            # them once against the refreshed answers and the outputs catch up.
            # Tasks FIRST: a task failure exits 4 with the answers file and
            # _ref both unmoved -- the same not-applied invariant a conflict
            # gets -- so the re-run replays everything, including the tasks.
            run_recipe_tasks(source, dest, merged)
            for rel in answer_rels:
                shutil.copyfile(new / rel, dest / rel)
                print(f"  answers   {rel}")

    if conflicts == 0:
        record_ref(source, dest, config)
    else:
        # The answers file and _ref stay where they were: a conflicted update
        # is not applied. Resolve the markers, commit, and re-run -- the
        # resolved side matches the new render, so the replay merges clean and
        # only then advances the ref.
        print(f"note: {source.id} keeps its recorded _ref until the conflicts resolve")
    for aggregator, directory in AGGREGATORS:
        if directory in touched_fragments:
            print(f"note: {directory} changed; re-run the {aggregator} fold")
    return conflicts


# --- commands ------------------------------------------------------------


def parse_data(pairs: list[str]) -> dict:
    data = {}
    for pair in pairs:
        if "=" not in pair:
            die(2, f"--data takes key=value, got {pair!r}")
        key, value = pair.split("=", 1)
        data[key] = value
    return data


def select_sources(args: argparse.Namespace) -> tuple[list[Source], dict | None]:
    """The recipe set: a profile's, the ones named, or the union of both.

    With `--profile` alone the profile's order is the order. Positional recipes
    union into a profile's set, placed by `order_set`, and the result must pass
    `check_set` -- reordering fixes position, not absence, so a REQUIRES or
    exclusive-group problem refuses. A positional set with no profile is the
    user's own order: problems print as warnings and the set runs as named.
    """
    if args.profile:
        profile = load_profile(args.profile)
        recipes = list(profile["layers"])
        extras = [recipe for recipe in args.recipes if recipe not in recipes]
        if extras:
            recipes = order_set(recipes + extras)
            problems = check_set(recipes)
            if problems:
                die(2, "; ".join(problems))
        return [resolve_source(recipe) for recipe in recipes], profile
    if not args.recipes:
        die(2, "name recipes or pass --profile")
    for problem in check_set(args.recipes):
        print(f"warning: {problem}", file=sys.stderr)
    return [resolve_source(recipe) for recipe in args.recipes], None


def cmd_list(args: argparse.Namespace) -> int:
    print("recipes:")
    for manifest in sorted(RECIPES.glob("*/*/copier.yml")):
        recipe = manifest.parent.relative_to(RECIPES)
        config = yaml.safe_load(manifest.read_text()) or {}
        summary = str(scaffold_meta(config).get("summary", "")).strip().split("\n")[0]
        print(f"  {recipe!s:<24} {summary}")
    print("\nprofiles:")
    for path in sorted(PROFILES.glob("*.yml")):
        profile = yaml.safe_load(path.read_text()) or {}
        print(f"  {path.stem:<24} {profile.get('summary', '')}")
    return 0


def cmd_check(args: argparse.Namespace) -> int:
    failures = 0
    paths = (
        [PROFILES / f"{name}.yml" for name in args.profiles]
        if args.profiles
        else sorted(PROFILES.glob("*.yml"))
    )
    warnings = 0
    for path in paths:
        problems = check_profile(path)
        if problems:
            failures += 1
            for problem in problems:
                print(f"{path.stem}: {problem}", file=sys.stderr)
            continue
        for warning in dead_answers(path):
            warnings += 1
            print(f"{path.stem}: warning: {warning}", file=sys.stderr)
    if failures:
        return 1
    print(f"ok: {len(paths)} profile(s)" + (f", {warnings} warning(s)" if warnings else ""))
    return 0


def cmd_plan(args: argparse.Namespace) -> int:
    sources, profile = select_sources(args)
    data = parse_data(args.data)
    if profile is not None:
        merged = demo_answers(profile) if args.demo else {}
        merged.update(profile.get("answers") or {})
        merged.update(data)
        data = merged
    plan = build_plan(sources, args.dest, data, args.data_file)
    if args.json:
        print(json.dumps(plan, indent=2))
    else:
        print_plan(plan)
    return 5 if plan["conflicts"] else 0


def cmd_render(args: argparse.Namespace) -> int:
    sources, profile = select_sources(args)
    data = parse_data(args.data)
    if profile is not None:
        merged = demo_answers(profile) if args.demo else {}
        merged.update(profile.get("answers") or {})
        merged.update(data)
        data = merged

    if not args.force and not args.pretend and len(sources) > 1:
        plan = build_plan(sources, args.dest, data, args.data_file)
        if plan["conflicts"]:
            print_plan(plan)
            return 5

    dest = args.dest
    if not args.pretend and not (dest / ".git").exists():
        dest.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", str(dest)], check=True)

    if not args.pretend and args.commit and (dest / ".git").exists():
        # The CLI's own commits must not depend on ambient identity: a CI
        # runner has none, and `git commit` there exits 128. Set only where
        # unset -- `--get` sees global config, so a configured user keeps theirs.
        for key, value in (("user.email", "scaffold@example.com"), ("user.name", "Scaffold")):
            if subprocess.run(
                ["git", "-C", str(dest), "config", "--get", key],
                capture_output=True,
                check=False,
            ).returncode:
                subprocess.run(["git", "-C", str(dest), "config", key, value], check=True)
        # The generator ran before the render and its output sits uncommitted --
        # base/repo's precheck would refuse it, and rightly: copier overwrites
        # with no diff to review. A baseline commit IS that diff, so the first
        # recipe's change is reviewable against exactly what the generator made.
        git_commit(dest, "chore: pre-render tree")

    for source in sources:
        render_one(source, dest, data, args.data_file, args.pretend)
        print(f"  ok    render {source.id}")
        if not args.pretend and args.commit:
            # base/repo's precheck refuses a destination with uncommitted
            # changes: copier overwrites and leaves no diff to review.
            git_commit(dest, f"chore: render {source.id}")

    if profile is not None and args.build:
        failures = run_build(profile, dest)
        if failures:
            print(f"\n{profile['name']}: {failures} build command(s) failed", file=sys.stderr)
            return 1
    return 0


def cmd_check_answers(args: argparse.Namespace) -> int:
    sources, profile = select_sources(args)
    data = parse_data(args.data)
    if profile is not None:
        data = {**(profile.get("answers") or {}), **data}
    gaps = collect_gaps(sources, data, args.data_file)
    invalid = invalid_answers(sources, data, args.data_file)
    if not gaps and not invalid:
        print("answers complete")
        return 0
    for recipe, key in gaps:
        print(f"Provide a value for {key!r} in recipe {recipe!r}", file=sys.stderr)
    for recipe, key, message in invalid:
        print(f"Invalid value for {key!r} in recipe {recipe!r}: {message}", file=sys.stderr)
    return 1


def cmd_update(args: argparse.Namespace) -> int:
    data = parse_data(args.data)
    conflicts = 0
    for ref in args.recipes:
        source = resolve_source(ref)
        print(f"update {source.id}:")
        conflicts += update_recipe(source, args.dest, data)
    if conflicts:
        print(
            f"\n{conflicts} file(s) carry conflict markers; resolve, then commit.",
            file=sys.stderr,
        )
        return 5
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="scaffold", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="recipes and profiles")

    check = sub.add_parser("check", help="validate profiles against recipes/")
    check.add_argument("profiles", nargs="*")

    def common(p: argparse.ArgumentParser, dest_required: bool = True) -> None:
        p.add_argument("recipes", nargs="*", help="recipe ids, paths, or URLs")
        p.add_argument(
            "--profile",
            help="take the recipe set from a profile; positional recipes union in, "
            "ordered by their declared `after`",
        )
        p.add_argument("--dest", type=Path, required=dest_required)
        p.add_argument("--data", action="append", default=[], metavar="KEY=VALUE")
        p.add_argument("--data-file", type=Path, help="YAML file of answers")

    plan = sub.add_parser("plan", help="the file map, writing nothing")
    common(plan)
    plan.add_argument("--json", action="store_true")
    plan.add_argument("--demo", action="store_true", help="fill interview answers with stand-ins")

    render = sub.add_parser("render", help="render recipes into a destination")
    common(render)
    render.add_argument("--pretend", action="store_true", help="list writes, writing nothing")
    render.add_argument("--force", action="store_true", help="render despite plan conflicts")
    render.add_argument("--no-commit", dest="commit", action="store_false")
    render.add_argument("--build", action="store_true", help="run the profile's build commands")
    render.add_argument("--demo", action="store_true", help="fill interview answers with stand-ins")

    answers = sub.add_parser("check-answers", help="every missing required answer at once")
    common(answers, dest_required=False)

    update = sub.add_parser("update", help="re-render at HEAD and 3-way merge drift")
    update.add_argument("recipes", nargs="+")
    update.add_argument("--dest", type=Path, required=True)
    update.add_argument("--data", action="append", default=[], metavar="KEY=VALUE")

    args = parser.parse_args()

    # plan, render, and check-answers all take --data-file, and all three would otherwise
    # hand a mistyped path to copier, which reports it as its own failure: exit 4, with a
    # copier traceback, for what is a usage error.
    data_file = getattr(args, "data_file", None)
    if data_file is not None and not data_file.is_file():
        die(2, f"no such data file: {data_file}")

    handlers = {
        "list": cmd_list,
        "check": cmd_check,
        "plan": cmd_plan,
        "render": cmd_render,
        "check-answers": cmd_check_answers,
        "update": cmd_update,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
