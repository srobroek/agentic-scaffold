"""agentic/rtk: the project-local filters, their trust, and telemetry.

Every claim asserted here was checked against rtk 0.44.1 on 2026-07-29.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
RENDER = REPO_ROOT / "scripts" / "render.py"

needs_rtk = pytest.mark.skipif(shutil.which("rtk") is None, reason="rtk absent from PATH")


def render(dest: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RENDER), "agentic/rtk", str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )


@pytest.fixture
def rtk(tmp_path: Path) -> Path:
    dest = tmp_path / "d"
    dest.mkdir()
    subprocess.run(["git", "init", "-q", str(dest)], check=True)
    result = render(dest)
    assert result.returncode == 0, result.stderr
    return dest


def test_the_filters_land_at_the_one_path_rtk_reads(rtk: Path) -> None:
    """`rtk trust` reads project-local filters from the current directory only.

    Copies under `~/.config/rtk/`, `~/Library/Application Support/rtk/`, and `~/.rtk/`
    are ignored, and `rtk verify` stays at its built-in count, so a misplaced file is a
    silent no-op rather than an error.
    """
    assert (rtk / ".rtk" / "filters.toml").is_file()


def test_the_filter_file_is_valid_toml_and_carries_its_tests(rtk: Path) -> None:
    """`rtk verify` runs the inline tests, which is what catches a filter that matches
    nothing."""
    spec = tomllib.loads((rtk / ".rtk" / "filters.toml").read_text())

    assert spec["schema_version"] == 1
    assert "wt-list" in spec["filters"]
    assert spec["tests"]["wt-list"], "the filter ships no tests"


def test_no_filter_truncates_rows(rtk: Path) -> None:
    """`bd list` measured 23,425 bytes across 222 rows with no ANSI: already dense.

    The only saving on offer was cutting rows to 90 characters for 19 percent, which
    removes the issue titles. Dense output belongs to the spill hook, which keeps the
    head and tail and names a recovery path.
    """
    spec = tomllib.loads((rtk / ".rtk" / "filters.toml").read_text())
    for name, spec_ in spec["filters"].items():
        assert "max_line_length" not in spec_, f"{name} truncates rows"
        assert "truncate" not in str(spec_).lower(), f"{name} truncates rows"


def test_setup_disables_telemetry(rtk: Path) -> None:
    """Consent is machine-global, in rtk's own config directory.

    Verified: a project `.rtk/config.toml` carrying `[telemetry] enabled = false` left
    `rtk telemetry status` unchanged, so no template can set it and the recipe must.
    """
    body = (rtk / ".just.d" / "rtk.just").read_text()
    assert "rtk telemetry disable" in body


def test_setup_trusts_and_verifies(rtk: Path) -> None:
    """The file travels with the clone; the trust is a per-machine content hash and does
    not, so a fresh clone has to run this."""
    body = (rtk / ".just.d" / "rtk.just").read_text()
    assert "rtk trust --yes" in body
    assert "rtk verify" in body


def test_setup_degrades_without_rtk(rtk: Path) -> None:
    """A repository may be cloned by someone who does not have rtk."""
    body = (rtk / ".just.d" / "rtk.just").read_text()
    assert "command -v rtk" in body


def test_a_hand_tuned_filter_survives_a_second_render(rtk: Path) -> None:
    """Editing the file revokes its trust, since rtk hashes the content, so replacing a
    tuned filter would silently stop it working."""
    path = rtk / ".rtk" / "filters.toml"
    path.write_text('schema_version = 1\n\n[filters.mine]\ndescription = "mine"\n')

    render(rtk)

    assert "mine" in path.read_text()


@needs_rtk
def test_rtk_accepts_the_shipped_filters(rtk: Path) -> None:
    """The tool's own reader is the authority on whether a filter file is usable.

    `rtk verify` reports its own built-in tests plus the file's, so the count rising
    above rtk's baseline is what proves the file was loaded rather than ignored.
    """
    trusted = subprocess.run(
        ["rtk", "trust", "--yes"], cwd=rtk, capture_output=True, text=True, check=False
    )
    assert trusted.returncode == 0, trusted.stdout + trusted.stderr

    verified = subprocess.run(
        ["rtk", "verify"], cwd=rtk, capture_output=True, text=True, check=False
    )
    assert verified.returncode == 0, verified.stdout + verified.stderr

    # "156/156 tests passed" when the file's two loaded on top of rtk's 154.
    output = verified.stdout + verified.stderr
    assert "tests passed" in output
    counts = [
        int(part.split("/")[0])
        for part in output.split()
        if "/" in part and part.split("/")[0].isdigit()
    ]
    assert counts and max(counts) > 154, f"the shipped filters were not loaded: {output!r}"
