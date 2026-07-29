#!/usr/bin/env python3
"""Write LICENSE for the answered SPDX identifier.

Three licences are vendored beside this script, so the common cases need no
network. Any other SPDX identifier is fetched from the SPDX licence list.

    write_license.py <dest> <spdx-id> <holder> <year>
"""

from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

VENDORED = Path(__file__).resolve().parent.parent / "licenses"
SPDX_DETAILS = "https://raw.githubusercontent.com/spdx/license-list-data/main/json/details/{id}.json"
TIMEOUT_SECONDS = 15


def vendored_text(spdx_id: str) -> str | None:
    """Match case-insensitively: an SPDX id is case-sensitive, answers are not."""
    for candidate in VENDORED.glob("*.txt"):
        if candidate.stem.lower() == spdx_id.lower():
            return candidate.read_text()
    return None


def fetched_text(spdx_id: str) -> str:
    url = SPDX_DETAILS.format(id=spdx_id)
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            payload = json.loads(response.read())
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise SystemExit(
                f"unknown SPDX identifier {spdx_id!r}. "
                f"Vendored: {', '.join(sorted(p.stem for p in VENDORED.glob('*.txt')))}. "
                "See https://spdx.org/licenses/ for the full list."
            ) from error
        raise SystemExit(f"fetching {spdx_id} failed: HTTP {error.code}") from error
    except (urllib.error.URLError, TimeoutError) as error:
        raise SystemExit(
            f"fetching {spdx_id} failed: {error}. "
            f"Vendored offline: {', '.join(sorted(p.stem for p in VENDORED.glob('*.txt')))}."
        ) from error

    text = payload.get("licenseText")
    if not text:
        raise SystemExit(f"the SPDX entry for {spdx_id} carries no licenceText")
    return text


def substitute(text: str, holder: str, year: str) -> str:
    """Fill the placeholders the licence bodies leave for a holder and a year."""
    if not holder:
        return text
    for placeholder in (
        "<year>",
        "[yyyy]",
        "[year]",
        "<YEAR>",
        "yyyy",
    ):
        text = text.replace(placeholder, year)
    for placeholder in (
        "<name of author>",
        "<copyright holders>",
        "[name of copyright owner]",
        "[fullname]",
        "<COPYRIGHT HOLDER>",
        "name of author",
    ):
        text = text.replace(placeholder, holder)
    return text


def main() -> int:
    if len(sys.argv) != 5:
        print(__doc__, file=sys.stderr)
        return 2

    dest, spdx_id, holder, year = sys.argv[1:5]
    if spdx_id.lower() in {"", "none"}:
        return 0

    text = vendored_text(spdx_id)
    source = "vendored"
    if text is None:
        text = fetched_text(spdx_id)
        source = "spdx.org"

    target = Path(dest) / "LICENSE"
    target.write_text(substitute(text, holder, year))
    print(f"LICENSE written for {spdx_id} ({source})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
