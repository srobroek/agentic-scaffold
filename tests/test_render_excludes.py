"""render.py excludes editor and filesystem artifacts from every layer.

copier 9.17.0 stops applying its own DEFAULT_EXCLUDE once `_subdirectory` is set,
and every layer here sets it. These tests pin the workaround, because the failure
is invisible twice over: `.DS_Store` is gitignored, so a template carrying one
shows nothing in `git status`, and the file only appears in a rendered project.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"
TEMPLATES = REPO_ROOT / "templates"


def load_render():
    """Import render.py as a module so TEMPLATES can be pointed at a probe tree."""
    spec = importlib.util.spec_from_file_location("render_under_test", RENDER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_no_template_carries_a_filesystem_artifact() -> None:
    """The artifact is gitignored, so nothing else in the suite would report it."""
    junk = sorted(
        str(p.relative_to(TEMPLATES))
        for pattern in (".DS_Store", "._*", "Thumbs.db")
        for p in TEMPLATES.rglob(pattern)
    )
    assert not junk, f"filesystem artifacts under templates/: {junk}"


@pytest.mark.parametrize("artifact", [".DS_Store", "._resource", "__pycache__/stale.pyc"])
def test_an_artifact_in_a_template_is_not_rendered(artifact: str, tmp_path: Path) -> None:
    """A layer sets `_subdirectory`, which is what disables copier's own default."""
    layer = tmp_path / "templates" / "probe" / "artifact"
    template = layer / "template" / "nested"
    template.mkdir(parents=True)
    (layer / "copier.yml").write_text("_subdirectory: template\n")
    (template / "keep.txt").write_text("kept\n")

    planted = template / artifact
    planted.parent.mkdir(parents=True, exist_ok=True)
    planted.write_bytes(b"junk\n")

    dest = tmp_path / "dest"
    dest.mkdir()

    # render.py resolves layers against its own repo root, so the probe layer is
    # reached by pointing that constant at the temporary tree.
    module = load_render()
    module.TEMPLATES = tmp_path / "templates"
    module.render("probe/artifact", dest, None, pretend=False)

    assert (dest / "nested" / "keep.txt").is_file()
    assert not (dest / "nested" / artifact).exists()
