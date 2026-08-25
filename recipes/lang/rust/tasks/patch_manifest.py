#!/usr/bin/env python3
"""Add to Cargo.toml what `cargo init` leaves out.

    patch_manifest.py <dest> <spdx-id> <edition>

`cargo init` writes no `license` key, so `cargo deny check licenses` fails against
the crate itself. It also writes no `[lints]` table, so lint policy would live in
CI arguments rather than in the manifest where `cargo clippy` reads it.

An empty `<edition>` keeps whatever `cargo init` wrote, which is the installed
toolchain's own current edition -- the detection is cargo itself. A value is for
a workspace, where the root manifest pins `edition.workspace` before cargo runs.

Also settles the Cargo.lock line in `.gitignore.d/rust` from the tree: a
`src/main.rs` is a binary and commits the lockfile, a `src/lib.rs` ignores it.
The `crate_kind` answer decided the fragment at render time and stays
authoritative only where no src/ exists yet -- a workspace root.

Edits in place and is idempotent: an existing key is left alone rather than
duplicated. Does nothing when there is no Cargo.toml, since a workspace root
renders before its members.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

LINTS = """
[lints.rust]
unsafe_code = "forbid"
unused_qualifications = "warn"
# missing_docs is deliberately absent. CI runs clippy with `-D warnings`, which
# promotes every warn to an error, so a warn-level missing_docs fails the build on
# `cargo init`'s own scaffold. Turn it on once the public surface is documented.

[lints.clippy]
# Deny the groups that catch real defects.
correctness = { level = "deny", priority = -1 }
suspicious = { level = "deny", priority = -1 }
perf = { level = "deny", priority = -1 }
# pedantic stays off. CI runs `clippy -D warnings`, which promotes every warn to
# an error, and pedantic fires on `cargo init`'s own scaffold (must_use_candidate
# on a two-line function). Enable it per crate once the code is written.
unwrap_used = "warn"
expect_used = "warn"

[lints.rustdoc]
broken_intra_doc_links = "deny"
"""


def has_table(text: str, table: str) -> bool:
    return f"[{table}]" in text or f"[{table}." in text


FRAGMENT_LIB = """# rust
# A library ignores Cargo.lock; a binary commits it so builds reproduce.
Cargo.lock
"""

FRAGMENT_BIN = """# rust
# A binary commits Cargo.lock, so nothing conditional is ignored here.
"""


def settle_lockfile_line(dest: Path) -> None:
    """Rewrite the rust gitignore fragment from what src/ actually holds."""
    fragment = dest / ".gitignore.d" / "rust"
    if not fragment.is_file():
        return
    if (dest / "src" / "main.rs").is_file():
        wanted = FRAGMENT_BIN
    elif (dest / "src" / "lib.rs").is_file():
        wanted = FRAGMENT_LIB
    else:
        return  # a workspace root: the crate_kind answer already decided
    if fragment.read_text() != wanted:
        fragment.write_text(wanted)
        print("settled .gitignore.d/rust from src/")


def main() -> int:
    if len(sys.argv) != 4:
        print(__doc__, file=sys.stderr)
        return 2

    dest, spdx_id, edition = sys.argv[1:4]
    settle_lockfile_line(Path(dest))

    manifest = Path(dest) / "Cargo.toml"
    if not manifest.is_file():
        print("no Cargo.toml here, nothing to patch")
        return 0

    text = manifest.read_text()
    try:
        parsed = tomllib.loads(text)
    except tomllib.TOMLDecodeError as error:
        raise SystemExit(f"Cargo.toml does not parse: {error}") from error

    # A virtual workspace manifest carries no [package]; lints go on the members.
    package = parsed.get("package")
    if package is None:
        print("workspace manifest, leaving it alone")
        return 0

    changed = []

    if "license" not in package and "license-file" not in package:
        marker = "[package]\n"
        index = text.index(marker) + len(marker)
        text = f'{text[:index]}license = "{spdx_id}"\n{text[index:]}'
        changed.append(f"license = {spdx_id}")

    # An empty answer keeps what cargo wrote: cargo's own default IS the
    # installed toolchain's current edition, so cargo is the detection.
    if edition and "edition" in package and package.get("edition") != edition:
        text = text.replace(f'edition = "{package["edition"]}"', f'edition = "{edition}"')
        changed.append(f"edition = {edition}")

    if not has_table(text, "lints"):
        text = text.rstrip() + "\n" + LINTS
        changed.append("[lints]")

    if changed:
        manifest.write_text(text)
        print(f"Cargo.toml patched: {', '.join(changed)}")
    else:
        print("Cargo.toml already carries license, edition, and lints")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
