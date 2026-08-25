"""The CLI excludes editor and filesystem artifacts from every recipe.

copier 9.17.0 stops applying its own DEFAULT_EXCLUDE once `_subdirectory` is set,
and every recipe here sets it. These tests pin the workaround, because the failure
is invisible twice over: `.DS_Store` is gitignored, so a template carrying one
shows nothing in `git status`, and the file only appears in a rendered project.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from conftest import render_recipe

REPO_ROOT = Path(__file__).resolve().parent.parent
RECIPES = REPO_ROOT / "recipes"


def test_no_template_carries_a_filesystem_artifact() -> None:
    """The artifact is gitignored, so nothing else in the suite would report it."""
    junk = sorted(
        str(p.relative_to(RECIPES))
        for pattern in (".DS_Store", "._*", "Thumbs.db")
        for p in RECIPES.rglob(pattern)
    )
    assert not junk, f"filesystem artifacts under recipes/: {junk}"


@pytest.mark.parametrize("artifact", [".DS_Store", "._resource", "__pycache__/stale.pyc"])
def test_an_artifact_in_a_template_is_not_rendered(artifact: str, tmp_path: Path) -> None:
    """A recipe sets `_subdirectory`, which is what disables copier's own default.

    The probe recipe is a local directory rather than an entry under recipes/, because
    `resolve_source` takes a path as readily as an in-repo id: one interface, and no
    fixture written into the real catalog.
    """
    recipe = tmp_path / "probe"
    template = recipe / "template" / "nested"
    template.mkdir(parents=True)
    (recipe / "copier.yml").write_text("_subdirectory: template\n")
    (template / "keep.txt").write_text("kept\n")

    planted = template / artifact
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_bytes(b"junk\n")

    dest = tmp_path / "dest"
    dest.mkdir()

    result = render_recipe(str(recipe), dest)

    assert result.returncode == 0, result.stderr
    assert (dest / "nested" / "keep.txt").is_file()
    assert not (dest / "nested" / artifact).exists()
