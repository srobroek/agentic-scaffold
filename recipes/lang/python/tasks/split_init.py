#!/usr/bin/env python3
"""Empty out the package __init__ that `uv init --lib` fills with a function.

    split_init.py <dest> <layout>

`uv init --lib` writes a `hello()` into `src/<pkg>/__init__.py`. ruff's
`non-empty-init-module` rejects that, so the scaffold fails its own lint before a
line of real code exists.

The fix is the convention the rule exists to encourage: an `__init__.py` that
re-exports, and the code in a module beside it. The function moves to `core.py`
and the `__init__` imports it.

Idempotent, and it leaves anything it did not write alone: an `__init__` that is
already re-exports only, or a `core.py` that already exists, stops the task.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

PLACEHOLDER = '"""{package}."""\n\nfrom {package}.core import hello\n\n__all__ = ["hello"]\n'


def is_reexport_only(source: str) -> bool:
    """True when the module holds nothing but a docstring, imports, and __all__."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return False
    for node in tree.body:
        if isinstance(node, ast.Import | ast.ImportFrom):
            continue
        if isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue  # a docstring
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            continue
        return False
    return True


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2

    dest, layout = sys.argv[1:3]
    root = Path(dest) / ("src" if layout == "src" else ".")
    if not root.is_dir():
        print("no package root, nothing to split")
        return 0

    for init in sorted(root.glob("*/__init__.py")):
        package = init.parent.name
        source = init.read_text()

        if is_reexport_only(source):
            continue

        core = init.parent / "core.py"
        if core.exists():
            print(f"{core.relative_to(dest)} already exists, leaving {package} alone")
            continue

        core.write_text(f'"""Implementation for {package}."""\n\n\n{source.lstrip()}')
        init.write_text(PLACEHOLDER.format(package=package))
        print(f"moved {package}/__init__.py body into {package}/core.py")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
