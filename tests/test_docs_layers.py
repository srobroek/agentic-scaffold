"""docs/*: the site, the decision records, and what each engine needs."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

SITE_ANSWERS = """\
project_name: Demo
description: A demo site
site_url: "https://owner.github.io/repo"
docs_engine: starlight
node_version: "24"
repo_url: "https://github.com/owner/repo"
sidebar_autogenerate: true
"""


def render(layer: str, dest: Path, answers: str = "") -> subprocess.CompletedProcess[str]:
    argv = [sys.executable, str(RENDER), layer, str(dest)]
    if answers:
        answers_file = dest.parent / f"{dest.name}-{layer.replace('/', '-')}.yml"
        answers_file.write_text(answers)
        argv += ["--answers", str(answers_file)]
    return subprocess.run(argv, capture_output=True, text=True, check=False)


# --- docs/adr --------------------------------------------------------------


@pytest.fixture
def adr(tmp_path: Path) -> Path:
    dest = tmp_path / "adr"
    dest.mkdir()
    result = render("docs/adr", dest, "project_name: demo\n")
    assert result.returncode == 0, result.stderr
    return dest


def test_the_records_land_under_docs_adr(adr: Path) -> None:
    """`base/repo` creates `docs/` and nothing inside it, so this owns its subtree."""
    assert (adr / "docs" / "adr" / "index.md").is_file()
    assert (adr / "docs" / "adr" / "0000-template.md").is_file()


def test_the_template_sorts_first_and_is_not_a_decision(adr: Path) -> None:
    """Numbered 0000 so it never reads as a decision anyone took."""
    body = (adr / "docs" / "adr" / "0000-template.md").read_text()
    assert "ADR-NNNN" in body
    for heading in ("## Status", "## Context", "## Decision", "## Consequences"):
        assert heading in body, f"the template has no {heading}"


def test_a_written_record_survives_a_second_render(adr: Path) -> None:
    """The index accrues rows and the template accrues local conventions."""
    index = adr / "docs" / "adr" / "index.md"
    index.write_text("# Mine\n\n| ADR-0001 | Chose X | Accepted |\n")

    render("docs/adr", adr, "project_name: demo\n")

    assert "ADR-0001" in index.read_text()


# --- docs/site -------------------------------------------------------------


@pytest.fixture
def site(tmp_path: Path) -> Path:
    dest = tmp_path / "site"
    dest.mkdir()
    result = render("docs/site", dest, SITE_ANSWERS)
    assert result.returncode == 0, result.stderr
    return dest


def config_of(dest: Path) -> str:
    return (dest / "docs" / "site" / "astro.config.mjs").read_text()


def test_the_site_url_is_written(site: Path) -> None:
    """Mandatory rather than optional.

    Without an explicit `site` the Astro sitemap integration warns and emits nothing, so
    the sitemap is silently absent. Verified by building: with it, `sitemap-index.xml` and
    a populated `sitemap-0.xml` were produced.
    """
    assert "site: 'https://owner.github.io/repo'" in config_of(site)


def test_one_engine_renders_at_a_time(site: Path) -> None:
    """A conditional filename holding a quote breaks jinja compilation, so the engine
    comparison is a derived boolean instead."""
    body = config_of(site)
    assert "@astrojs/starlight" in body
    assert "fumadocs" not in body

    deps = json.loads((site / "docs" / "site" / "package.json").read_text())["dependencies"]
    assert "@astrojs/starlight" in deps
    assert "react" not in deps, "starlight needs no React island"


def test_fumadocs_brings_react(tmp_path: Path) -> None:
    """It hydrates the page shell as a React island, where starlight needs none."""
    dest = tmp_path / "fuma"
    dest.mkdir()
    render("docs/site", dest, SITE_ANSWERS.replace("starlight", "fumadocs"))

    deps = json.loads((dest / "docs" / "site" / "package.json").read_text())["dependencies"]
    assert "fumadocs-ui" in deps
    assert "react" in deps
    assert "@astrojs/starlight" not in deps
    # And the starlight-only content config does not come along.
    assert not (dest / "docs" / "site" / "src" / "content.config.ts").exists()


def test_an_absent_repo_url_omits_the_links(tmp_path: Path) -> None:
    """A dead edit link is worse than none."""
    dest = tmp_path / "site"
    dest.mkdir()
    render("docs/site", dest, SITE_ANSWERS.replace('repo_url: "https://github.com/owner/repo"', 'repo_url: ""'))

    body = config_of(dest)
    assert "editLink" not in body
    assert "social" not in body


def test_an_explicit_sidebar_is_written_when_asked(tmp_path: Path) -> None:
    dest = tmp_path / "site"
    dest.mkdir()
    render("docs/site", dest, SITE_ANSWERS.replace("sidebar_autogenerate: true", "sidebar_autogenerate: false"))

    assert "sidebar:" in config_of(dest)


def test_the_build_output_is_ignored(site: Path) -> None:
    """The build writes into the tree rather than a shared location, and an unignored
    artefact is packed into the next agent index."""
    fragment = (site / ".gitignore.d" / "site").read_text()
    for path in ("docs/site/dist/", "docs/site/.astro/", "docs/site/node_modules/"):
        assert path in fragment, f"{path} is unignored"


def test_the_node_pin_satisfies_astro(site: Path) -> None:
    """Astro 7 needs node 22.12 or later."""
    body = (site / ".mise" / "conf.d" / "site.toml").read_text()
    version = next(line for line in body.splitlines() if line.startswith("node"))
    assert int(version.split('"')[1].split(".")[0]) >= 22


def test_a_hand_edited_config_survives_a_second_render(site: Path) -> None:
    path = site / "docs" / "site" / "astro.config.mjs"
    path.write_text("// mine\nexport default {};\n")

    render("docs/site", site, SITE_ANSWERS)

    assert "// mine" in path.read_text()
