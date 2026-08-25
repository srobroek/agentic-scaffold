#!/usr/bin/env python3
"""Settle the opentofu and tflint pins from the newest released versions.

    resolve_versions.py <dest> <opentofu-version> <tflint-version>

An empty answer asks mise for the latest release, so a render never freezes at
the template's authoring-day version. An explicit answer wins, and with mise
absent or offline the pin falls back to the floor below -- the newest version
the recipe was verified against -- rather than an empty string mise rejects.

Rewrites what the render already wrote: the mise fragment and the two
required_version floors. required_version is `>=`, so a newer pin only widens
what an existing checkout accepts.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

# The newest versions this recipe's assertions were verified against.
FLOOR = {"opentofu": "1.12.5", "tflint": "0.64.0"}


def latest(tool: str) -> str:
    if shutil.which("mise") is None:
        return ""
    result = subprocess.run(
        ["mise", "latest", tool], capture_output=True, text=True, check=False, timeout=60
    )
    version = result.stdout.strip()
    return version if result.returncode == 0 and re.fullmatch(r"[\d.]+", version) else ""


def settle(path: Path, pattern: str, replacement: str) -> None:
    if not path.is_file():
        return
    text = path.read_text()
    settled = re.sub(pattern, replacement, text, flags=re.M)
    if settled != text:
        path.write_text(settled)


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2

    dest = Path(sys.argv[1])
    versions = {}
    for tool, answered in (("opentofu", sys.argv[2]), ("tflint", sys.argv[3])):
        versions[tool] = answered.strip() or latest(tool) or FLOOR[tool]

    settle(
        dest / ".mise" / "conf.d" / "terraform.toml",
        r'^opentofu = "[^"]*"$',
        f'opentofu = "{versions["opentofu"]}"',
    )
    settle(
        dest / ".mise" / "conf.d" / "terraform.toml",
        r'^tflint = "[^"]*"$',
        f'tflint = "{versions["tflint"]}"',
    )
    for versions_tf in (
        dest / "infra" / "versions.tf",
        dest / "infra" / "bootstrap" / "versions.tf",
    ):
        settle(
            versions_tf,
            r'^  required_version = ">= [^"]*"$',
            f'  required_version = ">= {versions["opentofu"]}"',
        )

    print(f"pinned opentofu {versions['opentofu']}, tflint {versions['tflint']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
