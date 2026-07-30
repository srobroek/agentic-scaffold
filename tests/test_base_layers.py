"""The three base layers: license, repo, gitignore."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"


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
def test_the_policy_licences_resolve(spdx: str, tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, f'license: {spdx}\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 0, result.stderr
    assert (dest / "LICENSE").is_file()


def test_agpl_only_maps_to_the_github_key(tmp_path: Path) -> None:
    """SPDX separates -only from -or-later; GitHub carries one key for both."""
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, 'license: AGPL-3.0-only\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 0, result.stderr
    assert "AFFERO" in (dest / "LICENSE").read_text().upper()


def test_licence_id_matching_is_case_insensitive(tmp_path: Path) -> None:
    """GitHub keys are lowercase; an answer typed by hand may not be."""
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, 'license: mpl-2.0\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 0, result.stderr
    assert "Mozilla Public License" in (dest / "LICENSE").read_text()


def test_the_holder_and_year_are_substituted(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    render("base/license", dest, 'license: MIT\ncopyright_name: Acme Ltd\ncopyright_year: "2031"\n')
    body = (dest / "LICENSE").read_text()
    assert "Acme Ltd" in body
    assert "2031" in body
    assert "[fullname]" not in body


def test_an_unknown_identifier_fails_without_writing(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, 'license: NotReal\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 4
    assert not (dest / "LICENSE").exists()
    # The message must list what GitHub carries.
    assert "Apache-2.0" in result.stdout + result.stderr


def test_licence_none_writes_nothing(tmp_path: Path) -> None:
    dest = tmp_path / "d"
    dest.mkdir()
    result = render(
        "base/license", dest, 'license: none\ncopyright_name: X\ncopyright_year: "2026"\n'
    )
    assert result.returncode == 0
    assert not (dest / "LICENSE").exists()


def test_no_licence_text_is_vendored() -> None:
    """gh api is the source; a copy in the repository would drift from it."""
    layer = REPO_ROOT / "templates" / "base" / "license"
    assert not (layer / "licenses").exists()


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


@pytest.mark.parametrize(
    ("artifact", "written_by"),
    [
        (".DS_Store", "Finder, into any directory it displays"),
        ("._*", "macOS, as a resource fork"),
        ("Thumbs.db", "the Windows thumbnail cache"),
        ("*~", "a Linux editor, as a backup file"),
    ],
)
def test_gitignore_covers_the_os_artifacts_with_no_language_layer(
    artifact: str, written_by: str, tmp_path: Path
) -> None:
    """The OS writes these whatever the project is, so no derived list gates them.

    A docs-only repository renders no language layer at all, and one of these files
    still reached a template directory in this repository. They come from gitnr's
    three Global templates rather than a hand-rolled list here.
    """
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("base/gitignore", dest, 'gitnr_templates: ""\n')
    assert result.returncode == 0, result.stderr
    assert artifact in (dest / ".gitignore").read_text(), (
        f"{artifact} is unignored, though it is written by {written_by}"
    )


def test_a_pattern_holding_a_carriage_return_survives(tmp_path: Path) -> None:
    """GitHub's macOS template carries `Icon[\\r]`, a filename with a literal CR.

    Reading gitnr's output with `text=True` enables universal newlines, which rewrites
    that CR to LF and splits the pattern across two lines. What is left, `Icon[`, is an
    unterminated character class, and every tool that reads .gitignore errors on it:
    zizmor exited 1 with "error parsing glob 'Icon['" while auditing workflows.
    """
    dest = tmp_path / "d"
    dest.mkdir()
    result = render("base/gitignore", dest, 'gitnr_templates: ""\n')
    assert result.returncode == 0, result.stderr

    raw = (dest / ".gitignore").read_bytes()
    assert b"Icon[\r]" in raw, "the CR was translated, splitting the pattern"
    # The truncated form is what a tool chokes on.
    assert b"Icon[\n" not in raw


def test_gitignore_leaves_editor_directories_to_the_developer(tmp_path: Path) -> None:
    """`.vscode/` and `.idea/` follow the developer, not the project.

    They belong in a global `core.excludesFile`; ignoring them here would impose one
    editor's layout on every repository this scaffolds.
    """
    dest = tmp_path / "d"
    dest.mkdir()
    render("base/gitignore", dest, 'gitnr_templates: ""\n')
    body = (dest / ".gitignore").read_text()
    assert ".vscode/" not in body
    assert ".idea/" not in body


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
