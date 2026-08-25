#!/usr/bin/env python3
"""Pin go in the mise fragment from what the module already declares.

    sync_go_pin.py <dest> <go-version>

An empty answer reads the `go` directive from go.mod: `go mod init` wrote the
installed toolchain's own version there, so the generator is the detection.
Without a go.mod -- a fragments-only render, or a workspace whose members come
later -- the running toolchain answers through `go version`, and with no go on
PATH the pin falls back to `latest` rather than an empty string mise rejects.

CI needs none of this: the setup action reads go.mod natively through
`go-version-file`.
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path


def from_go_mod(dest: Path) -> str:
    manifest = dest / "go.mod"
    if not manifest.is_file():
        return ""
    match = re.search(r"^go (\d+\.\d+(?:\.\d+)?)$", manifest.read_text(), re.M)
    return match.group(1) if match else ""


def from_toolchain() -> str:
    if shutil.which("go") is None:
        return ""
    result = subprocess.run(
        ["go", "version"], capture_output=True, text=True, check=False, timeout=30
    )
    match = re.search(r"go(\d+\.\d+)", result.stdout)
    return match.group(1) if match else ""


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    dest = Path(sys.argv[1])
    answered = sys.argv[2].strip()

    version = answered or from_go_mod(dest) or from_toolchain() or "latest"

    fragment = dest / ".mise" / "conf.d" / "go.toml"
    if not fragment.is_file():
        print("no mise fragment here, nothing to pin")
        return 0

    text = fragment.read_text()
    pinned = re.sub(r'^go = "[^"]*"$', f'go = "{version}"', text, count=1, flags=re.M)
    if pinned != text:
        fragment.write_text(pinned)
    print(f"go pinned to {version}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
