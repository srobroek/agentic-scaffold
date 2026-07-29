"""The three base layers: license, repo, gitignore."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"
VENDORED = REPO_ROOT / "templates" / "base" / "license" / "licenses"


def render(layer: str, dest: Path, answers: str) -> subprocess.CompletedProcess[str]:
    answers_file = dest.parent / f"{dest.name}-answers.yml"
    answers_file.write_text(answers)
    return subprocess.run(
        [sys.executable, str(RENDER), layer, str(dest), "--answers", str(answers_file)],
        capture_output=True,
        text=True,
        check=False,
    )


def git_init(path: Path) -> None:
    subprocess.run(["git", "init", "-q", str(path)], check=True)


# --- base/license ----------------------------------------------------------


@pytest.mark.parametrize("spdx", ["Apache-2.0", "MPL-2.0", "AGPL-3.0-only"])
def test_the_policy_licences_need_no_network(spdx: str, tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, f'license: {spdx}\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 0, result.stderr
    assert "(vendored)" in result.stdout
    assert (dest / "LICENSE").is_file()


def test_licence_id_matching_is_case_insensitive(tmp_path: Path) -> None:
    """An SPDX id is case-sensitive; an answer typed by hand is not."""
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, 'license: mpl-2.0\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 0, result.stderr
    assert "Mozilla Public License" in (dest / "LICENSE").read_text()


def test_an_unknown_identifier_fails_without_writing(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, 'license: NotReal\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 4
    assert not (dest / "LICENSE").exists()
    # The message must name what is available offline.
    assert "Apache-2.0" in result.stdout + result.stderr


def test_licence_none_writes_nothing(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, 'license: none\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 0
    assert not (dest / "LICENSE").exists()


def test_the_vendored_set_matches_the_documented_policy() -> None:
    assert {p.stem for p in VENDORED.glob("*.txt")} == {
        "Apache-2.0",
        "MPL-2.0",
        "AGPL-3.0-only",
    }


# --- base/repo -------------------------------------------------------------


def test_repo_layer_writes_the_skeleton(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("base/repo", dest, "project_name: demo\ndescription: A demo\norg: acme\n")
    assert result.returncode == 0, result.stderr
    for expected in ("README.md", ".editorconfig", ".gitattributes"):
        assert (dest / expected).is_file()
    assert "# demo" in (dest / "README.md").read_text()


def test_repo_layer_leaves_docs_contents_alone(tmp_path: Path) -> None:
    """docs/agents and docs/adr own their subtrees; base/repo only makes docs/."""
    dest = tmp_path / "d"
    dest.mkdir()
    render("base/repo", dest, "project_name: demo\n")
    assert (dest / "docs").is_dir()
    assert not (dest / "docs" / "agents").exists()


def test_precheck_refuses_a_dirty_destination(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    git_init(dest)
    (dest / "dirty.txt").write_text("uncommitted\n")

    result = render("base/repo", dest, "project_name: demo\n")

    assert result.returncode == 3
    assert "uncommitted changes" in result.stderr


# --- base/gitignore --------------------------------------------------------


def test_gitignore_always_ignores_generated_output(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("base/gitignore", dest, 'gitnr_templates: ""\n')
    assert result.returncode == 0, result.stderr
    body = (dest / ".gitignore").read_text()
    assert "repomix.xml" in body
    assert ".claude/skills/repomix-*/" in body


def test_gitignore_folds_the_fragments(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    (dest / ".gitignore.d").mkdir()
    (dest / ".gitignore.d" / "rust").write_text("/target\nCargo.lock\n")

    result = render("base/gitignore", dest, 'gitnr_templates: ""\n')

    assert result.returncode == 0
    body = (dest / ".gitignore").read_text()
    assert "/target" in body
    assert "# rust" in body


def test_a_fragment_with_its_own_comment_is_not_double_headed(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    (dest / ".gitignore.d").mkdir()
    (dest / ".gitignore.d" / "beads").write_text("# beads\n.beads/dolt/\n")

    render("base/gitignore", dest, 'gitnr_templates: ""\n')

    assert (dest / ".gitignore").read_text().count("# beads") == 1


def test_gitignore_is_rebuilt_identically(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    (dest / ".gitignore.d").mkdir()
    (dest / ".gitignore.d" / "rust").write_text("/target\n")

    render("base/gitignore", dest, 'gitnr_templates: ""\n')
    first = (dest / ".gitignore").read_text()
    render("base/gitignore", dest, 'gitnr_templates: ""\n')

    assert (dest / ".gitignore").read_text() == first
