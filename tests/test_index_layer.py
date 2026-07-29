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

ANSWERS = 'index_languages:\n  - "**/*.py"\n  - "**/*.md"\nindex_full_pack: false\nindex_extra_ignores: []\n'


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


def test_the_map_omits_file_contents(tmp_path: Path) -> None:
    """A map is 20 thousand tokens against the full pack's 6.3 million."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("agentic/index", dest, ANSWERS)
    output = config_of(dest)["output"]
    assert output["files"] is False
    assert output["filePath"] == "repomix-map.xml"


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
        "repomix-map.xml",
        "graphify-out/",
        ".serena/",
        "/repomix-output.xml",
        "/repomix-output.md",
        "/repomix-output.txt",
    ):
        assert name in body


def test_the_full_pack_is_opt_in(tmp_path: Path) -> None:
    off = tmp_path / "off"
    off.mkdir()
    render("agentic/index", off, ANSWERS)
    assert "repomix-full.xml" not in (off / ".gitignore.d" / "index").read_text()

    on = tmp_path / "on"
    on.mkdir()
    render("agentic/index", on, ANSWERS.replace("index_full_pack: false", "index_full_pack: true"))
    assert "repomix-full.xml" in (on / ".gitignore.d" / "index").read_text()


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


def test_the_map_and_graph_are_copied_into_a_worktree(tmp_path: Path) -> None:
    """Copying beats rebuilding: 82KB against 1.3s, 9.9MB against 6.9s."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("workspace/worktrunk", dest, WT_ANSWERS)
    body = (dest / ".worktreeinclude").read_text()
    assert "repomix-map.xml" in body
    assert "graphify-out/" in body


def test_post_start_refreshes_the_map(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    render("workspace/worktrunk", dest, WT_ANSWERS)
    config = tomllib.loads((dest / ".config" / "wt.toml").read_text())
    assert config["post-start"]["repomix-map"] == "repomix"
