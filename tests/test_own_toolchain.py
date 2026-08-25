"""This repository's own mise.toml: every pin has to be a version that exists.

Written after CI failed on `Failed to install pipx:yamllint@1.38.1` while `just check` passed
locally. yamllint's newest release is 1.38.0; 1.38.1 was never published. The local pass was
an accident: a python install carried an unrelated yamllint 1.37.1 earlier on PATH, so the
recipe ran that one and never noticed mise had installed nothing.

The failure mode is specific to a pinned toolchain. `mise install` is the only step that
validates a version string, it runs before the tests, and a tool reachable from somewhere else
on PATH hides the gap from every recipe downstream.
"""

from __future__ import annotations

import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
MISE = REPO_ROOT / "mise.toml"

needs_mise = pytest.mark.skipif(shutil.which("mise") is None, reason="mise absent")

# Pins mise cannot enumerate, with why. `latest` is not a version to check, and a backend
# whose registry has no ls-remote entry would report every pin as missing.
UNCHECKABLE = {"python", "uv", "just", "prek", "cargo:gitnr"}

# `latest` on purpose. Every other entry in mise.toml's pinned block is a version some test
# asserts behaviour against; trivy's findings come from a vulnerability database rather than
# from its own behaviour, and no test here asserts a specific finding.
DELIBERATELY_LATEST = UNCHECKABLE | {"trivy"}


def pins() -> dict[str, str]:
    return tomllib.loads(MISE.read_text())["tools"]


def test_every_tool_is_pinned_or_deliberately_latest() -> None:
    """A test skips rather than fails when its tool is absent, so an unpinned toolchain means a
    green run that checked less than it appears to."""
    for name, spec in pins().items():
        assert isinstance(spec, str), f"{name} is not a plain version string"
        if spec == "latest":
            assert name in DELIBERATELY_LATEST, (
                f"{name} is `latest`; pin it, or record here why it should float"
            )


@needs_mise
@pytest.mark.slow
def test_every_pinned_version_exists() -> None:
    """`mise ls-remote <tool>` lists what can be installed. A pin absent from that list fails
    the toolchain install in CI, which happens before any test runs and reports as a mise exit
    code rather than as a bad version."""
    missing = []
    for name, spec in pins().items():
        if spec == "latest" or name in UNCHECKABLE:
            continue
        result = subprocess.run(
            ["mise", "ls-remote", name],
            capture_output=True,
            text=True,
            check=False,
            timeout=300,
        )
        if result.returncode != 0:
            # A backend that cannot enumerate is not evidence the pin is wrong.
            continue
        available = set(result.stdout.split())
        if not available:
            # Exit 0 with nothing listed, which `aqua:gastownhall/beads` does: mise warns
            # `No versions found` and still succeeds. Treating that as a missing version failed
            # the gate on a pin that was installed and working, so an empty list is the same
            # non-evidence as a failed lookup.
            continue
        if spec not in available:
            newest = sorted(available)[-3:] if available else []
            missing.append(f"{name}={spec} (available near: {newest})")

    assert not missing, "pinned versions that do not exist: " + "; ".join(missing)


