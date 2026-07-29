"""agentic/index: the repomix config, and the artefacts it must ignore.

Every claim asserted here was measured on 2026-07-29 with repomix 1.17.0.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tomllib
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

ANSWERS = 'index_languages:\n  - "**/*.py"\n  - "**/*.md"\nindex_extra_ignores: []\n'


def render(layer: str, dest: Path, answers: str) -> subprocess.CompletedProcess[str]:
    answers_file = dest.parent / f"{dest.name}-answers.yml"
    answers_file.write_text(answers)
    return subprocess.run(
        [sys.executable, str(RENDER), layer, str(dest), "--answers", str(answers_file)],
        capture_output=True,
        text=True,
        check=False,
    )


def config_of(dest: Path) -> dict:
    return json.loads((dest / "repomix.config.json").read_text())


def test_the_config_is_valid_json(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("agentic/index", dest, ANSWERS)
    assert result.returncode == 0, result.stderr
    assert config_of(dest)["include"] == ["**/*.py", "**/*.md"]


def test_one_artefact_carries_the_contents(tmp_path: Path) -> None:
    """One pack, searched. `rg` over it lists every path in 0.009s and finds one in
    0.010s, so a separate metadata-only map earns nothing.

    Keeping one also removes repomix's `--no-files` trap: there is no `--files`, so a
    config carrying `files: false` cannot be overridden from the command line, and a
    recipe pointing at it produces a metadata-only pack while calling itself full.
    """
    dest = tmp_path / "d"
    dest.mkdir()
    render("agentic/index", dest, ANSWERS)
    output = config_of(dest)["output"]
    assert output["filePath"] == "repomix-full.xml"
    # `files: false` is what would make the pack metadata-only, unoverridably.
    assert output.get("files") is not False


def test_extra_ignores_are_appended(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    render(
        "agentic/index",
        dest,
        ANSWERS.replace("index_extra_ignores: []", 'index_extra_ignores:\n  - "**/vendor/**"'),
    )
    patterns = config_of(dest)["ignore"]["customPatterns"]
    assert "**/vendor/**" in patterns
    assert "**/CHANGELOG.md" in patterns


def test_the_config_ignores_every_index_artefact(tmp_path: Path) -> None:
    """An unignored artefact is packed into the next one: 38 percent of one pack."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("agentic/index", dest, ANSWERS)
    patterns = config_of(dest)["ignore"]["customPatterns"]
    for artefact in ("**/graphify-out/**", "**/.serena/**", "**/repomix*.xml"):
        assert artefact in patterns


def test_the_gitignore_fragment_covers_repomix_default_names(tmp_path: Path) -> None:
    """repomix writes repomix-output.* when --output is omitted."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("agentic/index", dest, ANSWERS)
    body = (dest / ".gitignore.d" / "index").read_text()
    for name in (
        "repomix-full.xml",
        "graphify-out/",
        ".serena/",
        "/repomix-output.xml",
        "/repomix-output.md",
        "/repomix-output.txt",
    ):
        assert name in body


def test_no_second_config_is_written(tmp_path: Path) -> None:
    """Two configs need a test asserting their filters match, or the pack indexes what
    the map hides. One artefact removes the class of bug."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("agentic/index", dest, ANSWERS)

    assert not (dest / "repomix-full.config.json").exists()
    assert sorted(p.name for p in dest.glob("repomix*.json")) == ["repomix.config.json"]


def test_the_recipes_search_the_pack_rather_than_read_it(tmp_path: Path) -> None:
    """A pack of a 4,107-file repository is 6.3 million tokens, roughly six context
    windows, so reading it cannot succeed. Searching it is 0.010s."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("agentic/index", dest, ANSWERS)
    body = (dest / ".just.d" / "index.just").read_text()

    # Bare `repomix` reads repomix.config.json, so the recipe is identical everywhere
    # while the patterns differ per repository.
    assert "\n    repomix\n" in body
    assert "rg -o" in body
    # `</file>` is self-delimiting, which is why the extract works on xml.
    assert "awk" in body


# --- the worktrunk side ----------------------------------------------------

WT_ANSWERS = (
    'forge_platform: github\nforge_hostname: ""\nsetup_command: "just setup"\n'
    "dev_server: false\nworktree_includes: []\n"
)


def test_worktrunk_config_is_valid_toml_both_ways(tmp_path: Path) -> None:
    for name, answers in (
        ("plain", WT_ANSWERS),
        ("dev", WT_ANSWERS.replace("dev_server: false", 'dev_server: true\ndev_command: "just dev"')),
    ):
        dest = tmp_path / name
        dest.mkdir()
        result = render("workspace/worktrunk", dest, answers)
        assert result.returncode == 0, result.stderr
        tomllib.loads((dest / ".config" / "wt.toml").read_text())


def test_the_pack_and_graph_are_copied_into_a_worktree(tmp_path: Path) -> None:
    """Copying beats rebuilding on both: 1.3 to 3.2s for the pack, 6.9s for the graph.

    Neither holds an absolute path, so a copy is valid in any checkout.
    """
    dest = tmp_path / "d"
    dest.mkdir()
    render("workspace/worktrunk", dest, WT_ANSWERS)
    body = (dest / ".worktreeinclude").read_text()
    assert "repomix-full.xml" in body
    assert "graphify-out/" in body


def test_post_start_refreshes_the_pack(tmp_path: Path) -> None:
    """No staleness gate: a pack is 1.3 to 3.2s, repomix has no cache, and post-start
    runs once per worktree, so deferring amortises nothing."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("workspace/worktrunk", dest, WT_ANSWERS)
    config = tomllib.loads((dest / ".config" / "wt.toml").read_text())
    assert config["post-start"]["repomix"] == "repomix"
