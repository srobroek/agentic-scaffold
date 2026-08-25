#!/usr/bin/env python3
"""Write LICENSE for the answered identifier.

    write_license.py <dest> <licence-id> <holder> <year>

`gh api /licenses/<key>` is the source. It carries 13 licences, including all
three the policy uses, and needs no vendored copy in this repository.

GitHub keys are lowercase and do not always match the SPDX identifier:
`AGPL-3.0-only` is `agpl-3.0` there. An answer is normalised before the call, and
an identifier GitHub does not carry falls through to the SPDX licence list.
"""

from __future__ import annotations

import json
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

TIMEOUT_SECONDS = 20
SPDX_DETAILS = (
    "https://raw.githubusercontent.com/spdx/license-list-data/main/json/details/{id}.json"
)

# SPDX distinguishes -only from -or-later; GitHub carries one key for both.
SPDX_TO_GH_KEY = {
    "agpl-3.0-only": "agpl-3.0",
    "agpl-3.0-or-later": "agpl-3.0",
    "gpl-3.0-only": "gpl-3.0",
    "gpl-3.0-or-later": "gpl-3.0",
    "gpl-2.0-only": "gpl-2.0",
    "gpl-2.0-or-later": "gpl-2.0",
    "lgpl-2.1-only": "lgpl-2.1",
    "lgpl-2.1-or-later": "lgpl-2.1",
}


def gh_key(licence_id: str) -> str:
    lowered = licence_id.lower()
    return SPDX_TO_GH_KEY.get(lowered, lowered)


def from_gh(licence_id: str) -> tuple[str, str] | None:
    """Return (body, spdx_id) from the GitHub Licenses API, or None."""
    result = subprocess.run(
        ["gh", "api", f"/licenses/{gh_key(licence_id)}"],
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    body = payload.get("body")
    return (body, payload.get("spdx_id") or licence_id) if body else None


def from_spdx(licence_id: str) -> tuple[str, str] | None:
    """Fall back to the SPDX list, which carries every identifier GitHub omits."""
    try:
        with urllib.request.urlopen(
            SPDX_DETAILS.format(id=licence_id), timeout=TIMEOUT_SECONDS
        ) as response:
            payload = json.loads(response.read())
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None
    body = payload.get("licenseText")
    return (body, payload.get("licenseId") or licence_id) if body else None


def available() -> str:
    result = subprocess.run(
        ["gh", "api", "/licenses", "--jq", ".[].spdx_id"],
        capture_output=True,
        text=True,
        check=False,
        timeout=TIMEOUT_SECONDS,
    )
    if result.returncode != 0:
        return "run `gh api /licenses` to list them"
    return ", ".join(result.stdout.split())


def substitute(text: str, holder: str, year: str) -> str:
    """Fill the placeholders a licence body leaves for a holder and a year."""
    if not holder:
        return text
    for placeholder in ("<year>", "[yyyy]", "[year]", "<YEAR>", "[yyyy] [name of copyright owner]"):
        text = text.replace(placeholder, year)
    for placeholder in (
        "<name of author>",
        "<copyright holders>",
        "[name of copyright owner]",
        "[fullname]",
        "<COPYRIGHT HOLDER>",
    ):
        text = text.replace(placeholder, holder)
    return text


def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2

    dest, licence_id, holder, year = sys.argv[1:5]
    if licence_id.lower() in {"", "none"}:
        return 0

    found = from_gh(licence_id)
    source = "gh"
    if found is None:
        found = from_spdx(licence_id)
        source = "spdx.org"
    if found is None:
        raise SystemExit(
            f"no licence text for {licence_id!r}. "
            f"GitHub carries: {available()}. "
            "Any other SPDX identifier must appear at https://spdx.org/licenses/."
        )

    body, spdx_id = found
    (Path(dest) / "LICENSE").write_text(substitute(body, holder, year))
    print(f"LICENSE written for {spdx_id} (via {source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
