#!/usr/bin/env python3
"""Render one layer into a destination.

    render.py <group>/<layer> <dest> [--answers FILE] [--pretend]

Exit codes:
    0  rendered
    2  usage error, or unknown layer
    3  a required executable is missing, or a precheck refused
    4  copier raised
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
TEMPLATES = REPO_ROOT / "templates"


def die(code: int, message: str) -> None:
    print(f"error: {message}", file=sys.stderr)
    raise SystemExit(code)


def layer_dir(layer: str) -> Path:
    if layer.count("/") != 1:
        die(2, f"layer must be <group>/<name>, got {layer!r}")
    path = TEMPLATES / layer
    if not path.is_dir():
        die(2, f"no such layer: {layer}")
    if not (path / "copier.yml").is_file():
        die(2, f"{layer} has no copier.yml")
    return path


def layer_meta(path: Path) -> dict:
    """Read the `_scaffold` block from copier.yml.

    copier ignores unknown underscore keys, so layer metadata lives there rather
    than in a second file that could disagree with it.
    """
    config = yaml.safe_load((path / "copier.yml").read_text()) or {}
    meta = config.get("_scaffold") or {}
    return meta if isinstance(meta, dict) else {}


def check_binaries(layer: str, meta: dict) -> None:
    missing = [b for b in meta.get("requires_bin", []) if shutil.which(b) is None]
    if missing:
        die(3, f"{layer} needs {', '.join(missing)} on PATH")


def run_precheck(layer: str, path: Path, meta: dict, dest: Path) -> None:
    name = meta.get("precheck")
    if not name:
        return
    script = path / name
    if not script.is_file():
        die(3, f"{layer} declares precheck {name!r}, which is absent")
    result = subprocess.run(
        [sys.executable, str(script), str(dest)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        die(3, f"{layer} precheck refused: {detail}")


def render(layer: str, dest: Path, answers: Path | None, pretend: bool) -> None:
    path = layer_dir(layer)
    meta = layer_meta(path)
    check_binaries(layer, meta)
    run_precheck(layer, path, meta, dest)

    command = [
        sys.executable,
        "-m",
        "copier",
        "copy",
        "--trust",
        "--defaults",
        "--overwrite",
    ]
    if pretend:
        command.append("--pretend")
    if answers:
        if not answers.is_file():
            die(2, f"no such answers file: {answers}")
        command += ["--data-file", str(answers)]
    command += [str(path), str(dest)]

    result = subprocess.run(command, check=False)
    if result.returncode != 0:
        die(4, f"copier failed rendering {layer} (exit {result.returncode})")


def main() -> int:
    parser = argparse.ArgumentParser(prog="render.py", description=__doc__)
    parser.add_argument("layer", help="<group>/<name> under templates/")
    parser.add_argument("dest", type=Path)
    parser.add_argument("--answers", type=Path, help="YAML file of answers")
    parser.add_argument(
        "--pretend",
        action="store_true",
        help="list what would be written, writing nothing",
    )
    args = parser.parse_args()

    render(args.layer, args.dest, args.answers, args.pretend)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