@needs_mise
def test_the_config_linters_resolve_through_mise() -> None:
    """`lint-config` runs these bare, so one reachable from elsewhere on PATH runs instead of
    the pinned one and the pin is never exercised. That is exactly how yamllint 1.38.1 passed
    locally and failed in CI."""
    for tool in ("yamllint", "taplo", "actionlint", "zizmor"):
        result = subprocess.run(
            ["mise", "which", tool],
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
        if result.returncode != 0:
            pytest.skip(f"{tool} not installed yet; `just setup` installs the toolchain")
        assert "/mise/installs/" in result.stdout, (
            f"{tool} resolves to {result.stdout.strip()}, outside mise, so the pin in "
            "mise.toml is not what lint-config runs"
        )


@needs_mise
def test_every_runtime_a_layer_requires_is_pinned() -> None:
    """A layer declaring `requires_bin` refuses to render without it, so an absent runtime
    fails a test rather than skipping it.

    15 tests failed in CI on `lang/ts needs bun on PATH` and `agentic/beads needs bd on PATH`
    while passing locally, where both happened to be installed outside mise.
    """
    required = set()
    for config in sorted(REPO_ROOT.glob("recipes/*/*/copier.yml")):
        config_data = yaml.safe_load(config.read_text()) or {}
        meta = config_data.get("_scaffold") or {}
        for binary in meta.get("requires_bin") or []:
            required.add(binary)

    # Supplied by the ubuntu-latest runner image rather than by mise, confirmed by CI: the run
    # that failed 15 tests on absent bun and bd reported nothing about these.
    from_elsewhere = {"git", "python3", "gh", "cargo"}

    # mise.toml is what a fresh runner installs from. `mise which` is not the test: it resolves
    # from whatever is already in the install cache, so it answers for this machine and passes
    # even when the tool was never pinned. That is the exact failure being guarded against.
    #
    # A backend prefix names its own binary: `aqua:gastownhall/beads` provides `bd`.
    provided = set()
    for name in pins():
        provided.add(name)
        provided.add(name.rsplit("/", 1)[-1])
        provided.add(name.split(":", 1)[-1])
    provided |= {"bd"} if "aqua:gastownhall/beads" in pins() else set()

    missing = sorted(required - from_elsewhere - provided)
    assert not missing, (
        f"layers require {missing} and mise.toml pins none of them, so every test that renders "
        "such a layer fails instead of skipping"
    )


def test_no_test_hardcodes_a_mise_latest_path() -> None:
    """`installs/<tool>/latest` is a symlink to whatever version was installed last, not to what
    mise.toml pins, and on a CI runner it does not exist at all.

    Both failures happened. It pointed at node 25 locally while the pin said 24, and on the
    runner the CDK tests fell through to the image's own npm, whose `npm ci` broke projen's
    generated `install:ci` task: five errors in CI against a local pass, testing a version the
    pin never named. `conftest.mise_bin` asks `mise which` instead.
    """
    offenders = []
    for path in sorted((REPO_ROOT / "tests").glob("test_*.py")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            if "installs/" not in line or "/latest" not in line:
                continue
            # Prose about the trap is not an instance of it. A real one is a path literal, so
            # it carries the mise prefix inside quotes.
            if '".local/share/mise/installs' not in line:
                continue
            offenders.append(f"{path.name}:{number}")
    assert not offenders, (
        "these hardcode a mise `latest` path instead of calling conftest.mise_bin: "
        + ", ".join(offenders)
    )


def test_every_binary_a_recipe_invokes_is_pinned() -> None:
    """A recipe shelling out to an unpinned tool exits 127 in CI while passing locally.

    `just packages` did exactly that: apm came from pipx outside any pin, so the recipe worked
    here and failed on the runner. The requires_bin check above did not catch it, because no
    layer declares apm -- the scaffold's own justfile invokes it.
    """
    justfile = (REPO_ROOT / "justfile").read_text()

    # Bare command words at the start of a recipe line. Enough to catch a tool nobody pinned
    # without parsing just's grammar.
    invoked = set()
    for line in justfile.splitlines():
        if not line.startswith(("    ", "\t")):
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith(("#", "@", "-", "{{", "set ", "if ", "fi", "for ")):
            continue
        word = stripped.split()[0]
        if word.isidentifier() or "-" in word:
            invoked.add(word)

    # Provided by the runner image, by uv, or by just itself.
    from_elsewhere = {
        "git", "python3", "echo", "cd", "mkdir", "cp", "rm", "test", "then", "else", "done",
        "exit", "printf", "grep", "sed", "awk", "find", "sort", "uniq", "head", "tail", "cat",
        "just", "uv", "true", "false", "export", "local", "shift", "read", "case", "esac",
        "while", "do", "trap", "shopt", "diff", "ls", "wc", "tr", "xargs", "bash", "sh", "gh",
        "cargo", "npm", "npx",
        # mise cannot pin itself: it is what installs everything else, and mise-action puts it
        # on the runner's PATH.
        "mise",
    }

    pinned = set()
    for name in pins():
        pinned.add(name)
        pinned.add(name.rsplit("/", 1)[-1])
        pinned.add(name.split(":", 1)[-1])
    # A backend prefix names the package, not always the binary it installs. Each mapping is
    # keyed on the pin, so removing the pin removes the binary too -- listing the binaries
    # unconditionally would defeat the check.
    BINARY_OF = {
        "aqua:gastownhall/beads": "bd",
        "pipx:apm-cli": "apm",
        "npm:@moonrepo/cli": "moon",
        "ubi:oasdiff/oasdiff": "oasdiff",
        "cargo:gitnr": "gitnr",
    }
    for spec, binary in BINARY_OF.items():
        if spec in pins():
            pinned.add(binary)

    missing = sorted(invoked - from_elsewhere - pinned)
    assert not missing, (
        f"these recipes invoke {missing}, which mise.toml does not pin, so they exit 127 on a "
        "runner while passing locally"
    )


def test_every_template_compiles_as_jinja() -> None:
    """A template that fails to compile is invisible until something renders it.

    `${#name}` opens jinja's comment tag, so a bash array length or string length in a workflow
    body made copier abort with `Missing end of comment tag` -- naming no file and no line. The
    render left the previous output in place, so linting the "rendered" file passed against a
    stale copy and the defect shipped twice. Wrapping the body in `{% raw %}` is the fix; this
    test is what makes the next one fail here rather than in CI.

    Compilation only. Rendering needs each layer's answers, which the per-layer tests supply.
    """
    from jinja2 import Environment, TemplateSyntaxError

    # copier's own delimiters. The defaults would not reproduce the failure.
    env = Environment(
        block_start_string="{%",
        block_end_string="%}",
        variable_start_string="{{",
        variable_end_string="}}",
        comment_start_string="{#",
        comment_end_string="#}",
        keep_trailing_newline=True,
    )

    broken = []
    for path in sorted((REPO_ROOT / "recipes").rglob("*.jinja")):
        try:
            env.parse(path.read_text(encoding="utf-8"))
        except TemplateSyntaxError as error:
            broken.append(f"{path.relative_to(REPO_ROOT)}:{error.lineno}: {error.message}")
        except UnicodeDecodeError:
            # A binary asset that happens to end in .jinja is not a template defect.
            continue

    assert not broken, "templates that do not compile:\n  " + "\n  ".join(broken)
